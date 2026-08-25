"""API-level integration tests against a real Postgres database. Requires
the docker-compose Postgres service to be running:
    docker compose up -d postgres
"""

from __future__ import annotations

import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.routes.legend_entries as legend_routes_module
import app.routes.plans as plans_route_module
from tests import pdf_fixtures as fx
from tests.db_test_support import build_test_engine, new_sessionmaker, truncate_all

from app.db.database import get_db
from app.main import app
from app.schemas.project import ProjectCreate
from app.services.legend_service import LegendService
from app.services.ocr_service import OcrResult, OcrService
from app.services.plan_service import PlanService
from app.services.project_service import ProjectService
from app.services.storage_service import StorageService


class _FakeOcrProvider:
    name = "fake"

    def extract_text(self, image_path):
        return OcrResult(text="Stahlbeton C25/30 d=20cm", provider=self.name, confidence=0.9)


class LegendRoutesTests(unittest.TestCase):
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

        def _override_get_db():
            yield self.session

        def _override_plan_service() -> PlanService:
            return PlanService(self.session, storage=self.storage)

        def _override_legend_service() -> LegendService:
            return LegendService(self.session, storage=self.storage, ocr=OcrService(provider=_FakeOcrProvider()))

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[plans_route_module.get_plan_service] = _override_plan_service
        app.dependency_overrides[legend_routes_module.get_legend_service] = _override_legend_service
        self.client = TestClient(app)

        project = ProjectService(self.session).create_project(ProjectCreate(name="Legend Route Test Project"))
        self.project_id = str(project.id)
        plan = PlanService(self.session, storage=self.storage).upload_plan(
            project.id, "vector.pdf", fx.build_vector_pdf_bytes()
        )
        self.plan_id = str(plan.id)

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(plans_route_module.get_plan_service, None)
        app.dependency_overrides.pop(legend_routes_module.get_legend_service, None)
        self.session.close()
        self._tmp.cleanup()

    def _base(self, project_id=None, plan_id=None):
        return f"/api/projects/{project_id or self.project_id}/plans/{plan_id or self.plan_id}/legend-entries"

    def _create(self, page_number=1):
        return self.client.post(self._base(), json={"page_number": page_number})

    # -- creation / listing --------------------------------------------

    def test_create_draft_returns_201(self):
        response = self._create()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "draft")
        self.assertFalse(body["has_pattern_selection"])
        uuid.UUID(body["id"])

    def test_create_unknown_project_returns_404(self):
        response = self.client.post(self._base(project_id=str(uuid.uuid4())), json={"page_number": 1})
        self.assertEqual(response.status_code, 404)

    def test_create_unknown_plan_returns_404(self):
        response = self.client.post(self._base(plan_id=str(uuid.uuid4())), json={"page_number": 1})
        self.assertEqual(response.status_code, 404)

    def test_create_unknown_page_returns_404(self):
        response = self._create(page_number=99)
        self.assertEqual(response.status_code, 404)

    def test_list_returns_created_entries(self):
        self._create()
        self._create()
        response = self.client.get(self._base())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)

    def test_get_unknown_entry_returns_404(self):
        response = self.client.get(f"{self._base()}/{uuid.uuid4()}")
        self.assertEqual(response.status_code, 404)

    def test_cross_project_access_returns_404(self):
        entry_id = self._create().json()["id"]
        other_project = ProjectService(self.session).create_project(ProjectCreate(name="Other"))
        response = self.client.get(self._base(project_id=str(other_project.id)) + f"/{entry_id}")
        self.assertEqual(response.status_code, 404)

    # -- selections / bounds validation ---------------------------------

    def test_save_pattern_selection_returns_updated_entry(self):
        entry_id = self._create().json()["id"]
        response = self.client.post(
            f"{self._base()}/{entry_id}/pattern", json={"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.15}
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["pattern_x"], 0.1)
        self.assertTrue(body["has_pattern_selection"])

    def test_negative_coordinate_returns_400(self):
        entry_id = self._create().json()["id"]
        response = self.client.post(
            f"{self._base()}/{entry_id}/pattern", json={"x": -0.1, "y": 0.1, "width": 0.2, "height": 0.1}
        )
        self.assertEqual(response.status_code, 422)  # rejected by the Pydantic Field constraint

    def test_zero_size_selection_returns_422(self):
        entry_id = self._create().json()["id"]
        response = self.client.post(
            f"{self._base()}/{entry_id}/pattern", json={"x": 0.1, "y": 0.1, "width": 0, "height": 0.1}
        )
        self.assertEqual(response.status_code, 422)

    def test_selection_extending_past_page_returns_400(self):
        entry_id = self._create().json()["id"]
        response = self.client.post(
            f"{self._base()}/{entry_id}/pattern", json={"x": 0.9, "y": 0.1, "width": 0.5, "height": 0.1}
        )
        self.assertEqual(response.status_code, 400)

    def test_get_pattern_crop_returns_png(self):
        entry_id = self._create().json()["id"]
        self.client.post(f"{self._base()}/{entry_id}/pattern", json={"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.15})
        response = self.client.get(f"{self._base()}/{entry_id}/pattern")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(response.content[:8], b"\x89PNG\r\n\x1a\n")

    def test_get_pattern_crop_before_selection_returns_404(self):
        entry_id = self._create().json()["id"]
        response = self.client.get(f"{self._base()}/{entry_id}/pattern")
        self.assertEqual(response.status_code, 404)

    # -- OCR -------------------------------------------------------------

    def test_ocr_without_description_returns_400(self):
        entry_id = self._create().json()["id"]
        response = self.client.post(f"{self._base()}/{entry_id}/ocr")
        self.assertEqual(response.status_code, 400)

    def test_ocr_success_returns_text_and_advances_status(self):
        entry_id = self._create().json()["id"]
        self.client.post(f"{self._base()}/{entry_id}/description", json={"x": 0.5, "y": 0.5, "width": 0.2, "height": 0.1})
        response = self.client.post(f"{self._base()}/{entry_id}/ocr")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["raw_ocr_text"], "Stahlbeton C25/30 d=20cm")
        self.assertEqual(body["status"], "ocr_complete")
        self.assertEqual(body["ocr_provider"], "fake")
        self.assertIsNone(body["ocr_error"])

    # -- update / confirm -------------------------------------------

    def test_patch_updates_corrected_text_and_material(self):
        entry_id = self._create().json()["id"]
        response = self.client.patch(
            f"{self._base()}/{entry_id}",
            json={"corrected_text": "Stahlbeton C25/30", "material_name": "Stahlbeton C25/30", "thickness_mm": 200},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["corrected_text"], "Stahlbeton C25/30")
        self.assertEqual(body["material_name"], "Stahlbeton C25/30")
        self.assertEqual(body["thickness_mm"], 200)
        self.assertEqual(body["status"], "draft")  # PATCH must never itself confirm

    def test_confirm_without_required_fields_returns_400_with_reasons(self):
        entry_id = self._create().json()["id"]
        response = self.client.post(f"{self._base()}/{entry_id}/confirm")
        self.assertEqual(response.status_code, 400)
        self.assertIn("reasons", response.json()["detail"])

    def test_full_happy_path_create_to_confirm_to_retrieve(self):
        entry_id = self._create().json()["id"]

        pattern = self.client.post(
            f"{self._base()}/{entry_id}/pattern", json={"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.15}
        )
        self.assertEqual(pattern.status_code, 200)

        description = self.client.post(
            f"{self._base()}/{entry_id}/description", json={"x": 0.5, "y": 0.5, "width": 0.2, "height": 0.1}
        )
        self.assertEqual(description.status_code, 200)

        ocr = self.client.post(f"{self._base()}/{entry_id}/ocr")
        self.assertEqual(ocr.status_code, 200)
        self.assertEqual(ocr.json()["status"], "ocr_complete")

        patch = self.client.patch(
            f"{self._base()}/{entry_id}",
            json={"corrected_text": "Stahlbeton C25/30, d=20cm", "material_name": "Stahlbeton C25/30", "thickness_mm": 200},
        )
        self.assertEqual(patch.status_code, 200)

        confirm = self.client.post(f"{self._base()}/{entry_id}/confirm")
        self.assertEqual(confirm.status_code, 200)
        confirmed_body = confirm.json()
        self.assertEqual(confirmed_body["status"], "confirmed")
        self.assertIsNotNone(confirmed_body["confirmed_at"])

        retrieved = self.client.get(f"{self._base()}/{entry_id}")
        self.assertEqual(retrieved.status_code, 200)
        retrieved_body = retrieved.json()
        self.assertEqual(retrieved_body["status"], "confirmed")
        self.assertEqual(retrieved_body["raw_ocr_text"], "Stahlbeton C25/30 d=20cm")
        self.assertEqual(retrieved_body["corrected_text"], "Stahlbeton C25/30, d=20cm")

    def test_existing_plan_and_project_routes_unaffected(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get(f"/api/projects/{self.project_id}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/projects/{self.project_id}/plans/{self.plan_id}").status_code, 200)


if __name__ == "__main__":
    unittest.main()
