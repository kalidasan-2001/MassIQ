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

import cv2
import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests import detection_fixtures as df
from tests import hatch_fixtures as hfx
from tests import pdf_fixtures as fx
from tests.db_test_support import build_test_engine, new_sessionmaker, truncate_all

from app.models.detected_region import DetectedRegionStatus
from app.models.detection_run import DetectionRunStatus
from app.models.hatch_feature_set import HatchFeatureSet
from app.schemas.legend_entry import LegendEntryUpdate
from app.schemas.project import ProjectCreate
from app.services.detection_service import (
    DetectedRegionNotFoundError,
    DetectionRunNotFoundError,
    DetectionService,
    ExactlyOneReferenceRequiredError,
    PagePreviewNotAvailableError,
    ReferenceFeatureSetRequiredError,
    ReferenceFeatureVersionOutdatedError,
    ReferenceNotConfirmedError,
    ReferenceNotFoundError,
)
from app.services.hatch_feature_service import HatchFeatureService
from app.services.legend_crop_service import RegionSelection
from app.services.legend_service import LegendEntryNotFoundError, LegendService
from app.services.ocr_service import OcrResult, OcrService
from app.services.pattern_library_service import PatternLibraryService
from app.services.plan_service import PlanPageNotFoundError, PlanService
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


class DetectionServiceTestsBase(unittest.TestCase):
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
        self.library_service = PatternLibraryService(self.session, storage=self.storage)
        self.detection_service = DetectionService(self.session, storage=self.storage)

        self.project = self.project_service.create_project(ProjectCreate(name="Detection Test Project"))
        self.plan = self.plan_service.upload_plan(self.project.id, "vector.pdf", fx.build_vector_pdf_bytes())

    def tearDown(self):
        self.session.close()
        self._tmp.cleanup()

    def _confirmed_reference_entry(self, pattern_image=None, material_name="Stahlbeton C25/30"):
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
        if pattern_image is not None:
            crop_path = self.storage.resolve_legend_crop(confirmed.pattern_image_reference)
            crop_path.write_bytes(_encode_png(pattern_image))
            self.feature_service.compute_features(self.project.id, self.plan.id, confirmed.id)
        return confirmed

    def _set_page_preview(self, page_image: np.ndarray):
        """Overwrites the plan page's own rendered preview with a
        synthetic detection-benchmark page image, mirroring the
        established R4/R5 pattern of substituting a known-content image
        after the normal upload/render pipeline creates the file."""
        page = self.plan_service.get_page(self.project.id, self.plan.id, 1)
        preview_path = self.storage.resolve_preview(page.preview_reference)
        preview_path.write_bytes(_encode_png(page_image))


class StartRunValidationTests(DetectionServiceTestsBase):
    def test_neither_reference_provided_raises(self):
        with self.assertRaises(ExactlyOneReferenceRequiredError):
            self.detection_service.start_run(self.project.id, self.plan.id, 1)

    def test_both_references_provided_raises(self):
        with self.assertRaises(ExactlyOneReferenceRequiredError):
            self.detection_service.start_run(
                self.project.id, self.plan.id, 1,
                legend_entry_id=uuid.uuid4(), pattern_library_entry_id=uuid.uuid4(),
            )

    def test_unconfirmed_legend_entry_reference_raises(self):
        entry = self.legend_service.create_draft(self.project.id, self.plan.id, page_number=1)
        with self.assertRaises(ReferenceNotConfirmedError):
            self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=entry.id)

    def test_confirmed_entry_without_features_raises(self):
        entry = self._confirmed_reference_entry(pattern_image=None)
        with self.assertRaises(ReferenceFeatureSetRequiredError):
            self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=entry.id)

    def test_unknown_legend_entry_raises_not_found(self):
        with self.assertRaises(LegendEntryNotFoundError):
            self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=uuid.uuid4())

    def test_outdated_feature_version_reference_raises_clear_error(self):
        """R7 section 4 -- closes the LOW future-risk the R6 independent
        review flagged: an outdated reference must raise a clear,
        explicit domain error before the run starts, not silently
        complete with zero candidates indistinguishable from 'nothing
        found'."""
        entry = self._confirmed_reference_entry(hfx.family_a_parallel_45())
        feature_set = self.session.query(HatchFeatureSet).filter_by(legend_entry_id=entry.id).one()
        feature_set.feature_version = "0.9-outdated"
        self.session.commit()

        with self.assertRaises(ReferenceFeatureVersionOutdatedError) as ctx:
            self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=entry.id)
        self.assertEqual(ctx.exception.error_code, "REFERENCE_FEATURE_VERSION_OUTDATED")
        self.assertIn("REFERENCE_FEATURE_VERSION_OUTDATED", str(ctx.exception))

    def test_unknown_pattern_library_entry_raises(self):
        entry = self._confirmed_reference_entry(hfx.family_a_parallel_45())
        with self.assertRaises(ReferenceNotFoundError):
            self.detection_service.start_run(
                self.project.id, self.plan.id, 1, pattern_library_entry_id=uuid.uuid4()
            )

    def test_invalid_page_number_raises(self):
        entry = self._confirmed_reference_entry(hfx.family_a_parallel_45())
        with self.assertRaises(PlanPageNotFoundError):
            self.detection_service.start_run(self.project.id, self.plan.id, 99, legend_entry_id=entry.id)

    def test_cross_project_reference_raises(self):
        entry = self._confirmed_reference_entry(hfx.family_a_parallel_45())
        other_project = self.project_service.create_project(ProjectCreate(name="Other"))
        with self.assertRaises(Exception):
            self.detection_service.start_run(other_project.id, self.plan.id, 1, legend_entry_id=entry.id)


class RunExecutionTests(DetectionServiceTestsBase):
    def test_successful_run_from_legend_entry_reference_persists_regions(self):
        entry = self._confirmed_reference_entry(hfx.family_a_parallel_45())
        page_image, ground_truth = df.build_single_target_page()
        self._set_page_preview(page_image)

        run = self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=entry.id)
        self.assertEqual(run.status, DetectionRunStatus.COMPLETED)
        self.assertEqual(run.reference_legend_entry_id, entry.id)
        self.assertIsNone(run.reference_pattern_library_entry_id)
        self.assertGreater(run.candidate_region_count, 0)
        self.assertIsNotNone(run.completed_at)
        self.assertEqual(run.detector_version, "1.0")

        regions = self.detection_service.list_regions(self.project.id, self.plan.id, run.id)
        self.assertEqual(len(regions), run.candidate_region_count)
        for region in regions:
            self.assertEqual(region.status, DetectedRegionStatus.CANDIDATE)
            self.assertGreaterEqual(region.similarity, 0.0)
            self.assertLessEqual(region.similarity, 1.0)

    def test_successful_run_from_pattern_library_entry_reference(self):
        entry = self._confirmed_reference_entry(hfx.family_a_parallel_45())
        library_entry = self.library_service.add_entry(self.project.id, self.plan.id, entry.id)
        page_image, _ = df.build_single_target_page()
        self._set_page_preview(page_image)

        run = self.detection_service.start_run(
            self.project.id, self.plan.id, 1, pattern_library_entry_id=library_entry.id
        )
        self.assertEqual(run.status, DetectionRunStatus.COMPLETED)
        self.assertEqual(run.reference_pattern_library_entry_id, library_entry.id)
        self.assertIsNone(run.reference_legend_entry_id)

    def test_blank_page_completes_with_zero_regions_not_a_failure(self):
        """No candidate tiles / all low-evidence tiles must still be a
        clean COMPLETED run, never FAILED (R6 section 28)."""
        entry = self._confirmed_reference_entry(hfx.family_a_parallel_45())
        page_image, _ = df.build_blank_page()
        self._set_page_preview(page_image)

        run = self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=entry.id)
        self.assertEqual(run.status, DetectionRunStatus.COMPLETED)
        self.assertEqual(run.candidate_region_count, 0)
        self.assertGreater(run.tiles_skipped, 0)
        self.assertEqual(self.detection_service.list_regions(self.project.id, self.plan.id, run.id), [])

    def test_missing_preview_raises_a_controlled_error(self):
        entry = self._confirmed_reference_entry(hfx.family_a_parallel_45())
        page = self.plan_service.get_page(self.project.id, self.plan.id, 1)
        preview_path = self.storage.resolve_preview(page.preview_reference)
        preview_path.unlink()
        with self.assertRaises(PagePreviewNotAvailableError):
            self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=entry.id)

    def test_corrupt_preview_fails_the_run_cleanly_not_a_crash(self):
        entry = self._confirmed_reference_entry(hfx.family_a_parallel_45())
        page = self.plan_service.get_page(self.project.id, self.plan.id, 1)
        preview_path = self.storage.resolve_preview(page.preview_reference)
        preview_path.write_bytes(b"not actually a png")

        run = self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=entry.id)
        self.assertEqual(run.status, DetectionRunStatus.FAILED)
        self.assertIsNotNone(run.error_message)
        self.assertNotIn("Traceback", run.error_message)
        self.assertIsNotNone(run.completed_at)
        # No partial COMPLETED state -- a failed run has no regions.
        self.assertEqual(self.detection_service.list_regions(self.project.id, self.plan.id, run.id), [])

    def test_custom_parameters_are_recorded_on_the_run(self):
        entry = self._confirmed_reference_entry(hfx.family_a_parallel_45())
        page_image, _ = df.build_single_target_page()
        self._set_page_preview(page_image)

        run = self.detection_service.start_run(
            self.project.id, self.plan.id, 1, legend_entry_id=entry.id,
            tile_size_px=96, stride_px=96, candidate_threshold=0.5, min_evidence_coverage=0.3,
        )
        self.assertEqual(run.parameters["tile_size_px"], 96)
        self.assertEqual(run.parameters["stride_px"], 96)
        self.assertEqual(run.parameters["candidate_threshold"], 0.5)
        self.assertEqual(run.parameters["min_evidence_coverage"], 0.3)


class ReviewTests(DetectionServiceTestsBase):
    def test_accept_and_reject_persist(self):
        entry = self._confirmed_reference_entry(hfx.family_a_parallel_45())
        page_image, _ = df.build_multi_target_page()
        self._set_page_preview(page_image)
        run = self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=entry.id)
        regions = self.detection_service.list_regions(self.project.id, self.plan.id, run.id)
        self.assertGreaterEqual(len(regions), 2)

        accepted = self.detection_service.update_region_status(
            self.project.id, self.plan.id, run.id, regions[0].id, DetectedRegionStatus.ACCEPTED
        )
        rejected = self.detection_service.update_region_status(
            self.project.id, self.plan.id, run.id, regions[1].id, DetectedRegionStatus.REJECTED
        )
        self.assertEqual(accepted.status, DetectedRegionStatus.ACCEPTED)
        self.assertEqual(rejected.status, DetectedRegionStatus.REJECTED)

        refreshed = self.detection_service.list_regions(self.project.id, self.plan.id, run.id)
        statuses = {r.id: r.status for r in refreshed}
        self.assertEqual(statuses[regions[0].id], DetectedRegionStatus.ACCEPTED)
        self.assertEqual(statuses[regions[1].id], DetectedRegionStatus.REJECTED)

    def test_unknown_region_raises(self):
        entry = self._confirmed_reference_entry(hfx.family_a_parallel_45())
        page_image, _ = df.build_single_target_page()
        self._set_page_preview(page_image)
        run = self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=entry.id)
        with self.assertRaises(DetectedRegionNotFoundError):
            self.detection_service.update_region_status(
                self.project.id, self.plan.id, run.id, uuid.uuid4(), DetectedRegionStatus.ACCEPTED
            )

    def test_unknown_run_raises(self):
        with self.assertRaises(DetectionRunNotFoundError):
            self.detection_service.get_run(self.project.id, self.plan.id, uuid.uuid4())


class OwnershipIsolationTests(DetectionServiceTestsBase):
    def test_run_from_another_project_is_not_found(self):
        entry = self._confirmed_reference_entry(hfx.family_a_parallel_45())
        page_image, _ = df.build_single_target_page()
        self._set_page_preview(page_image)
        run = self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=entry.id)

        other_project = self.project_service.create_project(ProjectCreate(name="Other"))
        other_plan = self.plan_service.upload_plan(other_project.id, "b.pdf", fx.build_vector_pdf_bytes())
        with self.assertRaises(DetectionRunNotFoundError):
            self.detection_service.get_run(other_project.id, other_plan.id, run.id)

    def test_reference_from_another_project_library_is_rejected(self):
        entry = self._confirmed_reference_entry(hfx.family_a_parallel_45())
        library_entry = self.library_service.add_entry(self.project.id, self.plan.id, entry.id)

        other_project = self.project_service.create_project(ProjectCreate(name="Other2"))
        other_plan = self.plan_service.upload_plan(other_project.id, "c.pdf", fx.build_vector_pdf_bytes())
        with self.assertRaises(ReferenceNotFoundError):
            self.detection_service.start_run(
                other_project.id, other_plan.id, 1, pattern_library_entry_id=library_entry.id
            )


class PersistenceTests(DetectionServiceTestsBase):
    def test_run_and_regions_persist_across_a_brand_new_engine_and_session(self):
        entry = self._confirmed_reference_entry(hfx.family_a_parallel_45())
        page_image, _ = df.build_single_target_page()
        self._set_page_preview(page_image)
        run = self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=entry.id)
        regions = self.detection_service.list_regions(self.project.id, self.plan.id, run.id)
        self.detection_service.update_region_status(
            self.project.id, self.plan.id, run.id, regions[0].id, DetectedRegionStatus.ACCEPTED
        )

        fresh_session = self.Session()
        try:
            fresh_service = DetectionService(fresh_session, storage=self.storage)
            fetched_run = fresh_service.get_run(self.project.id, self.plan.id, run.id)
            self.assertEqual(fetched_run.status, DetectionRunStatus.COMPLETED)
            fetched_regions = fresh_service.list_regions(self.project.id, self.plan.id, run.id)
            self.assertEqual(fetched_regions[0].status, DetectedRegionStatus.ACCEPTED)
        finally:
            fresh_session.close()

    def test_run_discoverable_via_list_runs_for_page_after_a_fresh_session(self):
        """The route the frontend uses to rediscover a run after a
        browser reload (R6 section 24) -- proves it works from a
        genuinely independent session, not just in-memory state."""
        entry = self._confirmed_reference_entry(hfx.family_a_parallel_45())
        page_image, _ = df.build_single_target_page()
        self._set_page_preview(page_image)
        run = self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=entry.id)

        fresh_session = self.Session()
        try:
            fresh_service = DetectionService(fresh_session, storage=self.storage)
            runs = fresh_service.list_runs_for_page(self.project.id, self.plan.id, 1)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].id, run.id)
        finally:
            fresh_session.close()

    def test_list_runs_for_page_orders_most_recent_first(self):
        entry = self._confirmed_reference_entry(hfx.family_a_parallel_45())
        page_image, _ = df.build_single_target_page()
        self._set_page_preview(page_image)
        first = self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=entry.id)
        second = self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=entry.id)

        runs = self.detection_service.list_runs_for_page(self.project.id, self.plan.id, 1)
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0].id, second.id)
        self.assertEqual(runs[1].id, first.id)


if __name__ == "__main__":
    unittest.main()
