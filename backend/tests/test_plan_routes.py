"""API-level integration tests against a real Postgres database. Requires the
docker-compose Postgres service to be running:
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

import app.routes.plans as plans_route_module
from tests import pdf_fixtures as fx
from tests.db_test_support import build_test_engine, new_sessionmaker, truncate_all

from app.db.database import get_db
from app.main import app
from app.schemas.project import ProjectCreate
from app.services.plan_service import PlanService
from app.services.project_service import ProjectService
from app.services.storage_service import StorageService


class PlanRoutesTests(unittest.TestCase):
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

        def _override_storage_service() -> StorageService:
            return self.storage

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[plans_route_module.get_plan_service] = _override_plan_service
        app.dependency_overrides[plans_route_module.get_storage_service] = _override_storage_service
        self.client = TestClient(app)

        project = ProjectService(self.session).create_project(ProjectCreate(name="Route Test Project"))
        self.project_id = str(project.id)

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(plans_route_module.get_plan_service, None)
        app.dependency_overrides.pop(plans_route_module.get_storage_service, None)
        self.session.close()
        self._tmp.cleanup()

    def _upload(self, filename: str, content: bytes, project_id: str | None = None):
        return self.client.post(
            f"/api/projects/{project_id or self.project_id}/plans",
            files={"file": (filename, content, "application/pdf")},
        )

    def test_upload_valid_vector_pdf_returns_201_ready(self):
        response = self._upload("vector.pdf", fx.build_vector_pdf_bytes())
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["processing_status"], "ready")
        self.assertEqual(body["pdf_type"], "vector")
        self.assertEqual(body["page_count"], 1)
        self.assertEqual(body["original_filename"], "vector.pdf")
        uuid.UUID(body["id"])

    def test_upload_raster_pdf_classified_raster(self):
        response = self._upload("raster.pdf", fx.build_raster_pdf_bytes())
        self.assertEqual(response.json()["pdf_type"], "raster")

    def test_upload_mixed_pdf_classified_mixed(self):
        response = self._upload("mixed.pdf", fx.build_mixed_pdf_bytes())
        self.assertEqual(response.json()["pdf_type"], "mixed")

    def test_upload_multi_page_pdf(self):
        response = self._upload("multi.pdf", fx.build_multi_page_vector_pdf_bytes(3))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["page_count"], 3)

    def test_upload_empty_file_returns_400_not_500(self):
        response = self._upload("empty.pdf", fx.build_empty_pdf_bytes())
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("Traceback", response.text)

    def test_upload_corrupt_file_returns_400(self):
        response = self._upload("corrupt.pdf", fx.build_corrupt_pdf_bytes())
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("Traceback", response.text)

    def test_upload_fake_text_file_returns_400(self):
        response = self._upload("fake.pdf", fx.build_fake_pdf_bytes())
        self.assertEqual(response.status_code, 400)

    def test_upload_to_unknown_project_returns_404(self):
        response = self._upload("vector.pdf", fx.build_vector_pdf_bytes(), project_id=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 404)

    def test_list_plans_returns_uploaded_plans(self):
        self._upload("a.pdf", fx.build_vector_pdf_bytes())
        self._upload("b.pdf", fx.build_vector_pdf_bytes())
        response = self.client.get(f"/api/projects/{self.project_id}/plans")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)

    def test_list_plans_unknown_project_returns_404(self):
        response = self.client.get(f"/api/projects/{uuid.uuid4()}/plans")
        self.assertEqual(response.status_code, 404)

    def test_get_plan_detail_includes_pages_in_order(self):
        created = self._upload("multi.pdf", fx.build_multi_page_vector_pdf_bytes(3)).json()
        response = self.client.get(f"/api/projects/{self.project_id}/plans/{created['id']}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["pages"]), 3)
        self.assertEqual([p["page_number"] for p in body["pages"]], [1, 2, 3])

    def test_get_unknown_plan_returns_404(self):
        response = self.client.get(f"/api/projects/{self.project_id}/plans/{uuid.uuid4()}")
        self.assertEqual(response.status_code, 404)

    def test_get_plan_from_wrong_project_returns_404(self):
        other_project_id = ProjectService(self.session).create_project(ProjectCreate(name="Other")).id
        created = self._upload("a.pdf", fx.build_vector_pdf_bytes(), project_id=str(other_project_id)).json()
        response = self.client.get(f"/api/projects/{self.project_id}/plans/{created['id']}")
        self.assertEqual(response.status_code, 404)

    def test_list_plan_pages_endpoint(self):
        created = self._upload("multi.pdf", fx.build_multi_page_vector_pdf_bytes(3)).json()
        response = self.client.get(f"/api/projects/{self.project_id}/plans/{created['id']}/pages")
        self.assertEqual(response.status_code, 200)
        pages = response.json()
        self.assertEqual(len(pages), 3)
        self.assertEqual([p["page_number"] for p in pages], [1, 2, 3])

    def test_existing_health_and_root_endpoints_unaffected(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 200)

    # -- R2.5: preview endpoint -------------------------------------------

    def test_get_plan_page_preview_returns_valid_png(self):
        created = self._upload("vector.pdf", fx.build_vector_pdf_bytes()).json()
        response = self.client.get(
            f"/api/projects/{self.project_id}/plans/{created['id']}/pages/1/preview"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertGreater(len(response.content), 0)
        self.assertEqual(response.content[:8], b"\x89PNG\r\n\x1a\n")  # real PNG magic bytes, not a stub

    def test_preview_unknown_project_returns_404(self):
        created = self._upload("vector.pdf", fx.build_vector_pdf_bytes()).json()
        response = self.client.get(
            f"/api/projects/{uuid.uuid4()}/plans/{created['id']}/pages/1/preview"
        )
        self.assertEqual(response.status_code, 404)

    def test_preview_unknown_plan_returns_404(self):
        response = self.client.get(
            f"/api/projects/{self.project_id}/plans/{uuid.uuid4()}/pages/1/preview"
        )
        self.assertEqual(response.status_code, 404)

    def test_preview_unknown_page_returns_404(self):
        created = self._upload("vector.pdf", fx.build_vector_pdf_bytes()).json()  # 1 page only
        response = self.client.get(
            f"/api/projects/{self.project_id}/plans/{created['id']}/pages/99/preview"
        )
        self.assertEqual(response.status_code, 404)

    def test_preview_cross_project_access_returns_404(self):
        """A Plan that exists but belongs to a different project must 404,
        not leak its preview -- same isolation rule already proven for
        get_plan, exercised here for the preview endpoint specifically."""
        other_project_id = ProjectService(self.session).create_project(ProjectCreate(name="Other")).id
        created = self._upload("a.pdf", fx.build_vector_pdf_bytes(), project_id=str(other_project_id)).json()
        response = self.client.get(
            f"/api/projects/{self.project_id}/plans/{created['id']}/pages/1/preview"
        )
        self.assertEqual(response.status_code, 404)

    def test_preview_response_does_not_leak_filesystem_path(self):
        """No absolute path or raw storage-root reference should ever reach
        the client -- only image bytes and a synthetic filename."""
        created = self._upload("vector.pdf", fx.build_vector_pdf_bytes()).json()
        response = self.client.get(
            f"/api/projects/{self.project_id}/plans/{created['id']}/pages/1/preview"
        )
        self.assertEqual(response.status_code, 200)
        disposition = response.headers.get("content-disposition", "")
        self.assertNotIn(str(self._tmp.name), disposition)
        self.assertNotIn("plans/", disposition)
        self.assertIn("page-1.png", disposition)


if __name__ == "__main__":
    unittest.main()
