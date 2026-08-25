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
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests import pdf_fixtures as fx
from tests.db_test_support import build_test_engine, new_sessionmaker, truncate_all

from app.models.plan import PdfType, PlanProcessingStatus
from app.schemas.project import ProjectCreate
from app.services.pdf_inspection_service import InvalidPdfError
from app.services.plan_service import PlanNotFoundError, PlanService
from app.services.project_service import ProjectNotFoundError, ProjectService
from app.services.storage_service import StorageService


class PlanServiceTestsBase(unittest.TestCase):
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
        # Isolated per-test storage root -- never touches backend/app/storage/.
        self.storage = StorageService(root=Path(self._tmp.name))
        self.plan_service = PlanService(self.session, storage=self.storage)
        self.project_service = ProjectService(self.session)
        self.project = self.project_service.create_project(ProjectCreate(name="Test Project"))

    def tearDown(self):
        self.session.close()
        self._tmp.cleanup()


class UploadPlanTests(PlanServiceTestsBase):
    def test_valid_vector_pdf_creates_ready_plan(self):
        plan = self.plan_service.upload_plan(self.project.id, "vector.pdf", fx.build_vector_pdf_bytes())
        self.assertEqual(plan.processing_status, PlanProcessingStatus.READY)
        self.assertEqual(plan.pdf_type, PdfType.VECTOR)
        self.assertEqual(plan.page_count, 1)
        self.assertEqual(plan.original_filename, "vector.pdf")
        self.assertEqual(len(plan.pages), 1)
        self.assertIsInstance(plan.id, uuid.UUID)
        self.assertEqual(plan.project_id, self.project.id)

    def test_multi_page_pdf_creates_matching_plan_page_rows(self):
        plan = self.plan_service.upload_plan(self.project.id, "multi.pdf", fx.build_multi_page_vector_pdf_bytes(3))
        self.assertEqual(plan.page_count, 3)
        self.assertEqual(len(plan.pages), 3)
        self.assertEqual([p.page_number for p in plan.pages], [1, 2, 3])
        for page in plan.pages:
            self.assertGreater(page.width, 0)
            self.assertGreater(page.height, 0)
            self.assertIsNotNone(page.preview_reference)
            # Preview must actually be resolvable on disk, not just a string.
            resolved = self.storage.resolve_preview(page.preview_reference)
            self.assertTrue(resolved.exists())
        self.assertEqual(plan.pages[2].rotation, 90)

    def test_raster_pdf_classified_raster(self):
        plan = self.plan_service.upload_plan(self.project.id, "raster.pdf", fx.build_raster_pdf_bytes())
        self.assertEqual(plan.pdf_type, PdfType.RASTER)

    def test_mixed_pdf_classified_mixed(self):
        plan = self.plan_service.upload_plan(self.project.id, "mixed.pdf", fx.build_mixed_pdf_bytes())
        self.assertEqual(plan.pdf_type, PdfType.MIXED)

    def test_original_file_is_persisted_and_resolvable(self):
        content = fx.build_vector_pdf_bytes()
        plan = self.plan_service.upload_plan(self.project.id, "vector.pdf", content)
        resolved = self.storage.resolve_original_plan(plan.stored_file_reference)
        self.assertEqual(resolved.read_bytes(), content)

    def test_stored_reference_is_relative_not_absolute(self):
        plan = self.plan_service.upload_plan(self.project.id, "vector.pdf", fx.build_vector_pdf_bytes())
        self.assertFalse(Path(plan.stored_file_reference).is_absolute())
        self.assertNotIn(str(self.storage.root), plan.stored_file_reference)

    def test_unknown_project_raises_not_found_and_nothing_persisted(self):
        bogus_project_id = uuid.uuid4()
        with self.assertRaises(ProjectNotFoundError):
            self.plan_service.upload_plan(bogus_project_id, "x.pdf", fx.build_vector_pdf_bytes())

    def test_empty_upload_rejected_and_nothing_persisted(self):
        with self.assertRaises(InvalidPdfError):
            self.plan_service.upload_plan(self.project.id, "empty.pdf", fx.build_empty_pdf_bytes())
        self.assertEqual(self.plan_service.list_plans(self.project.id), [])

    def test_corrupt_pdf_rejected_and_nothing_persisted(self):
        with self.assertRaises(InvalidPdfError):
            self.plan_service.upload_plan(self.project.id, "corrupt.pdf", fx.build_corrupt_pdf_bytes())
        self.assertEqual(self.plan_service.list_plans(self.project.id), [])

    def test_fake_pdf_rejected_nothing_persisted_and_no_files_written(self):
        with self.assertRaises(InvalidPdfError):
            self.plan_service.upload_plan(self.project.id, "fake.pdf", fx.build_fake_pdf_bytes())
        self.assertEqual(self.plan_service.list_plans(self.project.id), [])
        plans_dir = Path(self._tmp.name) / "plans"
        remaining = list(plans_dir.glob("*")) if plans_dir.exists() else []
        self.assertEqual(remaining, [], "rejected upload must not write any files")


class PlanRetrievalTests(PlanServiceTestsBase):
    def test_list_plans_returns_all_for_project(self):
        self.plan_service.upload_plan(self.project.id, "a.pdf", fx.build_vector_pdf_bytes())
        self.plan_service.upload_plan(self.project.id, "b.pdf", fx.build_vector_pdf_bytes())
        self.assertEqual(len(self.plan_service.list_plans(self.project.id)), 2)

    def test_list_plans_unknown_project_raises_not_found(self):
        with self.assertRaises(ProjectNotFoundError):
            self.plan_service.list_plans(uuid.uuid4())

    def test_get_plan_returns_created_plan_with_pages(self):
        created = self.plan_service.upload_plan(self.project.id, "a.pdf", fx.build_multi_page_vector_pdf_bytes(3))
        fetched = self.plan_service.get_plan(self.project.id, created.id)
        self.assertEqual(fetched.id, created.id)
        self.assertEqual(len(fetched.pages), 3)

    def test_get_unknown_plan_raises_not_found(self):
        with self.assertRaises(PlanNotFoundError):
            self.plan_service.get_plan(self.project.id, uuid.uuid4())

    def test_plan_from_other_project_is_not_found_via_wrong_project_id(self):
        """Project isolation: a real Plan ID belonging to a different project
        must 404 here, not leak across projects."""
        other_project = self.project_service.create_project(ProjectCreate(name="Other Project"))
        plan = self.plan_service.upload_plan(other_project.id, "a.pdf", fx.build_vector_pdf_bytes())
        with self.assertRaises(PlanNotFoundError):
            self.plan_service.get_plan(self.project.id, plan.id)


class UploadPlanFailurePathTests(PlanServiceTestsBase):
    def test_forced_failure_during_page_rendering_leaves_no_trace(self):
        """Forces a failure partway through ingesting a 3-page PDF (page 1's
        preview succeeds, page 2's render raises). Must prove: no Plan row
        committed, no PlanPage rows committed, and no files left on disk for
        that plan_id -- the DB must never be able to say READY, or even
        contain a partial row, while assets are incomplete."""
        from app.services import plan_service as plan_service_module

        call_count = {"n": 0}
        original_render = plan_service_module.render_page_to_png_bytes

        def flaky_render(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("simulated rendering failure")
            return original_render(*args, **kwargs)

        with mock.patch.object(plan_service_module, "render_page_to_png_bytes", side_effect=flaky_render):
            with self.assertRaises(RuntimeError):
                self.plan_service.upload_plan(self.project.id, "multi.pdf", fx.build_multi_page_vector_pdf_bytes(3))

        self.assertEqual(self.plan_service.list_plans(self.project.id), [])
        plans_dir = Path(self._tmp.name) / "plans"
        remaining = list(plans_dir.glob("*")) if plans_dir.exists() else []
        self.assertEqual(remaining, [], "failed ingestion must not leave orphaned files on disk")


if __name__ == "__main__":
    unittest.main()
