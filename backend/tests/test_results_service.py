"""Integration tests against a real Postgres database (see db_test_support.py)."""

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

from app.models.detected_region import DetectedRegion, DetectedRegionStatus
from app.models.quantity_result import QuantityResultStatus
from app.schemas.legend_entry import LegendEntryUpdate
from app.schemas.project import ProjectCreate
from app.services.detection_service import DetectionService
from app.services.hatch_feature_service import HatchFeatureService
from app.services.legend_crop_service import RegionSelection
from app.services.legend_service import LegendService
from app.services.ocr_service import OcrResult, OcrService
from app.services.pattern_library_service import PatternLibraryService
from app.services.plan_scale_service import PlanScaleService
from app.services.plan_service import PlanService
from app.services.project_service import ProjectService
from app.services.quantity_service import QuantityService
from app.services.results_service import ResultNotFoundError, ResultsService
from app.services.storage_service import StorageService


class _FakeOcrProvider:
    name = "fake"

    def extract_text(self, image_path):
        return OcrResult(text="Stahlbeton C25/30", provider=self.name, confidence=0.9)


def _encode_png(image) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return buffer.tobytes()


class ResultsServiceTests(unittest.TestCase):
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
        self.feature_service = HatchFeatureService(self.session, storage=self.storage)
        self.library_service = PatternLibraryService(self.session, storage=self.storage)
        self.detection_service = DetectionService(self.session, storage=self.storage)
        self.scale_service = PlanScaleService(self.session, storage=self.storage)
        self.quantity_service = QuantityService(self.session, storage=self.storage)
        self.results_service = ResultsService(self.session)

        self.project = self.project_service.create_project(ProjectCreate(name="Results Test Project"))
        self.plan = self.plan_service.upload_plan(self.project.id, "vector.pdf", fx.build_vector_pdf_bytes())

    def tearDown(self):
        self.session.close()
        self._tmp.cleanup()

    def _confirmed_quantity_result(self, material_name="Stahlbeton C25/30", area_w=0.1, area_h=0.1, dimension_m=2.0):
        entry = self.legend_service.create_draft(self.project.id, self.plan.id, page_number=1)
        entry = self.legend_service.save_pattern_selection(
            self.project.id, self.plan.id, entry.id, RegionSelection(x=0.05, y=0.05, width=0.2, height=0.1)
        )
        self.legend_service.save_description_selection(
            self.project.id, self.plan.id, entry.id, RegionSelection(x=0.5, y=0.5, width=0.2, height=0.1)
        )
        self.legend_service.update_entry(
            self.project.id, self.plan.id, entry.id,
            LegendEntryUpdate(corrected_text=f"{material_name} label", material_name=material_name),
        )
        confirmed = self.legend_service.confirm(self.project.id, self.plan.id, entry.id)

        crop_path = self.storage.resolve_legend_crop(confirmed.pattern_image_reference)
        crop_path.write_bytes(_encode_png(hfx.family_a_parallel_45()))
        self.feature_service.compute_features(self.project.id, self.plan.id, confirmed.id)

        page = self.plan_service.get_page(self.project.id, self.plan.id, 1)
        preview_path = self.storage.resolve_preview(page.preview_reference)
        preview_path.write_bytes(_encode_png(np.full((700, 900, 3), 255, dtype=np.uint8)))

        run = self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=confirmed.id)

        self.session.add(
            DetectedRegion(
                detection_run_id=run.id, x=0, y=0, width=area_w, height=area_h,
                similarity=0.9, evidence_coverage=0.9, tile_count=1, status=DetectedRegionStatus.ACCEPTED,
            )
        )
        self.session.add(
            DetectedRegion(
                detection_run_id=run.id, x=0.5, y=0.5, width=0.05, height=0.05,
                similarity=0.5, evidence_coverage=0.5, tile_count=1, status=DetectedRegionStatus.REJECTED,
            )
        )
        self.session.commit()

        self.scale_service.confirm_calibrated_distance(
            self.project.id, self.plan.id, 1, calibrated_distance_plan_points=1.0, calibrated_distance_real_m=1.0
        )
        result = self.quantity_service.calculate(self.project.id, self.plan.id, run.id, confirmed_dimension_m=dimension_m)
        confirmed_result = self.quantity_service.confirm(self.project.id, self.plan.id, run.id)
        return confirmed_result, run, page

    # -- Material provenance (R8 section 7) --------------------------------

    def test_material_resolved_from_legend_entry_reference(self):
        result, run, page = self._confirmed_quantity_result(material_name="Stahlbeton C25/30")
        row = self.results_service.get_result(self.project.id, result.id)
        self.assertEqual(row.material_name, "Stahlbeton C25/30")
        self.assertEqual(row.reference_type, "legend_entry")
        self.assertEqual(row.reference_id, run.reference_legend_entry_id)

    def test_material_resolved_from_pattern_library_entry_reference(self):
        entry = self.legend_service.create_draft(self.project.id, self.plan.id, page_number=1)
        entry = self.legend_service.save_pattern_selection(
            self.project.id, self.plan.id, entry.id, RegionSelection(x=0.05, y=0.05, width=0.2, height=0.1)
        )
        self.legend_service.save_description_selection(
            self.project.id, self.plan.id, entry.id, RegionSelection(x=0.5, y=0.5, width=0.2, height=0.1)
        )
        self.legend_service.update_entry(
            self.project.id, self.plan.id, entry.id,
            LegendEntryUpdate(corrected_text="Library Concrete", material_name="Library Concrete", material_code="LC-1"),
        )
        confirmed_entry = self.legend_service.confirm(self.project.id, self.plan.id, entry.id)
        crop_path = self.storage.resolve_legend_crop(confirmed_entry.pattern_image_reference)
        crop_path.write_bytes(_encode_png(hfx.family_a_parallel_45()))
        self.feature_service.compute_features(self.project.id, self.plan.id, confirmed_entry.id)
        library_entry = self.library_service.add_entry(self.project.id, self.plan.id, confirmed_entry.id)

        page = self.plan_service.get_page(self.project.id, self.plan.id, 1)
        preview_path = self.storage.resolve_preview(page.preview_reference)
        preview_path.write_bytes(_encode_png(np.full((700, 900, 3), 255, dtype=np.uint8)))

        run = self.detection_service.start_run(self.project.id, self.plan.id, 1, pattern_library_entry_id=library_entry.id)
        self.session.add(
            DetectedRegion(
                detection_run_id=run.id, x=0, y=0, width=0.1, height=0.1,
                similarity=0.9, evidence_coverage=0.9, tile_count=1, status=DetectedRegionStatus.ACCEPTED,
            )
        )
        self.session.commit()
        self.scale_service.confirm_calibrated_distance(
            self.project.id, self.plan.id, 1, calibrated_distance_plan_points=1.0, calibrated_distance_real_m=1.0
        )
        result = self.quantity_service.calculate(self.project.id, self.plan.id, run.id, confirmed_dimension_m=1.0)

        row = self.results_service.get_result(self.project.id, result.id)
        self.assertEqual(row.material_name, "Library Concrete")
        self.assertEqual(row.material_code, "LC-1")
        self.assertEqual(row.reference_type, "pattern_library_entry")
        self.assertEqual(row.reference_id, library_entry.id)

    # -- Result row content --------------------------------------------

    def test_result_row_contains_expected_fields(self):
        result, run, page = self._confirmed_quantity_result(dimension_m=2.5)
        row = self.results_service.get_result(self.project.id, result.id)
        self.assertEqual(row.status, QuantityResultStatus.CONFIRMED)
        self.assertEqual(row.confirmed_dimension_m, 2.5)
        self.assertEqual(row.plan_id, self.plan.id)
        self.assertEqual(row.page_number, 1)
        self.assertEqual(row.accepted_region_count, 1)
        self.assertEqual(row.rejected_region_count, 1)  # computed on the fly, not stored
        self.assertEqual(row.calculation_version, result.calculation_version)
        self.assertIsNotNone(row.scale_method)
        self.assertGreater(row.area_m2, 0)
        self.assertAlmostEqual(row.volume_m3, row.area_m2 * 2.5, places=6)

    def test_no_internal_filesystem_path_exposed(self):
        result, run, page = self._confirmed_quantity_result()
        row = self.results_service.get_result(self.project.id, result.id)
        row_text = str(row)
        self.assertNotIn(str(self._tmp.name), row_text)
        self.assertNotIn(".png", row_text)

    # -- Ordering (R8 section 10) ----------------------------------------

    def test_deterministic_ordering_repeated_calls_match(self):
        self._confirmed_quantity_result(material_name="Zebra Material")
        self._confirmed_quantity_result(material_name="Alpha Material")
        first = [r.quantity_result_id for r in self.results_service.list_results(self.project.id)]
        second = [r.quantity_result_id for r in self.results_service.list_results(self.project.id)]
        self.assertEqual(first, second)
        # Material name ordering: Alpha before Zebra.
        rows = self.results_service.list_results(self.project.id)
        names = [r.material_name for r in rows]
        self.assertEqual(names, sorted(names))

    # -- Status filtering --------------------------------------------------

    def test_list_results_includes_draft_by_default(self):
        entry = self.legend_service.create_draft(self.project.id, self.plan.id, page_number=1)
        entry = self.legend_service.save_pattern_selection(
            self.project.id, self.plan.id, entry.id, RegionSelection(x=0.05, y=0.05, width=0.2, height=0.1)
        )
        self.legend_service.save_description_selection(
            self.project.id, self.plan.id, entry.id, RegionSelection(x=0.5, y=0.5, width=0.2, height=0.1)
        )
        self.legend_service.update_entry(
            self.project.id, self.plan.id, entry.id,
            LegendEntryUpdate(corrected_text="Draft Material", material_name="Draft Material"),
        )
        confirmed_entry = self.legend_service.confirm(self.project.id, self.plan.id, entry.id)
        crop_path = self.storage.resolve_legend_crop(confirmed_entry.pattern_image_reference)
        crop_path.write_bytes(_encode_png(hfx.family_a_parallel_45()))
        self.feature_service.compute_features(self.project.id, self.plan.id, confirmed_entry.id)
        page = self.plan_service.get_page(self.project.id, self.plan.id, 1)
        preview_path = self.storage.resolve_preview(page.preview_reference)
        preview_path.write_bytes(_encode_png(np.full((700, 900, 3), 255, dtype=np.uint8)))
        run = self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=confirmed_entry.id)
        self.session.add(
            DetectedRegion(
                detection_run_id=run.id, x=0, y=0, width=0.1, height=0.1,
                similarity=0.9, evidence_coverage=0.9, tile_count=1, status=DetectedRegionStatus.ACCEPTED,
            )
        )
        self.session.commit()
        self.scale_service.confirm_calibrated_distance(
            self.project.id, self.plan.id, 1, calibrated_distance_plan_points=1.0, calibrated_distance_real_m=1.0
        )
        self.quantity_service.calculate(self.project.id, self.plan.id, run.id, confirmed_dimension_m=1.0)
        # Deliberately NOT confirmed.

        all_rows = self.results_service.list_results(self.project.id)
        self.assertEqual(len(all_rows), 1)
        self.assertEqual(all_rows[0].status, QuantityResultStatus.DRAFT)

        confirmed_only = self.results_service.list_results(self.project.id, status=QuantityResultStatus.CONFIRMED)
        self.assertEqual(confirmed_only, [])

    # -- Empty results ------------------------------------------------------

    def test_empty_project_returns_empty_list_not_an_error(self):
        rows = self.results_service.list_results(self.project.id)
        self.assertEqual(rows, [])

    # -- Ownership isolation -------------------------------------------------

    def test_unknown_project_raises(self):
        from app.services.project_service import ProjectNotFoundError

        with self.assertRaises(ProjectNotFoundError):
            self.results_service.list_results(uuid.uuid4())

    def test_cross_project_result_access_raises(self):
        result, _run, _page = self._confirmed_quantity_result()
        other_project = self.project_service.create_project(ProjectCreate(name="Other"))
        with self.assertRaises(ResultNotFoundError):
            self.results_service.get_result(other_project.id, result.id)

    def test_unknown_result_raises(self):
        with self.assertRaises(ResultNotFoundError):
            self.results_service.get_result(self.project.id, uuid.uuid4())


if __name__ == "__main__":
    unittest.main()
