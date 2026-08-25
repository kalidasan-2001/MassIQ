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

from tests import pdf_fixtures as fx
from tests.db_test_support import build_test_engine, new_sessionmaker, truncate_all

from app.models.legend_entry import LegendEntryStatus
from app.schemas.legend_entry import LegendEntryUpdate
from app.schemas.project import ProjectCreate
from app.services.legend_crop_service import RegionSelection
from app.services.legend_service import (
    DescriptionNotSelectedError,
    LegendConfirmationError,
    LegendEntryNotFoundError,
    LegendService,
)
from app.services.ocr_service import OcrResult, OcrService
from app.services.plan_service import PlanPageNotFoundError, PlanService
from app.services.project_service import ProjectNotFoundError, ProjectService
from app.services.storage_service import StorageService


class _FakeOcrProvider:
    name = "fake"

    def __init__(self, text="Stahlbeton C25/30 d=20cm", confidence=0.9, raise_error=False):
        self._text = text
        self._confidence = confidence
        self._raise_error = raise_error

    def extract_text(self, image_path):
        if self._raise_error:
            raise RuntimeError("simulated OCR engine failure")
        return OcrResult(text=self._text, provider=self.name, confidence=self._confidence)


class LegendServiceTestsBase(unittest.TestCase):
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

        self.project = self.project_service.create_project(ProjectCreate(name="Legend Test Project"))
        self.plan = self.plan_service.upload_plan(self.project.id, "vector.pdf", fx.build_vector_pdf_bytes())

    def tearDown(self):
        self.session.close()
        self._tmp.cleanup()

    def _create_draft(self):
        return self.legend_service.create_draft(self.project.id, self.plan.id, page_number=1)

    def _confirmable_selection(self, x=0.05, y=0.05, width=0.2, height=0.1):
        return RegionSelection(x=x, y=y, width=width, height=height)


class CreateDraftTests(LegendServiceTestsBase):
    def test_create_draft_persists_with_resolved_plan_page(self):
        entry = self._create_draft()
        self.assertEqual(entry.status, LegendEntryStatus.DRAFT)
        self.assertEqual(entry.project_id, self.project.id)
        self.assertEqual(entry.plan_id, self.plan.id)
        self.assertEqual(entry.plan_page_id, self.plan.pages[0].id)
        self.assertIsNone(entry.pattern_image_reference)
        self.assertIsNone(entry.confirmed_at)

    def test_unknown_page_number_raises(self):
        with self.assertRaises(PlanPageNotFoundError):
            self.legend_service.create_draft(self.project.id, self.plan.id, page_number=99)

    def test_cannot_create_for_plan_belonging_to_another_project(self):
        """Ownership: a Plan that exists but belongs to a different project
        must not accept a new LegendEntry via this project_id."""
        other_project = self.project_service.create_project(ProjectCreate(name="Other Project"))
        with self.assertRaises(Exception):  # PlanNotFoundError (isolation), not a silent success
            self.legend_service.create_draft(other_project.id, self.plan.id, page_number=1)


class SelectionAndCropTests(LegendServiceTestsBase):
    def test_save_pattern_selection_persists_fields_and_file(self):
        entry = self._create_draft()
        selection = RegionSelection(x=0.1, y=0.1, width=0.2, height=0.15)
        updated = self.legend_service.save_pattern_selection(self.project.id, self.plan.id, entry.id, selection)
        self.assertEqual(updated.pattern_x, 0.1)
        self.assertEqual(updated.pattern_y, 0.1)
        self.assertEqual(updated.pattern_width, 0.2)
        self.assertEqual(updated.pattern_height, 0.15)
        self.assertIsNotNone(updated.pattern_image_reference)
        resolved = self.storage.resolve_legend_crop(updated.pattern_image_reference)
        self.assertTrue(resolved.exists())
        self.assertIn(f"legend/{entry.id}/pattern.png", updated.pattern_image_reference)

    def test_save_description_selection_persists_fields_and_file(self):
        entry = self._create_draft()
        selection = RegionSelection(x=0.5, y=0.5, width=0.2, height=0.15)
        updated = self.legend_service.save_description_selection(self.project.id, self.plan.id, entry.id, selection)
        self.assertIsNotNone(updated.description_image_reference)
        resolved = self.storage.resolve_legend_crop(updated.description_image_reference)
        self.assertTrue(resolved.exists())
        self.assertIn(f"legend/{entry.id}/description.png", updated.description_image_reference)

    def test_pattern_and_description_are_stored_separately_not_overwriting(self):
        entry = self._create_draft()
        self.legend_service.save_pattern_selection(self.project.id, self.plan.id, entry.id, self._confirmable_selection())
        updated = self.legend_service.save_description_selection(
            self.project.id, self.plan.id, entry.id, RegionSelection(x=0.6, y=0.6, width=0.2, height=0.1)
        )
        self.assertIsNotNone(updated.pattern_image_reference)
        self.assertIsNotNone(updated.description_image_reference)
        self.assertNotEqual(updated.pattern_image_reference, updated.description_image_reference)

    def test_get_crop_path_for_unset_kind_raises(self):
        from app.services.storage_service import StorageError

        entry = self._create_draft()
        with self.assertRaises(StorageError):
            self.legend_service.get_crop_path(self.project.id, self.plan.id, entry.id, "pattern")


class OcrTests(LegendServiceTestsBase):
    def test_ocr_success_sets_raw_text_and_status(self):
        entry = self._create_draft()
        self.legend_service.save_description_selection(self.project.id, self.plan.id, entry.id, self._confirmable_selection())
        updated, result = self.legend_service.run_ocr(self.project.id, self.plan.id, entry.id)
        self.assertEqual(updated.raw_ocr_text, "Stahlbeton C25/30 d=20cm")
        self.assertEqual(updated.status, LegendEntryStatus.OCR_COMPLETE)
        self.assertIsNone(result.error)

    def test_ocr_empty_result_still_completes_status(self):
        service = LegendService(self.session, storage=self.storage, ocr=OcrService(provider=_FakeOcrProvider(text="")))
        entry = self._create_draft()
        service.save_description_selection(self.project.id, self.plan.id, entry.id, self._confirmable_selection())
        updated, result = service.run_ocr(self.project.id, self.plan.id, entry.id)
        self.assertIsNone(updated.raw_ocr_text)
        self.assertEqual(updated.status, LegendEntryStatus.OCR_COMPLETE)
        self.assertIsNone(result.error)

    def test_ocr_failure_still_allows_manual_correction_and_confirmation(self):
        """OCR failure must be non-fatal: the user can still type the
        description manually and confirm the entry despite a technical
        OCR failure."""
        service = LegendService(
            self.session, storage=self.storage, ocr=OcrService(provider=_FakeOcrProvider(raise_error=True))
        )
        entry = self._create_draft()
        service.save_pattern_selection(self.project.id, self.plan.id, entry.id, self._confirmable_selection())
        service.save_description_selection(
            self.project.id, self.plan.id, entry.id, RegionSelection(x=0.5, y=0.5, width=0.2, height=0.1)
        )
        updated, result = service.run_ocr(self.project.id, self.plan.id, entry.id)
        self.assertIsNone(updated.raw_ocr_text)
        self.assertIsNotNone(result.error)
        self.assertEqual(updated.status, LegendEntryStatus.OCR_COMPLETE)

        # Manual correction still works after an OCR failure.
        corrected = service.update_entry(
            self.project.id, self.plan.id, entry.id,
            LegendEntryUpdate(corrected_text="Stahlbeton C30/37 d=20 cm", material_name="Stahlbeton C30/37"),
        )
        self.assertEqual(corrected.corrected_text, "Stahlbeton C30/37 d=20 cm")

        confirmed = service.confirm(self.project.id, self.plan.id, entry.id)
        self.assertEqual(confirmed.status, LegendEntryStatus.CONFIRMED)

    def test_ocr_without_description_selection_raises(self):
        entry = self._create_draft()
        with self.assertRaises(DescriptionNotSelectedError):
            self.legend_service.run_ocr(self.project.id, self.plan.id, entry.id)

    def test_raw_ocr_text_never_overwritten_by_correction(self):
        """Provenance: correcting the text must not touch raw_ocr_text."""
        entry = self._create_draft()
        self.legend_service.save_description_selection(self.project.id, self.plan.id, entry.id, self._confirmable_selection())
        self.legend_service.run_ocr(self.project.id, self.plan.id, entry.id)
        self.legend_service.update_entry(
            self.project.id, self.plan.id, entry.id, LegendEntryUpdate(corrected_text="A completely different value")
        )
        refreshed = self.legend_service.get_entry(self.project.id, self.plan.id, entry.id)
        self.assertEqual(refreshed.raw_ocr_text, "Stahlbeton C25/30 d=20cm")
        self.assertEqual(refreshed.corrected_text, "A completely different value")


class ConfirmationTests(LegendServiceTestsBase):
    def test_confirm_without_any_fields_raises_with_reasons(self):
        entry = self._create_draft()
        with self.assertRaises(LegendConfirmationError) as ctx:
            self.legend_service.confirm(self.project.id, self.plan.id, entry.id)
        self.assertGreaterEqual(len(ctx.exception.reasons), 3)

    def test_confirm_requires_pattern_description_text_and_material(self):
        entry = self._create_draft()
        self.legend_service.save_pattern_selection(self.project.id, self.plan.id, entry.id, self._confirmable_selection())
        with self.assertRaises(LegendConfirmationError):
            self.legend_service.confirm(self.project.id, self.plan.id, entry.id)

        self.legend_service.save_description_selection(
            self.project.id, self.plan.id, entry.id, RegionSelection(x=0.5, y=0.5, width=0.2, height=0.1)
        )
        with self.assertRaises(LegendConfirmationError):
            self.legend_service.confirm(self.project.id, self.plan.id, entry.id)

        self.legend_service.update_entry(
            self.project.id, self.plan.id, entry.id, LegendEntryUpdate(corrected_text="Stahlbeton C25/30")
        )
        with self.assertRaises(LegendConfirmationError) as ctx:
            self.legend_service.confirm(self.project.id, self.plan.id, entry.id)
        self.assertIn("material name is required", ctx.exception.reasons)

        self.legend_service.update_entry(
            self.project.id, self.plan.id, entry.id, LegendEntryUpdate(material_name="Stahlbeton C25/30")
        )
        confirmed = self.legend_service.confirm(self.project.id, self.plan.id, entry.id)
        self.assertEqual(confirmed.status, LegendEntryStatus.CONFIRMED)
        self.assertIsNotNone(confirmed.confirmed_at)

    def test_cannot_silently_confirm_via_update(self):
        """update_entry must never itself flip status to CONFIRMED -- only
        the explicit confirm() call may do that."""
        entry = self._create_draft()
        self.legend_service.save_pattern_selection(self.project.id, self.plan.id, entry.id, self._confirmable_selection())
        self.legend_service.save_description_selection(
            self.project.id, self.plan.id, entry.id, RegionSelection(x=0.5, y=0.5, width=0.2, height=0.1)
        )
        updated = self.legend_service.update_entry(
            self.project.id, self.plan.id, entry.id,
            LegendEntryUpdate(corrected_text="Stahlbeton C25/30", material_name="Stahlbeton C25/30"),
        )
        self.assertNotEqual(updated.status, LegendEntryStatus.CONFIRMED)


class RetrievalAndIsolationTests(LegendServiceTestsBase):
    def test_list_entries_returns_all_for_plan(self):
        self._create_draft()
        self._create_draft()
        self.assertEqual(len(self.legend_service.list_entries(self.project.id, self.plan.id)), 2)

    def test_get_unknown_entry_raises(self):
        with self.assertRaises(LegendEntryNotFoundError):
            self.legend_service.get_entry(self.project.id, self.plan.id, uuid.uuid4())

    def test_entry_from_other_plan_is_not_found_via_wrong_plan_id(self):
        other_plan = self.plan_service.upload_plan(self.project.id, "b.pdf", fx.build_vector_pdf_bytes())
        entry = self.legend_service.create_draft(self.project.id, other_plan.id, page_number=1)
        with self.assertRaises(LegendEntryNotFoundError):
            self.legend_service.get_entry(self.project.id, self.plan.id, entry.id)

    def test_entry_from_other_project_is_not_found(self):
        other_project = self.project_service.create_project(ProjectCreate(name="Other"))
        other_plan = self.plan_service.upload_plan(other_project.id, "c.pdf", fx.build_vector_pdf_bytes())
        entry = self.legend_service.create_draft(other_project.id, other_plan.id, page_number=1)
        with self.assertRaises(Exception):
            self.legend_service.get_entry(self.project.id, self.plan.id, entry.id)

    def test_persists_across_a_brand_new_engine_and_session(self):
        """Mirrors R1's cross-process persistence proof: data written via
        one engine/session must be readable via a completely independent
        second one against the same database."""
        entry = self._create_draft()
        self.legend_service.save_pattern_selection(self.project.id, self.plan.id, entry.id, self._confirmable_selection())
        self.legend_service.save_description_selection(
            self.project.id, self.plan.id, entry.id, RegionSelection(x=0.5, y=0.5, width=0.2, height=0.1)
        )
        self.legend_service.run_ocr(self.project.id, self.plan.id, entry.id)
        self.legend_service.update_entry(
            self.project.id, self.plan.id, entry.id,
            LegendEntryUpdate(corrected_text="Stahlbeton C25/30", material_name="Stahlbeton C25/30", thickness_mm=200),
        )
        self.legend_service.confirm(self.project.id, self.plan.id, entry.id)

        fresh_session = self.Session()
        try:
            fresh_service = LegendService(fresh_session, storage=self.storage)
            fetched = fresh_service.get_entry(self.project.id, self.plan.id, entry.id)
            self.assertEqual(fetched.status, LegendEntryStatus.CONFIRMED)
            self.assertEqual(fetched.corrected_text, "Stahlbeton C25/30")
            self.assertEqual(fetched.material_name, "Stahlbeton C25/30")
            self.assertEqual(fetched.thickness_mm, 200)
            self.assertEqual(fetched.raw_ocr_text, "Stahlbeton C25/30 d=20cm")
            self.assertIsNotNone(fetched.pattern_image_reference)
            self.assertIsNotNone(fetched.description_image_reference)
        finally:
            fresh_session.close()


if __name__ == "__main__":
    unittest.main()
