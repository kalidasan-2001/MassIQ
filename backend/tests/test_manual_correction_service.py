"""Integration tests against a real Postgres database (see db_test_support.py)."""

from __future__ import annotations

import sys
import tempfile
import unittest
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests import hatch_fixtures as hfx
from tests import pdf_fixtures as fx
from tests.db_test_support import build_test_engine, new_sessionmaker, truncate_all

from app.geometry.service import NormalizedRect
from app.models.manual_region_correction import ManualCorrectionType
from app.schemas.legend_entry import LegendEntryUpdate
from app.schemas.project import ProjectCreate
from app.services.detection_service import DetectionRunNotFoundError, DetectionService
from app.services.legend_crop_service import RegionSelection
from app.services.legend_service import LegendService
from app.services.manual_correction_service import (
    InvalidCorrectionGeometryError,
    ManualCorrectionNotFoundError,
    ManualCorrectionService,
)
from app.services.ocr_service import OcrResult, OcrService
from app.services.plan_service import PlanService
from app.services.project_service import ProjectService
from app.services.storage_service import StorageService


class _FakeOcrProvider:
    name = "fake"

    def extract_text(self, image_path):
        return OcrResult(text="Stahlbeton C25/30", provider=self.name, confidence=0.9)


class ManualCorrectionServiceTests(unittest.TestCase):
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

        self.project = self.project_service.create_project(ProjectCreate(name="Correction Test Project"))
        self.plan = self.plan_service.upload_plan(self.project.id, "vector.pdf", fx.build_vector_pdf_bytes())
        self.run = self._make_completed_run()

    def tearDown(self):
        self.session.close()
        self._tmp.cleanup()

    def _make_completed_run(self):
        """A real DetectionRun via the real pipeline, over a blank page --
        gives a genuine, ownership-consistent run with zero candidates, so
        manual-correction tests exercise real persistence without
        depending on CV-detected geometry."""
        import numpy as np

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

        from app.services.hatch_feature_service import HatchFeatureService
        import cv2

        feature_service = HatchFeatureService(self.session, storage=self.storage)
        crop_path = self.storage.resolve_legend_crop(confirmed.pattern_image_reference)
        ok, buffer = cv2.imencode(".png", hfx.family_a_parallel_45())
        assert ok
        crop_path.write_bytes(buffer.tobytes())
        feature_service.compute_features(self.project.id, self.plan.id, confirmed.id)

        # Blank preview -> a real, clean COMPLETED run with zero candidates.
        page = self.plan_service.get_page(self.project.id, self.plan.id, 1)
        preview_path = self.storage.resolve_preview(page.preview_reference)
        blank = np.full((700, 900, 3), 255, dtype=np.uint8)
        ok, buffer = cv2.imencode(".png", blank)
        assert ok
        preview_path.write_bytes(buffer.tobytes())

        return self.detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=confirmed.id)

    def test_create_add_correction(self):
        correction = self.correction_service.create_correction(
            self.project.id, self.plan.id, self.run.id, ManualCorrectionType.ADD, NormalizedRect(0.1, 0.1, 0.2, 0.2)
        )
        self.assertEqual(correction.correction_type, ManualCorrectionType.ADD)
        self.assertEqual(correction.detection_run_id, self.run.id)
        self.assertEqual(correction.plan_page_id, self.run.plan_page_id)

    def test_create_subtract_correction(self):
        correction = self.correction_service.create_correction(
            self.project.id, self.plan.id, self.run.id, ManualCorrectionType.SUBTRACT,
            NormalizedRect(0.3, 0.3, 0.1, 0.1),
        )
        self.assertEqual(correction.correction_type, ManualCorrectionType.SUBTRACT)

    def test_list_corrections_returns_created_order(self):
        first = self.correction_service.create_correction(
            self.project.id, self.plan.id, self.run.id, ManualCorrectionType.ADD, NormalizedRect(0, 0, 0.1, 0.1)
        )
        second = self.correction_service.create_correction(
            self.project.id, self.plan.id, self.run.id, ManualCorrectionType.SUBTRACT, NormalizedRect(0.2, 0, 0.1, 0.1)
        )
        corrections = self.correction_service.list_corrections(self.project.id, self.plan.id, self.run.id)
        self.assertEqual([c.id for c in corrections], [first.id, second.id])

    def test_delete_correction(self):
        correction = self.correction_service.create_correction(
            self.project.id, self.plan.id, self.run.id, ManualCorrectionType.ADD, NormalizedRect(0, 0, 0.1, 0.1)
        )
        self.correction_service.delete_correction(self.project.id, self.plan.id, self.run.id, correction.id)
        self.assertEqual(self.correction_service.list_corrections(self.project.id, self.plan.id, self.run.id), [])

    def test_delete_unknown_correction_raises(self):
        with self.assertRaises(ManualCorrectionNotFoundError):
            self.correction_service.delete_correction(self.project.id, self.plan.id, self.run.id, uuid.uuid4())

    def test_invalid_geometry_rejected(self):
        cases = [
            NormalizedRect(0, 0, 0, 0.1),  # zero width
            NormalizedRect(0, 0, 0.1, 0),  # zero height
            NormalizedRect(0, 0, -0.1, 0.1),  # negative width
            NormalizedRect(-0.1, 0, 0.1, 0.1),  # negative x
            NormalizedRect(0.95, 0, 0.5, 0.1),  # extends past page right edge
            NormalizedRect(0, 0, float("nan"), 0.1),  # NaN
            NormalizedRect(0, 0, float("inf"), 0.1),  # Infinity
        ]
        for rect in cases:
            with self.assertRaises(InvalidCorrectionGeometryError):
                self.correction_service.create_correction(
                    self.project.id, self.plan.id, self.run.id, ManualCorrectionType.ADD, rect
                )

    def test_unknown_run_raises(self):
        with self.assertRaises(DetectionRunNotFoundError):
            self.correction_service.create_correction(
                self.project.id, self.plan.id, uuid.uuid4(), ManualCorrectionType.ADD, NormalizedRect(0, 0, 0.1, 0.1)
            )

    def test_cross_project_run_access_raises(self):
        other_project = self.project_service.create_project(ProjectCreate(name="Other"))
        other_plan = self.plan_service.upload_plan(other_project.id, "b.pdf", fx.build_vector_pdf_bytes())
        with self.assertRaises(DetectionRunNotFoundError):
            self.correction_service.create_correction(
                other_project.id, other_plan.id, self.run.id, ManualCorrectionType.ADD, NormalizedRect(0, 0, 0.1, 0.1)
            )

    def test_correction_persists_across_a_fresh_session(self):
        correction = self.correction_service.create_correction(
            self.project.id, self.plan.id, self.run.id, ManualCorrectionType.ADD, NormalizedRect(0, 0, 0.1, 0.1)
        )
        fresh_session = self.Session()
        try:
            fresh_service = ManualCorrectionService(fresh_session, storage=self.storage)
            corrections = fresh_service.list_corrections(self.project.id, self.plan.id, self.run.id)
            self.assertEqual(len(corrections), 1)
            self.assertEqual(corrections[0].id, correction.id)
        finally:
            fresh_session.close()


if __name__ == "__main__":
    unittest.main()
