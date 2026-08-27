from __future__ import annotations

import logging
import time
import uuid

import cv2
import numpy as np

from app.hatch.config import FEATURE_VERSION
from app.hatch.feature_extractor import HatchFeatureExtractor
from app.hatch.models import HatchFeatures
from app.hatch.preprocessing import InvalidHatchImageError
from app.models.hatch_feature_set import HatchFeatureSet
from app.models.legend_entry import LegendEntry, LegendEntryStatus
from app.services.legend_service import LegendService
from app.services.storage_service import StorageError, StorageService

logger = logging.getLogger(__name__)

__all__ = [
    "HatchFeatureService",
    "NoPatternCropError",
    "LegendEntryNotConfirmedError",
    "InvalidHatchImageError",
]


class NoPatternCropError(Exception):
    """Raised when the LegendEntry has no pattern crop to extract features
    from at all -- distinct from InvalidHatchImageError, which is for a
    crop that exists but cannot be decoded/analyzed."""

    def __init__(self, legend_entry_id: uuid.UUID):
        self.legend_entry_id = legend_entry_id
        super().__init__(f"LegendEntry {legend_entry_id} has no pattern crop to extract features from")


class LegendEntryNotConfirmedError(Exception):
    """R4 is scoped to *confirmed* LegendEntries only (R4 section 1: "For
    every confirmed LegendEntry with a stored pattern crop") -- matches
    the app's human-in-the-loop principle that only explicitly confirmed
    data is authoritative enough to build derived, persisted analysis on."""

    def __init__(self, legend_entry_id: uuid.UUID):
        self.legend_entry_id = legend_entry_id
        super().__init__(f"LegendEntry {legend_entry_id} is not confirmed yet")


def _decode_image(image_bytes: bytes) -> np.ndarray:
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise InvalidHatchImageError("Pattern crop could not be decoded as an image")
    return image


class HatchFeatureService:
    """Connects a confirmed LegendEntry to the (pure, stateless)
    HatchFeatureExtractor and persists the result. Deliberately does not
    do any Pattern Library search/matching -- that is out of R4's scope
    entirely (see R4 section 20's "Do not mix Pattern Library search here").
    """

    def __init__(self, db, storage: StorageService | None = None, extractor: HatchFeatureExtractor | None = None):
        self._db = db
        self._storage = storage or StorageService()
        self._legend_service = LegendService(db, storage=self._storage)
        self._extractor = extractor or HatchFeatureExtractor()

    def _require_confirmed_entry_with_crop(
        self, project_id: uuid.UUID, plan_id: uuid.UUID, legend_entry_id: uuid.UUID
    ) -> LegendEntry:
        # Reuses LegendService's existing ownership/isolation chain
        # (Project -> Plan -> LegendEntry) -- no duplicated lookup logic.
        entry = self._legend_service.get_entry(project_id, plan_id, legend_entry_id)
        if entry.status != LegendEntryStatus.CONFIRMED:
            raise LegendEntryNotConfirmedError(legend_entry_id)
        if not entry.pattern_image_reference:
            raise NoPatternCropError(legend_entry_id)
        return entry

    def get_features(
        self, project_id: uuid.UUID, plan_id: uuid.UUID, legend_entry_id: uuid.UUID
    ) -> HatchFeatureSet | None:
        # get_entry alone (not the confirmed+crop check) is enough for a
        # plain read -- a GET on a draft entry with no features yet should
        #404 "no features", not "not confirmed", since those are different
        # facts a caller might want to distinguish.
        self._legend_service.get_entry(project_id, plan_id, legend_entry_id)
        return self._db.query(HatchFeatureSet).filter_by(legend_entry_id=legend_entry_id).one_or_none()

    def compute_features(
        self, project_id: uuid.UUID, plan_id: uuid.UUID, legend_entry_id: uuid.UUID, force: bool = False
    ) -> HatchFeatureSet:
        entry = self._require_confirmed_entry_with_crop(project_id, plan_id, legend_entry_id)

        existing = self._db.query(HatchFeatureSet).filter_by(legend_entry_id=legend_entry_id).one_or_none()
        if existing is not None and existing.feature_version == FEATURE_VERSION and not force:
            # No expensive CV work on an ordinary "compute" call that's
            # really just confirming what's already there -- R4 section 21
            # is explicit that recomputation must be an intentional,
            # explicit action, not something that happens silently on
            # every call.
            logger.info(
                "hatch_features_reused legend_entry_id=%s project_id=%s plan_id=%s feature_version=%s",
                legend_entry_id, project_id, plan_id, existing.feature_version,
            )
            return existing

        try:
            crop_path = self._storage.resolve_legend_crop(entry.pattern_image_reference)
        except StorageError as exc:
            # The DB row references a crop, but the file itself is missing
            # from disk (e.g. storage was cleared out-of-band) -- from the
            # caller's perspective this is the same "nothing to extract
            # from" condition as never having selected a pattern at all.
            raise NoPatternCropError(legend_entry_id) from exc
        image_bytes = crop_path.read_bytes()
        image = _decode_image(image_bytes)  # raises InvalidHatchImageError, never a raw cv2 exception

        start = time.perf_counter()
        try:
            features: HatchFeatures = self._extractor.extract(image)
        except InvalidHatchImageError:
            logger.warning(
                "hatch_features_extraction_failed legend_entry_id=%s project_id=%s plan_id=%s",
                legend_entry_id, project_id, plan_id,
            )
            raise
        duration_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "hatch_features_computed legend_entry_id=%s project_id=%s plan_id=%s feature_version=%s "
            "duration_ms=%.1f line_count=%d spacing_available=%s periodicity_available=%s "
            "missing_fields=%s",
            legend_entry_id, project_id, plan_id, features.feature_version, duration_ms,
            features.detected_line_count, features.spacing_available, features.periodicity_available,
            [
                name
                for name, value in (
                    ("normalized_line_spacing", features.normalized_line_spacing),
                    ("normalized_line_width", features.normalized_line_width),
                    ("periodicity", features.periodicity),
                    ("is_cross_hatch", features.is_cross_hatch),
                )
                if value is None
            ],
        )

        if existing is not None:
            row = existing
        else:
            row = HatchFeatureSet(legend_entry_id=legend_entry_id)
            self._db.add(row)

        row.feature_version = features.feature_version
        row.source_width = features.source_width
        row.source_height = features.source_height
        row.dominant_angles = features.dominant_angles
        row.is_cross_hatch = features.is_cross_hatch
        row.normalized_line_spacing = features.normalized_line_spacing
        row.line_density = features.line_density
        row.normalized_line_width = features.normalized_line_width
        row.periodicity = features.periodicity
        row.color_mean_l = features.color_mean_l
        row.color_mean_a = features.color_mean_a
        row.color_mean_b = features.color_mean_b
        row.color_std_l = features.color_std_l
        row.color_std_a = features.color_std_a
        row.color_std_b = features.color_std_b
        row.detected_line_count = features.detected_line_count
        row.angle_evidence_strength = features.angle_evidence_strength
        row.spacing_available = features.spacing_available
        row.periodicity_available = features.periodicity_available

        self._db.commit()
        self._db.refresh(row)
        return row
