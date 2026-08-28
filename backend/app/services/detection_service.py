"""R6 Detection Engine V2 application service.

Boundary this whole module exists to enforce (R6 section 23, non-
negotiable): a DetectionRun and its DetectedRegions NEVER write to a
quantity/area/volume field, anywhere. There is no such field on either
model, no import of quantityEngine-equivalent logic here, and no code
path in this file computes an area. A DetectedRegion's `status` (CANDIDATE
/ACCEPTED/REJECTED) is set only by an explicit user action
(`update_region_status`) -- final quantity math remains entirely the
existing frontend's job, over whatever accepted-region state the user
chose, exactly as it already works for the legacy MVP flow (see
frontend/src/utils/quantityEngine.js, untouched by R6).

Composes LegendService/PatternLibraryService/PlanService for ownership and
reference resolution -- never duplicates their checks. The actual CV
pipeline (tiling, extraction, gating, scoring, merging) lives in
`app.detection.*`, which this service calls exactly once per run and
never re-implements.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

import cv2
import numpy as np

from app.detection.config import (
    CANDIDATE_SIMILARITY_THRESHOLD,
    DETECTOR_VERSION,
    MIN_EVIDENCE_COVERAGE_FOR_CANDIDATE,
    TILE_SIZE_PX,
    TILE_STRIDE_PX,
)
from app.detection.detector import TooManyTilesError, run_detection
from app.hatch.config import FEATURE_VERSION
from app.hatch.similarity.models import ComparableFeatures
from app.models.detected_region import DetectedRegion, DetectedRegionStatus
from app.models.detection_run import DetectionRun, DetectionRunStatus
from app.models.hatch_feature_set import HatchFeatureSet
from app.models.legend_entry import LegendEntryStatus
from app.models.pattern_library_entry import PatternLibraryEntry
from app.services.legend_service import LegendService
from app.services.plan_service import PlanService
from app.services.storage_service import StorageError, StorageService

logger = logging.getLogger(__name__)

__all__ = [
    "DetectionService",
    "ExactlyOneReferenceRequiredError",
    "ReferenceNotConfirmedError",
    "ReferenceFeatureSetRequiredError",
    "ReferenceNotFoundError",
    "ReferenceFeatureVersionOutdatedError",
    "PagePreviewNotAvailableError",
    "DetectionRunNotFoundError",
    "DetectedRegionNotFoundError",
]


class ExactlyOneReferenceRequiredError(Exception):
    def __init__(self):
        super().__init__("Exactly one of legend_entry_id or pattern_library_entry_id must be provided")


class ReferenceNotConfirmedError(Exception):
    def __init__(self, legend_entry_id: uuid.UUID):
        self.legend_entry_id = legend_entry_id
        super().__init__(f"LegendEntry {legend_entry_id} must be confirmed to use as a detection reference")


class ReferenceFeatureSetRequiredError(Exception):
    """Mirrors R5's own FeatureSetRequiredError -- R6 never silently
    computes features either (R6 section 3/9's explicit-computation-only
    discipline continues unbroken from R4/R5)."""

    def __init__(self, detail: str):
        super().__init__(detail)


class ReferenceNotFoundError(Exception):
    def __init__(self, reference_id: uuid.UUID):
        self.reference_id = reference_id
        super().__init__(f"Reference {reference_id} not found in this project")


class ReferenceFeatureVersionOutdatedError(Exception):
    """R7 section 4 -- closes the LOW future-risk the R6 independent
    review flagged: without this guard, a reference HatchFeatureSet
    computed under an old FEATURE_VERSION would still be accepted, every
    tile would then fail combined_similarity's own version-mismatch gate,
    and the run would complete as COMPLETED with zero candidates --
    indistinguishable from "genuinely nothing found on this page". This
    guard raises a clear, explicit domain error before the run ever
    starts, instead. Does not modify the detector algorithm itself, and
    is not a migration/backfill framework -- just a pre-run equality
    check against the one current FEATURE_VERSION constant."""

    error_code = "REFERENCE_FEATURE_VERSION_OUTDATED"

    def __init__(self, reference_feature_version: str, current_feature_version: str):
        self.reference_feature_version = reference_feature_version
        self.current_feature_version = current_feature_version
        super().__init__(
            f"{self.error_code}: reference was computed with feature_version="
            f"'{reference_feature_version}', but the current feature_version is "
            f"'{current_feature_version}'. Recompute features on the reference before running detection."
        )


class PagePreviewNotAvailableError(Exception):
    def __init__(self, detail: str = "This page has no rendered preview to scan"):
        super().__init__(detail)


class DetectionRunNotFoundError(Exception):
    def __init__(self, run_id: uuid.UUID):
        self.run_id = run_id
        super().__init__(f"DetectionRun {run_id} not found")


class DetectedRegionNotFoundError(Exception):
    def __init__(self, region_id: uuid.UUID):
        self.region_id = region_id
        super().__init__(f"DetectedRegion {region_id} not found")


def _decode_image(image_bytes: bytes) -> np.ndarray:
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Page preview could not be decoded as an image")
    return image


class DetectionService:
    def __init__(self, db, storage: StorageService | None = None):
        self._db = db
        self._storage = storage or StorageService()
        self._legend_service = LegendService(db, storage=self._storage)
        self._plan_service = PlanService(db, storage=self._storage)

    # -- reference resolution -------------------------------------------

    def _resolve_reference(
        self,
        project_id: uuid.UUID,
        plan_id: uuid.UUID,
        legend_entry_id: uuid.UUID | None,
        pattern_library_entry_id: uuid.UUID | None,
    ) -> HatchFeatureSet:
        if (legend_entry_id is None) == (pattern_library_entry_id is None):
            raise ExactlyOneReferenceRequiredError()

        if legend_entry_id is not None:
            entry = self._legend_service.get_entry(project_id, plan_id, legend_entry_id)
            if entry.status != LegendEntryStatus.CONFIRMED:
                raise ReferenceNotConfirmedError(legend_entry_id)
            feature_set = self._db.query(HatchFeatureSet).filter_by(legend_entry_id=legend_entry_id).one_or_none()
            if feature_set is None:
                raise ReferenceFeatureSetRequiredError(
                    f"LegendEntry {legend_entry_id} has no computed HatchFeatureSet yet -- "
                    "compute features explicitly before running detection"
                )
            self._require_current_feature_version(feature_set)
            return feature_set

        library_entry = self._db.get(PatternLibraryEntry, pattern_library_entry_id)
        if library_entry is None or library_entry.project_id != project_id:
            raise ReferenceNotFoundError(pattern_library_entry_id)
        feature_set = self._db.get(HatchFeatureSet, library_entry.hatch_feature_set_id)
        if feature_set is None:
            # Defensive only -- a PatternLibraryEntry is never created
            # without a valid hatch_feature_set_id (R5's own add_entry
            # guarantee), so this should not occur in practice.
            raise ReferenceFeatureSetRequiredError(
                f"PatternLibraryEntry {pattern_library_entry_id} has no valid HatchFeatureSet"
            )
        self._require_current_feature_version(feature_set)
        return feature_set

    @staticmethod
    def _require_current_feature_version(feature_set: HatchFeatureSet) -> None:
        """R7 section 4 pre-run guard -- see ReferenceFeatureVersionOutdatedError.
        A plain equality check against the one current FEATURE_VERSION
        constant; not a version-compatibility matrix, not a migration
        framework."""
        if feature_set.feature_version != FEATURE_VERSION:
            raise ReferenceFeatureVersionOutdatedError(feature_set.feature_version, FEATURE_VERSION)

    # -- run execution -----------------------------------------------

    def start_run(
        self,
        project_id: uuid.UUID,
        plan_id: uuid.UUID,
        page_number: int,
        legend_entry_id: uuid.UUID | None = None,
        pattern_library_entry_id: uuid.UUID | None = None,
        tile_size_px: int | None = None,
        stride_px: int | None = None,
        candidate_threshold: float | None = None,
        min_evidence_coverage: float | None = None,
    ) -> DetectionRun:
        """Synchronous, start-to-finish (R6 section 26 -- acceptable for
        this first release; see the benchmark doc for measured
        durations). Explicit PENDING->RUNNING->COMPLETED/FAILED states
        are still recorded even though nothing here actually yields
        control mid-run, so the persisted record always shows a real
        status, not just an implicit "it returned so it must have
        worked." No partial COMPLETED state (R6 section 28): region
        persistence and the COMPLETED status update happen together, and
        any failure before that point rolls back to leave nothing
        half-written, then records FAILED in a fresh transaction."""
        page = self._plan_service.get_page(project_id, plan_id, page_number)
        feature_set = self._resolve_reference(project_id, plan_id, legend_entry_id, pattern_library_entry_id)

        if not page.preview_reference:
            raise PagePreviewNotAvailableError()
        try:
            preview_path = self._storage.resolve_preview(page.preview_reference)
        except StorageError as exc:
            raise PagePreviewNotAvailableError(str(exc)) from exc

        parameters = {
            "tile_size_px": tile_size_px or TILE_SIZE_PX,
            "stride_px": stride_px or TILE_STRIDE_PX,
            "candidate_threshold": candidate_threshold if candidate_threshold is not None else CANDIDATE_SIMILARITY_THRESHOLD,
            "min_evidence_coverage": (
                min_evidence_coverage if min_evidence_coverage is not None else MIN_EVIDENCE_COVERAGE_FOR_CANDIDATE
            ),
        }

        run = DetectionRun(
            project_id=project_id,
            plan_id=plan_id,
            plan_page_id=page.id,
            reference_legend_entry_id=legend_entry_id,
            reference_pattern_library_entry_id=pattern_library_entry_id,
            feature_version=feature_set.feature_version,
            detector_version=DETECTOR_VERSION,
            status=DetectionRunStatus.RUNNING,
            parameters=parameters,
        )
        self._db.add(run)
        self._db.commit()
        self._db.refresh(run)

        start = time.perf_counter()
        try:
            image_bytes = preview_path.read_bytes()
            page_image = _decode_image(image_bytes)
            reference = ComparableFeatures.from_features(feature_set)
            result = run_detection(
                page_image,
                reference,
                tile_size_px=parameters["tile_size_px"],
                stride_px=parameters["stride_px"],
                candidate_threshold=parameters["candidate_threshold"],
                min_evidence_coverage=parameters["min_evidence_coverage"],
            )
        except TooManyTilesError as exc:
            self._db.rollback()
            self._fail_run(run, str(exc))
            return run
        except Exception:
            # Any other extractor/decoding failure -- logged in full
            # server-side, never surfaced to the API caller (R6 sections
            # 27/35's explicit "no raw stack traces").
            logger.exception(
                "detection_run_failed detection_run_id=%s project_id=%s plan_page_id=%s", run.id, project_id, page.id
            )
            self._db.rollback()
            self._fail_run(run, "Detection failed while processing the page image.")
            return run

        for region in result.candidate_regions:
            self._db.add(
                DetectedRegion(
                    detection_run_id=run.id,
                    x=region.x,
                    y=region.y,
                    width=region.width,
                    height=region.height,
                    similarity=region.similarity,
                    evidence_coverage=region.evidence_coverage,
                    tile_count=region.tile_count,
                    status=DetectedRegionStatus.CANDIDATE,
                )
            )

        run.status = DetectionRunStatus.COMPLETED
        run.tile_count = result.tiles_evaluated + result.tiles_skipped
        run.tiles_evaluated = result.tiles_evaluated
        run.tiles_skipped = result.tiles_skipped
        run.candidate_region_count = len(result.candidate_regions)
        run.completed_at = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(run)

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "detection_run_completed detection_run_id=%s project_id=%s plan_page_id=%s detector_version=%s "
            "feature_version=%s reference_id=%s tiles_evaluated=%d tiles_skipped=%d regions=%d duration_ms=%.1f",
            run.id, project_id, page.id, DETECTOR_VERSION, feature_set.feature_version,
            legend_entry_id or pattern_library_entry_id, result.tiles_evaluated, result.tiles_skipped,
            len(result.candidate_regions), duration_ms,
        )
        return run

    def _fail_run(self, run: DetectionRun, error_message: str) -> None:
        # A fresh, minimal update -- deliberately not touching anything
        # else on the row, and committed on its own so a FAILED run is
        # never left as RUNNING forever.
        run.status = DetectionRunStatus.FAILED
        run.error_message = error_message
        run.completed_at = datetime.now(timezone.utc)
        self._db.add(run)
        self._db.commit()
        self._db.refresh(run)
        logger.info(
            "detection_run_failed_recorded detection_run_id=%s project_id=%s error=%s",
            run.id, run.project_id, error_message,
        )

    # -- retrieval -------------------------------------------------------

    def _require_run(self, project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID) -> DetectionRun:
        self._plan_service.get_plan(project_id, plan_id)  # ownership/isolation check
        run = self._db.get(DetectionRun, run_id)
        if run is None or run.project_id != project_id or run.plan_id != plan_id:
            raise DetectionRunNotFoundError(run_id)
        return run

    def get_run(self, project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID) -> DetectionRun:
        return self._require_run(project_id, plan_id, run_id)

    def list_runs_for_page(self, project_id: uuid.UUID, plan_id: uuid.UUID, page_number: int) -> list[DetectionRun]:
        """Lets the frontend rediscover the most recent run for a page
        after a reload (R6 section 24) without needing any client-side
        storage of run IDs -- the DB is the only source of truth."""
        page = self._plan_service.get_page(project_id, plan_id, page_number)
        return (
            self._db.query(DetectionRun)
            .filter_by(plan_page_id=page.id)
            .order_by(DetectionRun.created_at.desc())
            .all()
        )

    def list_regions(self, project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID) -> list[DetectedRegion]:
        run = self._require_run(project_id, plan_id, run_id)
        return (
            self._db.query(DetectedRegion)
            .filter_by(detection_run_id=run.id)
            .order_by(DetectedRegion.similarity.desc())
            .all()
        )

    # -- review --------------------------------------------------------

    def update_region_status(
        self,
        project_id: uuid.UUID,
        plan_id: uuid.UUID,
        run_id: uuid.UUID,
        region_id: uuid.UUID,
        status: DetectedRegionStatus,
    ) -> DetectedRegion:
        run = self._require_run(project_id, plan_id, run_id)
        region = self._db.get(DetectedRegion, region_id)
        if region is None or region.detection_run_id != run.id:
            raise DetectedRegionNotFoundError(region_id)
        region.status = status
        self._db.commit()
        self._db.refresh(region)
        logger.info(
            "detected_region_status_updated detection_run_id=%s region_id=%s status=%s",
            run.id, region.id, status.value,
        )
        return region
