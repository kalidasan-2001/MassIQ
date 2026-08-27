"""Integration tests against a real Postgres database (see db_test_support.py).
Requires the docker-compose Postgres service to be running:
    docker compose up -d postgres
"""

from __future__ import annotations

import sys
import tempfile
import unittest
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import cv2

from tests import hatch_fixtures as hfx
from tests import pdf_fixtures as fx
from tests.db_test_support import build_test_engine, new_sessionmaker, truncate_all

from app.hatch.config import FEATURE_VERSION
from app.hatch.preprocessing import InvalidHatchImageError
from app.schemas.legend_entry import LegendEntryUpdate
from app.schemas.project import ProjectCreate
from app.services.hatch_feature_service import (
    HatchFeatureService,
    LegendEntryNotConfirmedError,
    NoPatternCropError,
)
from app.services.legend_crop_service import RegionSelection
from app.services.legend_service import LegendEntryNotFoundError, LegendService
from app.services.ocr_service import OcrResult, OcrService
from app.services.plan_service import PlanService
from app.services.project_service import ProjectService
from app.services.storage_service import StorageService


class _FakeOcrProvider:
    name = "fake"

    def extract_text(self, image_path):
        return OcrResult(text="Stahlbeton C25/30 d=20cm", provider=self.name, confidence=0.9)


def _encode_png(image) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return buffer.tobytes()


class HatchFeatureServiceTestsBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = build_test_engine()
        cls.Session = new_sessionmaker(cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        truncate_all(self.engine)
        self.session = self.Session()
        self._tmp = tempfile.TemporaryDirectory()
        self.storage = StorageService(root=Path(self._tmp.name))
        self.project_service = ProjectService(self.session)
        self.plan_service = PlanService(self.session, storage=self.storage)
        self.legend_service = LegendService(
            self.session, storage=self.storage, ocr=OcrService(provider=_FakeOcrProvider())
        )
        self.feature_service = HatchFeatureService(self.session, storage=self.storage)

        self.project = self.project_service.create_project(ProjectCreate(name="Hatch Feature Test Project"))
        self.plan = self.plan_service.upload_plan(self.project.id, "vector.pdf", fx.build_vector_pdf_bytes())

    def tearDown(self):
        self.session.close()
        self._tmp.cleanup()

    def _confirmed_entry_with_pattern(self, pattern_bytes: bytes | None = None):
        """Builds a fully confirmed LegendEntry, then overwrites its
        pattern crop file with a specific synthetic hatch image -- the
        LegendCropService pipeline always crops from the plan preview PNG,
        which has no real hatch pattern in it, so tests that care about
        the *feature extraction result* substitute a known pattern
        afterwards rather than fighting the crop pipeline."""
        entry = self.legend_service.create_draft(self.project.id, self.plan.id, page_number=1)
        self.legend_service.save_pattern_selection(
            self.project.id, self.plan.id, entry.id, RegionSelection(x=0.05, y=0.05, width=0.2, height=0.1)
        )
        self.legend_service.save_description_selection(
            self.project.id, self.plan.id, entry.id, RegionSelection(x=0.5, y=0.5, width=0.2, height=0.1)
        )
        self.legend_service.update_entry(
            self.project.id, self.plan.id, entry.id,
            LegendEntryUpdate(corrected_text="Stahlbeton C25/30", material_name="Stahlbeton C25/30"),
        )
        confirmed = self.legend_service.confirm(self.project.id, self.plan.id, entry.id)

        if pattern_bytes is not None:
            crop_path = self.storage.resolve_legend_crop(confirmed.pattern_image_reference)
            crop_path.write_bytes(pattern_bytes)
        return confirmed


class OwnershipAndPreconditionTests(HatchFeatureServiceTestsBase):
    def test_unknown_entry_raises_not_found(self):
        with self.assertRaises(LegendEntryNotFoundError):
            self.feature_service.compute_features(self.project.id, self.plan.id, uuid.uuid4())

    def test_draft_entry_raises_not_confirmed(self):
        entry = self.legend_service.create_draft(self.project.id, self.plan.id, page_number=1)
        with self.assertRaises(LegendEntryNotConfirmedError):
            self.feature_service.compute_features(self.project.id, self.plan.id, entry.id)

    def test_confirmed_entry_without_pattern_is_impossible_via_confirm(self):
        """confirm() itself already requires a pattern selection -- this
        documents that HatchFeatureService's own NoPatternCropError path
        is a defense-in-depth check, not the primary gate."""
        entry = self.legend_service.create_draft(self.project.id, self.plan.id, page_number=1)
        from app.services.legend_service import LegendConfirmationError

        with self.assertRaises(LegendConfirmationError):
            self.legend_service.confirm(self.project.id, self.plan.id, entry.id)

    def test_missing_crop_file_on_disk_raises_no_pattern_crop_error(self):
        confirmed = self._confirmed_entry_with_pattern()
        crop_path = self.storage.resolve_legend_crop(confirmed.pattern_image_reference)
        crop_path.unlink()
        with self.assertRaises(NoPatternCropError):
            self.feature_service.compute_features(self.project.id, self.plan.id, confirmed.id)

    def test_corrupt_crop_file_raises_invalid_hatch_image_error(self):
        confirmed = self._confirmed_entry_with_pattern(pattern_bytes=b"not actually a png")
        with self.assertRaises(InvalidHatchImageError):
            self.feature_service.compute_features(self.project.id, self.plan.id, confirmed.id)

    def test_cross_project_access_raises(self):
        confirmed = self._confirmed_entry_with_pattern(pattern_bytes=_encode_png(hfx.family_a_parallel_45()))
        other_project = self.project_service.create_project(ProjectCreate(name="Other"))
        with self.assertRaises(Exception):
            self.feature_service.compute_features(other_project.id, self.plan.id, confirmed.id)


class ComputeAndPersistTests(HatchFeatureServiceTestsBase):
    def test_compute_persists_a_feature_set_matching_the_extractor(self):
        confirmed = self._confirmed_entry_with_pattern(pattern_bytes=_encode_png(hfx.family_d_cross_hatch_45_135()))
        result = self.feature_service.compute_features(self.project.id, self.plan.id, confirmed.id)
        self.assertEqual(result.legend_entry_id, confirmed.id)
        self.assertEqual(result.feature_version, FEATURE_VERSION)
        self.assertTrue(result.is_cross_hatch)
        self.assertEqual(len(result.dominant_angles), 2)

    def test_get_features_before_compute_returns_none(self):
        confirmed = self._confirmed_entry_with_pattern(pattern_bytes=_encode_png(hfx.family_a_parallel_45()))
        self.assertIsNone(self.feature_service.get_features(self.project.id, self.plan.id, confirmed.id))

    def test_get_features_after_compute_returns_the_persisted_row(self):
        confirmed = self._confirmed_entry_with_pattern(pattern_bytes=_encode_png(hfx.family_a_parallel_45()))
        self.feature_service.compute_features(self.project.id, self.plan.id, confirmed.id)
        fetched = self.feature_service.get_features(self.project.id, self.plan.id, confirmed.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.legend_entry_id, confirmed.id)

    def test_get_features_never_triggers_computation(self):
        """A plain GET must never perform CV work -- unlike compute_features,
        get_features has no `force`/extraction path at all."""
        confirmed = self._confirmed_entry_with_pattern(pattern_bytes=_encode_png(hfx.family_a_parallel_45()))
        self.assertIsNone(self.feature_service.get_features(self.project.id, self.plan.id, confirmed.id))
        # Still None after a second read -- nothing was silently computed.
        self.assertIsNone(self.feature_service.get_features(self.project.id, self.plan.id, confirmed.id))

    def test_persists_across_a_brand_new_engine_and_session(self):
        confirmed = self._confirmed_entry_with_pattern(pattern_bytes=_encode_png(hfx.family_b_parallel_90()))
        self.feature_service.compute_features(self.project.id, self.plan.id, confirmed.id)

        fresh_session = self.Session()
        try:
            fresh_service = HatchFeatureService(fresh_session, storage=self.storage)
            fetched = fresh_service.get_features(self.project.id, self.plan.id, confirmed.id)
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched.feature_version, FEATURE_VERSION)
        finally:
            fresh_session.close()


class RecomputationPolicyTests(HatchFeatureServiceTestsBase):
    def test_second_compute_without_force_returns_existing_row_unchanged(self):
        confirmed = self._confirmed_entry_with_pattern(pattern_bytes=_encode_png(hfx.family_a_parallel_45()))
        first = self.feature_service.compute_features(self.project.id, self.plan.id, confirmed.id)

        # Swap the crop for a totally different pattern -- if the second
        # call actually recomputed, the result would change.
        crop_path = self.storage.resolve_legend_crop(confirmed.pattern_image_reference)
        crop_path.write_bytes(_encode_png(hfx.family_d_cross_hatch_45_135()))

        second = self.feature_service.compute_features(self.project.id, self.plan.id, confirmed.id, force=False)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.dominant_angles, second.dominant_angles)
        self.assertFalse(second.is_cross_hatch)  # still the original family A result

    def test_force_true_recomputes_from_the_current_crop(self):
        confirmed = self._confirmed_entry_with_pattern(pattern_bytes=_encode_png(hfx.family_a_parallel_45()))
        first = self.feature_service.compute_features(self.project.id, self.plan.id, confirmed.id)

        crop_path = self.storage.resolve_legend_crop(confirmed.pattern_image_reference)
        crop_path.write_bytes(_encode_png(hfx.family_d_cross_hatch_45_135()))

        second = self.feature_service.compute_features(self.project.id, self.plan.id, confirmed.id, force=True)
        self.assertEqual(first.id, second.id)  # same row, updated in place
        self.assertTrue(second.is_cross_hatch)
        self.assertEqual(len(second.dominant_angles), 2)


if __name__ == "__main__":
    unittest.main()
