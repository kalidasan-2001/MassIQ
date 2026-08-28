"""Integration tests against a real Postgres database (see db_test_support.py).

Covers R7 section 30's full "Quantity" list plus the release-critical
human-authority rule (R7 section 3): CANDIDATE and REJECTED regions must
contribute ZERO area, only ACCEPTED regions and manual corrections ever
participate, and similarity score must never influence this.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
import uuid
from pathlib import Path

import cv2
import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests import hatch_fixtures as hfx
from tests import pdf_fixtures as fx
from tests.db_test_support import build_test_engine, new_sessionmaker, truncate_all

from app.geometry.config import CALCULATION_VERSION
from app.geometry.service import NormalizedRect
from app.models.detected_region import DetectedRegion, DetectedRegionStatus
from app.models.manual_region_correction import ManualCorrectionType
from app.models.quantity_result import QuantityResultStatus
from app.schemas.legend_entry import LegendEntryUpdate
from app.schemas.project import ProjectCreate
from app.services.detection_service import DetectionRunNotFoundError, DetectionService
from app.services.legend_crop_service import RegionSelection
from app.services.legend_service import LegendService
from app.services.manual_correction_service import ManualCorrectionService
from app.services.ocr_service import OcrResult, OcrService
from app.services.plan_scale_service import PlanScaleService
from app.services.plan_service import PlanService
from app.services.project_service import ProjectService
from app.services.quantity_service import (
    InvalidDimensionError,
    QuantityResultNotFoundError,
    QuantityService,
    ScaleNotConfirmedError,
)
from app.services.storage_service import StorageService


class _FakeOcrProvider:
    name = "fake"

    def extract_text(self, image_path):
        return OcrResult(text="Stahlbeton C25/30", provider=self.name, confidence=0.9)


class QuantityServiceTests(unittest.TestCase):
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
        self.legend_service = LegendService(self.session, storage=self.storage, ocr=OcrService(provider=_FakeOcrProvider()))
        self.detection_service = DetectionService(self.session, storage=self.storage)
        self.correction_service = ManualCorrectionService(self.session, storage=self.storage)
        self.scale_service = PlanScaleService(self.session, storage=self.storage)
        self.quantity_service = QuantityService(self.session, storage=self.storage)

        self.project = self.project_service.create_project(ProjectCreate(name="Quantity Test Project"))
        self.plan = self.plan_service.upload_plan(self.project.id, "vector.pdf", fx.build_vector_pdf_bytes())
        self.run = self._make_completed_run()

    def tearDown(self):
        self.session.close()
        self._tmp.cleanup()

    def _make_completed_run(self):
        from app.services.hatch_feature_service import HatchFeatureService

        entry = self.legend_service.create_draft(self.project.id, self.plan.id, page_number=1)
        entry = self.legend_service.save_pattern_selection(
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

        feature_service = HatchFeatureService(self.session, storage=self.storage)
        crop_path = self.storage.resolve_legend_crop(confirmed.pattern_image_reference)
        ok, buffer = cv2.imencode(".png", hfx.family_a_parallel_45())
        assert ok
        crop_path.write_bytes(buffer.tobytes())
        feature_service.compute_features(self.project.id, self.plan.id, confirmed.id)

        page = self.plan_service.get_page(self.project.id, self.plan.id, 1)
        preview_path = self.storage.resolve_preview(page.preview_reference)
        blank = np.full((700, 900, 3), 255, dtype=np.uint8)
        ok, buffer = cv2.imencode(".png", blank)
        assert ok
        preview_path.write_bytes(buffer.tobytes())

        self.page = page
        return self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=confirmed.id)

    def _add_region(self, status: DetectedRegionStatus, x=0.0, y=0.0, w=0.1, h=0.1, similarity=0.9) -> DetectedRegion:
        """Direct row insertion, deliberately bypassing the CV pipeline --
        QuantityService only cares about persisted status/geometry, and
        controlling both exactly is what lets these tests assert precise
        expected numbers (mirrors R6's own established test precedent of
        substituting known content after the real scaffolding exists)."""
        region = DetectedRegion(
            detection_run_id=self.run.id, x=x, y=y, width=w, height=h,
            similarity=similarity, evidence_coverage=0.9, tile_count=1, status=status,
        )
        self.session.add(region)
        self.session.commit()
        self.session.refresh(region)
        return region

    def _confirm_simple_scale(self):
        # 1 point == 1 meter, for simple hand-checkable expected numbers.
        return self.scale_service.confirm_calibrated_distance(
            self.project.id, self.plan.id, 1, calibrated_distance_plan_points=1.0, calibrated_distance_real_m=1.0
        )

    # -- Review authority (release-critical, R7 section 3) ----------------

    def test_candidate_region_contributes_zero_area(self):
        self._confirm_simple_scale()
        self._add_region(DetectedRegionStatus.CANDIDATE, x=0, y=0, w=0.1, h=0.1)
        result = self.quantity_service.calculate(self.project.id, self.plan.id, self.run.id, confirmed_dimension_m=2.0)
        self.assertEqual(result.final_area_m2, 0.0)
        self.assertEqual(result.volume_m3, 0.0)
        self.assertEqual(result.accepted_region_count, 0)

    def test_rejected_region_contributes_zero_area(self):
        self._confirm_simple_scale()
        self._add_region(DetectedRegionStatus.REJECTED, x=0, y=0, w=0.1, h=0.1, similarity=0.99)
        result = self.quantity_service.calculate(self.project.id, self.plan.id, self.run.id, confirmed_dimension_m=2.0)
        self.assertEqual(result.final_area_m2, 0.0)

    def test_accepted_region_contributes_regardless_of_similarity(self):
        self._confirm_simple_scale()
        # A LOW similarity accepted region must still fully contribute --
        # similarity must never gate/scale participation once a human has
        # explicitly accepted it.
        self._add_region(DetectedRegionStatus.ACCEPTED, x=0, y=0, w=0.1, h=0.1, similarity=0.01)
        page_area_width = self.page.width * 0.1
        page_area_height = self.page.height * 0.1
        expected_area = page_area_width * page_area_height  # scale = 1 point/meter
        result = self.quantity_service.calculate(self.project.id, self.plan.id, self.run.id, confirmed_dimension_m=1.0)
        self.assertAlmostEqual(result.final_area_m2, expected_area, places=6)
        self.assertEqual(result.accepted_region_count, 1)

    def test_mixed_statuses_only_accepted_counts(self):
        self._confirm_simple_scale()
        self._add_region(DetectedRegionStatus.CANDIDATE, x=0.5, y=0.5, w=0.1, h=0.1)
        self._add_region(DetectedRegionStatus.REJECTED, x=0.6, y=0.5, w=0.1, h=0.1)
        accepted = self._add_region(DetectedRegionStatus.ACCEPTED, x=0, y=0, w=0.1, h=0.1)
        result = self.quantity_service.calculate(self.project.id, self.plan.id, self.run.id, confirmed_dimension_m=1.0)
        expected_area = (accepted.width * self.page.width) * (accepted.height * self.page.height)
        self.assertAlmostEqual(result.final_area_m2, expected_area, places=6)
        self.assertEqual(result.accepted_region_count, 1)

    # -- Manual corrections integration ------------------------------------

    def test_manual_add_and_subtract_are_included(self):
        self._confirm_simple_scale()
        self._add_region(DetectedRegionStatus.ACCEPTED, x=0, y=0, w=0.2, h=0.2)
        self.correction_service.create_correction(
            self.project.id, self.plan.id, self.run.id, ManualCorrectionType.ADD, NormalizedRect(0.3, 0, 0.1, 0.1)
        )
        self.correction_service.create_correction(
            self.project.id, self.plan.id, self.run.id, ManualCorrectionType.SUBTRACT, NormalizedRect(0, 0, 0.05, 0.05)
        )
        result = self.quantity_service.calculate(self.project.id, self.plan.id, self.run.id, confirmed_dimension_m=1.0)
        self.assertEqual(result.manual_add_count, 1)
        self.assertEqual(result.manual_subtract_count, 1)
        self.assertGreater(result.final_area_m2, 0.0)

    # -- Zero/negative behavior (R7 section 22) ----------------------------

    def test_no_positive_geometry_yields_zero_area_and_volume(self):
        self._confirm_simple_scale()
        result = self.quantity_service.calculate(self.project.id, self.plan.id, self.run.id, confirmed_dimension_m=3.0)
        self.assertEqual(result.final_area_m2, 0.0)
        self.assertEqual(result.volume_m3, 0.0)

    def test_subtraction_larger_than_positive_never_negative(self):
        self._confirm_simple_scale()
        self._add_region(DetectedRegionStatus.ACCEPTED, x=0, y=0, w=0.1, h=0.1)
        self.correction_service.create_correction(
            self.project.id, self.plan.id, self.run.id, ManualCorrectionType.SUBTRACT, NormalizedRect(0, 0, 1.0, 1.0)
        )
        result = self.quantity_service.calculate(self.project.id, self.plan.id, self.run.id, confirmed_dimension_m=1.0)
        self.assertEqual(result.final_area_m2, 0.0)
        self.assertGreaterEqual(result.final_area_m2, 0.0)

    # -- Dimension validation -----------------------------------------------

    def test_invalid_dimension_rejected(self):
        self._confirm_simple_scale()
        self._add_region(DetectedRegionStatus.ACCEPTED, x=0, y=0, w=0.1, h=0.1)
        for bad in (0, -1, float("nan"), float("inf"), None):
            with self.assertRaises(InvalidDimensionError):
                self.quantity_service.calculate(self.project.id, self.plan.id, self.run.id, confirmed_dimension_m=bad)

    # -- Scale precondition (R7 section 49) ---------------------------------

    def test_calculate_without_confirmed_scale_raises(self):
        self._add_region(DetectedRegionStatus.ACCEPTED, x=0, y=0, w=0.1, h=0.1)
        with self.assertRaises(ScaleNotConfirmedError):
            self.quantity_service.calculate(self.project.id, self.plan.id, self.run.id, confirmed_dimension_m=1.0)

    # -- Idempotence (R7 section 21) -----------------------------------------

    def test_repeated_calculation_updates_same_row_not_a_duplicate(self):
        self._confirm_simple_scale()
        self._add_region(DetectedRegionStatus.ACCEPTED, x=0, y=0, w=0.1, h=0.1)
        first = self.quantity_service.calculate(self.project.id, self.plan.id, self.run.id, confirmed_dimension_m=2.0)
        second = self.quantity_service.calculate(self.project.id, self.plan.id, self.run.id, confirmed_dimension_m=2.0)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.final_area_m2, second.final_area_m2)
        self.assertEqual(first.volume_m3, second.volume_m3)

    def test_same_state_produces_deterministic_result(self):
        self._confirm_simple_scale()
        self._add_region(DetectedRegionStatus.ACCEPTED, x=0.1, y=0.1, w=0.15, h=0.25)
        results = [
            self.quantity_service.calculate(self.project.id, self.plan.id, self.run.id, confirmed_dimension_m=1.5)
            for _ in range(3)
        ]
        areas = {r.final_area_m2 for r in results}
        volumes = {r.volume_m3 for r in results}
        self.assertEqual(len(areas), 1)
        self.assertEqual(len(volumes), 1)

    def test_recalculation_resets_confirmed_status(self):
        self._confirm_simple_scale()
        self._add_region(DetectedRegionStatus.ACCEPTED, x=0, y=0, w=0.1, h=0.1)
        result = self.quantity_service.calculate(self.project.id, self.plan.id, self.run.id, confirmed_dimension_m=2.0)
        confirmed = self.quantity_service.confirm(self.project.id, self.plan.id, self.run.id)
        self.assertEqual(confirmed.status, QuantityResultStatus.CONFIRMED)
        self.assertIsNotNone(confirmed.confirmed_at)

        recalculated = self.quantity_service.calculate(
            self.project.id, self.plan.id, self.run.id, confirmed_dimension_m=3.0
        )
        self.assertEqual(recalculated.status, QuantityResultStatus.DRAFT)
        self.assertIsNone(recalculated.confirmed_at)

    # -- Calculation version (R7 section 19) ---------------------------------

    def test_calculation_version_is_recorded(self):
        self._confirm_simple_scale()
        self._add_region(DetectedRegionStatus.ACCEPTED, x=0, y=0, w=0.1, h=0.1)
        result = self.quantity_service.calculate(self.project.id, self.plan.id, self.run.id, confirmed_dimension_m=1.0)
        self.assertEqual(result.calculation_version, CALCULATION_VERSION)

    # -- Retrieval / ownership ------------------------------------------------

    def test_get_result_before_calculation_raises(self):
        with self.assertRaises(QuantityResultNotFoundError):
            self.quantity_service.get_result(self.project.id, self.plan.id, self.run.id)

    def test_confirm_before_calculation_raises(self):
        with self.assertRaises(QuantityResultNotFoundError):
            self.quantity_service.confirm(self.project.id, self.plan.id, self.run.id)

    def test_unknown_run_raises(self):
        with self.assertRaises(DetectionRunNotFoundError):
            self.quantity_service.calculate(self.project.id, self.plan.id, uuid.uuid4(), confirmed_dimension_m=1.0)

    def test_cross_project_run_access_raises(self):
        other_project = self.project_service.create_project(ProjectCreate(name="Other"))
        other_plan = self.plan_service.upload_plan(other_project.id, "b.pdf", fx.build_vector_pdf_bytes())
        with self.assertRaises(DetectionRunNotFoundError):
            self.quantity_service.calculate(other_project.id, other_plan.id, self.run.id, confirmed_dimension_m=1.0)

    def test_result_persists_across_a_fresh_session(self):
        self._confirm_simple_scale()
        self._add_region(DetectedRegionStatus.ACCEPTED, x=0, y=0, w=0.1, h=0.1)
        original = self.quantity_service.calculate(self.project.id, self.plan.id, self.run.id, confirmed_dimension_m=2.0)
        fresh_session = self.Session()
        try:
            fresh_service = QuantityService(fresh_session, storage=self.storage)
            fetched = fresh_service.get_result(self.project.id, self.plan.id, self.run.id)
            self.assertEqual(fetched.id, original.id)
            self.assertEqual(fetched.final_area_m2, original.final_area_m2)
        finally:
            fresh_session.close()


if __name__ == "__main__":
    unittest.main()
