"""R7 scope: the one authoritative, backend-computed QuantityResult
calculator (R7 section 6 -- "avoid two independent business-rule
implementations"). The frontend may compute a temporary preview, but the
persisted, exported number always comes from here.

Never trusts a frontend-provided `final_area` (R7 section 20) -- the only
inputs this service accepts from the caller are the DetectionRun to
calculate for and the explicitly confirmed dimension value. Everything
else (accepted regions, manual corrections, confirmed scale) is derived
from persistence, the same discipline R4-R6's explicit-computation-only
services already follow.

Idempotence policy (R7 section 21): calculating for the same
DetectionRun always UPDATES the one QuantityResult row for that run
(unique constraint on detection_run_id) rather than creating a duplicate.
Every recalculation resets `status` back to DRAFT and clears
`confirmed_at` -- a CONFIRMED result reflects a specific, already-seen
number; if the underlying review state changes and the number is
recomputed, that confirmation no longer applies to whatever the new
number is, so it is never carried forward silently.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.geometry.config import CALCULATION_VERSION
from app.geometry.service import NormalizedRect, compute_final_area_m2
from app.models.detected_region import DetectedRegionStatus
from app.models.manual_region_correction import ManualCorrectionType
from app.models.plan_page import PlanPage
from app.models.plan_scale import PlanScale
from app.models.quantity_result import QuantityResult, QuantityResultStatus
from app.services.detection_service import DetectionService
from app.services.manual_correction_service import ManualCorrectionService
from app.services.plan_scale_service import PlanScaleService
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)

__all__ = [
    "QuantityService",
    "InvalidDimensionError",
    "ScaleNotConfirmedError",
    "QuantityResultNotFoundError",
]


class InvalidDimensionError(Exception):
    """R7 section 11/17 -- the confirmed height/thickness must be an
    explicit, positive, finite number. Never derived from similarity,
    pattern library data, or OCR alone."""


class ScaleNotConfirmedError(Exception):
    """R7 section 49 -- quantity cannot be calculated before the page's
    scale has been explicitly confirmed. Wraps PlanScaleNotFoundError with
    quantity-calculation-specific context."""

    def __init__(self, plan_page_id: uuid.UUID):
        self.plan_page_id = plan_page_id
        super().__init__(f"PlanPage {plan_page_id} has no confirmed scale -- confirm scale before calculating quantity")


class QuantityResultNotFoundError(Exception):
    def __init__(self, run_id: uuid.UUID):
        self.run_id = run_id
        super().__init__(f"No QuantityResult for DetectionRun {run_id}")


class QuantityService:
    def __init__(self, db: Session, storage: StorageService | None = None):
        self._db = db
        storage = storage or StorageService()
        self._detection_service = DetectionService(db, storage=storage)
        self._manual_correction_service = ManualCorrectionService(db, storage=storage)
        self._scale_service = PlanScaleService(db, storage=storage)

    def calculate(
        self, project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID, confirmed_dimension_m: float
    ) -> QuantityResult:
        if (
            confirmed_dimension_m is None
            or confirmed_dimension_m != confirmed_dimension_m  # NaN
            or confirmed_dimension_m in (float("inf"), float("-inf"))
            or confirmed_dimension_m <= 0
        ):
            raise InvalidDimensionError("confirmed_dimension_m must be a positive, finite number")

        start = time.perf_counter()
        run = self._detection_service.get_run(project_id, plan_id, run_id)  # ownership-checked

        page = self._db.get(PlanPage, run.plan_page_id)  # DetectionRun.plan_page_id already ownership-verified via get_run

        scale = self._db.query(PlanScale).filter_by(plan_page_id=page.id).one_or_none()
        if scale is None:
            raise ScaleNotConfirmedError(page.id)

        # CANDIDATE/REJECTED contribute zero -- only ACCEPTED regions ever
        # participate (R7 section 3, release-critical human-authority rule).
        regions = self._detection_service.list_regions(project_id, plan_id, run_id)
        accepted_regions = [r for r in regions if r.status == DetectedRegionStatus.ACCEPTED]

        corrections = self._manual_correction_service.list_corrections(project_id, plan_id, run_id)
        additions = [c for c in corrections if c.correction_type == ManualCorrectionType.ADD]
        subtractions = [c for c in corrections if c.correction_type == ManualCorrectionType.SUBTRACT]

        positive_rects = [NormalizedRect(r.x, r.y, r.width, r.height) for r in accepted_regions] + [
            NormalizedRect(c.x, c.y, c.width, c.height) for c in additions
        ]
        negative_rects = [NormalizedRect(c.x, c.y, c.width, c.height) for c in subtractions]

        final_area_m2 = compute_final_area_m2(
            positive_rects,
            negative_rects,
            page_width_points=page.width,
            page_height_points=page.height,
            real_meters_per_plan_point=scale.real_meters_per_plan_point,
        )
        volume_m3 = final_area_m2 * confirmed_dimension_m

        result = self._db.query(QuantityResult).filter_by(detection_run_id=run.id).one_or_none()
        if result is None:
            result = QuantityResult(
                project_id=project_id,
                plan_id=plan_id,
                plan_page_id=page.id,
                detection_run_id=run.id,
            )
            self._db.add(result)

        result.final_area_m2 = final_area_m2
        result.confirmed_dimension_m = confirmed_dimension_m
        result.volume_m3 = volume_m3
        result.calculation_version = CALCULATION_VERSION
        result.status = QuantityResultStatus.DRAFT
        result.confirmed_at = None
        result.accepted_region_count = len(accepted_regions)
        result.manual_add_count = len(additions)
        result.manual_subtract_count = len(subtractions)
        self._db.commit()
        self._db.refresh(result)

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "quantity_calculated project_id=%s detection_run_id=%s quantity_result_id=%s "
            "accepted_region_count=%d manual_add_count=%d manual_subtract_count=%d "
            "calculation_version=%s duration_ms=%.1f",
            project_id, run.id, result.id, len(accepted_regions), len(additions), len(subtractions),
            CALCULATION_VERSION, duration_ms,
        )
        return result

    def get_result(self, project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID) -> QuantityResult:
        run = self._detection_service.get_run(project_id, plan_id, run_id)  # ownership-checked
        result = self._db.query(QuantityResult).filter_by(detection_run_id=run.id).one_or_none()
        if result is None:
            raise QuantityResultNotFoundError(run_id)
        return result

    def confirm(self, project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID) -> QuantityResult:
        result = self.get_result(project_id, plan_id, run_id)
        result.status = QuantityResultStatus.CONFIRMED
        result.confirmed_at = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(result)
        return result
