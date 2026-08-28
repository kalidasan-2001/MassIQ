"""R7 scope: ManualRegionCorrection CRUD, scoped to one DetectionRun (R7
section 8). Ownership/ existence is always resolved through
DetectionService.get_run first (defense in depth, same pattern R6's own
DetectionService._require_run establishes) -- a client can never address a
correction on a run it does not own, and a correction is always created
against a run+page that genuinely exist.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.geometry.service import NormalizedRect
from app.models.detection_run import DetectionRun
from app.models.manual_region_correction import ManualCorrectionType, ManualRegionCorrection
from app.services.detection_service import DetectionService
from app.services.storage_service import StorageService

__all__ = [
    "ManualCorrectionService",
    "ManualCorrectionNotFoundError",
    "InvalidCorrectionGeometryError",
]

MIN_DIMENSION = 1e-6  # normalized units -- rejects zero/negative-area rects


class ManualCorrectionNotFoundError(Exception):
    def __init__(self, correction_id: uuid.UUID):
        self.correction_id = correction_id
        super().__init__(f"ManualRegionCorrection {correction_id} not found")


class InvalidCorrectionGeometryError(Exception):
    """Controlled validation error (R7 section 11) -- negative/zero
    width or height, NaN/Infinity, or a rect extending outside the
    [0,1] page bounds. Never a raw geometry-stack traceback."""


def _validate_normalized_rect(x: float, y: float, width: float, height: float) -> None:
    values = (x, y, width, height)
    for value in values:
        if value is None or value != value or value in (float("inf"), float("-inf")):
            raise InvalidCorrectionGeometryError("Geometry values must be finite numbers (no NaN/Infinity)")
    if width <= MIN_DIMENSION or height <= MIN_DIMENSION:
        raise InvalidCorrectionGeometryError("width and height must be positive (zero-area regions are not allowed)")
    if x < 0 or y < 0:
        raise InvalidCorrectionGeometryError("x and y must be >= 0")
    if x + width > 1 + 1e-9 or y + height > 1 + 1e-9:
        raise InvalidCorrectionGeometryError("Region must lie within the page bounds ([0,1] normalized)")


class ManualCorrectionService:
    def __init__(self, db: Session, storage: StorageService | None = None):
        self._db = db
        self._detection_service = DetectionService(db, storage=storage or StorageService())

    def _require_run(self, project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID) -> DetectionRun:
        return self._detection_service.get_run(project_id, plan_id, run_id)

    def create_correction(
        self,
        project_id: uuid.UUID,
        plan_id: uuid.UUID,
        run_id: uuid.UUID,
        correction_type: ManualCorrectionType,
        rect: NormalizedRect,
    ) -> ManualRegionCorrection:
        run = self._require_run(project_id, plan_id, run_id)
        _validate_normalized_rect(rect.x, rect.y, rect.width, rect.height)

        correction = ManualRegionCorrection(
            project_id=project_id,
            plan_id=plan_id,
            plan_page_id=run.plan_page_id,
            detection_run_id=run.id,
            correction_type=correction_type,
            x=rect.x,
            y=rect.y,
            width=rect.width,
            height=rect.height,
        )
        self._db.add(correction)
        self._db.commit()
        self._db.refresh(correction)
        return correction

    def list_corrections(
        self, project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID
    ) -> list[ManualRegionCorrection]:
        run = self._require_run(project_id, plan_id, run_id)
        return (
            self._db.query(ManualRegionCorrection)
            .filter_by(detection_run_id=run.id)
            .order_by(ManualRegionCorrection.created_at.asc())
            .all()
        )

    def delete_correction(
        self, project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID, correction_id: uuid.UUID
    ) -> None:
        run = self._require_run(project_id, plan_id, run_id)
        correction = self._db.get(ManualRegionCorrection, correction_id)
        if correction is None or correction.detection_run_id != run.id:
            raise ManualCorrectionNotFoundError(correction_id)
        self._db.delete(correction)
        self._db.commit()
