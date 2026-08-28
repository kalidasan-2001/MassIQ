"""R7 scope: PlanScale confirmation and retrieval (R7 sections 13-15).

Closes the gap the R6 independent review's own audit surfaced: the legacy
MVP's `scale.pixelsPerMeter` lives only in ephemeral React state
(`PlanViewer.jsx`) and is never persisted. QuantityService requires a
confirmed PlanScale to exist before it will compute anything (R7 section
49 -- "scale requires user confirmation").

Never trusts an OCR/AI-derived scale automatically (R7 section 14) --
there is no code path here that reads a VLM/OCR suggestion and writes a
PlanScale; only an explicit `confirm_declared_scale`/`confirm_calibrated_distance`
call (a real user action) ever does.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.geometry.config import POINTS_TO_METERS
from app.models.plan_scale import PlanScale, PlanScaleMethod
from app.services.plan_service import PlanService
from app.services.storage_service import StorageService

__all__ = [
    "PlanScaleService",
    "PlanScaleNotFoundError",
    "InvalidScaleError",
]


class PlanScaleNotFoundError(Exception):
    def __init__(self, plan_page_id: uuid.UUID):
        self.plan_page_id = plan_page_id
        super().__init__(f"No confirmed scale for PlanPage {plan_page_id}")


class InvalidScaleError(Exception):
    """Controlled validation error (R7 section 11) -- never a raw
    ZeroDivisionError/ValueError leaking to the API caller."""


class PlanScaleService:
    def __init__(self, db: Session, storage: StorageService | None = None):
        self._db = db
        self._plan_service = PlanService(db, storage=storage or StorageService())

    def get_scale(self, project_id: uuid.UUID, plan_id: uuid.UUID, page_number: int) -> PlanScale:
        page = self._plan_service.get_page(project_id, plan_id, page_number)
        scale = self._db.query(PlanScale).filter_by(plan_page_id=page.id).one_or_none()
        if scale is None:
            raise PlanScaleNotFoundError(page.id)
        return scale

    def get_scale_or_none(self, project_id: uuid.UUID, plan_id: uuid.UUID, page_number: int) -> PlanScale | None:
        page = self._plan_service.get_page(project_id, plan_id, page_number)
        return self._db.query(PlanScale).filter_by(plan_page_id=page.id).one_or_none()

    def confirm_declared_scale(
        self, project_id: uuid.UUID, plan_id: uuid.UUID, page_number: int, declared_ratio: float
    ) -> PlanScale:
        """`declared_ratio` is the "1:N" reduction factor (e.g. 100 for
        "1:100") -- see PlanScale's docstring for the documented 100%-print
        assumption this method relies on."""
        if declared_ratio is None or declared_ratio != declared_ratio or declared_ratio <= 0:
            raise InvalidScaleError("declared_ratio must be a positive, finite number")
        real_meters_per_plan_point = POINTS_TO_METERS * declared_ratio
        return self._upsert(
            project_id,
            plan_id,
            page_number,
            method=PlanScaleMethod.DECLARED_SCALE,
            declared_ratio=declared_ratio,
            calibrated_distance_plan_points=None,
            calibrated_distance_real_m=None,
            real_meters_per_plan_point=real_meters_per_plan_point,
        )

    def confirm_calibrated_distance(
        self,
        project_id: uuid.UUID,
        plan_id: uuid.UUID,
        page_number: int,
        calibrated_distance_plan_points: float,
        calibrated_distance_real_m: float,
    ) -> PlanScale:
        for value, label in (
            (calibrated_distance_plan_points, "calibrated_distance_plan_points"),
            (calibrated_distance_real_m, "calibrated_distance_real_m"),
        ):
            if value is None or value != value or value <= 0:
                raise InvalidScaleError(f"{label} must be a positive, finite number")
        real_meters_per_plan_point = calibrated_distance_real_m / calibrated_distance_plan_points
        return self._upsert(
            project_id,
            plan_id,
            page_number,
            method=PlanScaleMethod.CALIBRATED_DISTANCE,
            declared_ratio=None,
            calibrated_distance_plan_points=calibrated_distance_plan_points,
            calibrated_distance_real_m=calibrated_distance_real_m,
            real_meters_per_plan_point=real_meters_per_plan_point,
        )

    def _upsert(
        self,
        project_id: uuid.UUID,
        plan_id: uuid.UUID,
        page_number: int,
        *,
        method: PlanScaleMethod,
        declared_ratio: float | None,
        calibrated_distance_plan_points: float | None,
        calibrated_distance_real_m: float | None,
        real_meters_per_plan_point: float,
    ) -> PlanScale:
        page = self._plan_service.get_page(project_id, plan_id, page_number)
        existing = self._db.query(PlanScale).filter_by(plan_page_id=page.id).one_or_none()
        now = datetime.now(timezone.utc)
        if existing is not None:
            # Re-confirming replaces the existing row in place (matches
            # HatchFeatureSet's own "recompute replaces" precedent) --
            # scale is a property of the page, and a page has exactly one
            # current scale at a time.
            existing.method = method
            existing.declared_ratio = declared_ratio
            existing.calibrated_distance_plan_points = calibrated_distance_plan_points
            existing.calibrated_distance_real_m = calibrated_distance_real_m
            existing.real_meters_per_plan_point = real_meters_per_plan_point
            existing.confirmed_at = now
            self._db.commit()
            self._db.refresh(existing)
            return existing

        scale = PlanScale(
            project_id=project_id,
            plan_id=plan_id,
            plan_page_id=page.id,
            method=method,
            declared_ratio=declared_ratio,
            calibrated_distance_plan_points=calibrated_distance_plan_points,
            calibrated_distance_real_m=calibrated_distance_real_m,
            real_meters_per_plan_point=real_meters_per_plan_point,
            confirmed_at=now,
        )
        self._db.add(scale)
        self._db.commit()
        self._db.refresh(scale)
        return scale
