"""API-level integration tests against a real Postgres database. Requires the
docker-compose Postgres service to be running:
    docker compose up -d postgres
"""

from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests.db_test_support import build_test_engine, new_sessionmaker, truncate_projects

from app.db.database import get_db
from app.main import app


class ProjectRoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = build_test_engine()
        cls.Session = new_sessionmaker(cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        truncate_projects(self.engine)
        self.session = self.Session()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        self.session.close()

    def test_create_project_returns_201_with_generated_fields(self):
        response = self.client.post("/api/projects", json={"name": "New Build", "description": "Test"})
        self.assertEqual(response.status_code, 201)
        body = response.json()
        uuid.UUID(body["id"])  # raises ValueError if not a valid UUID
        self.assertEqual(body["name"], "New Build")
        self.assertEqual(body["status"], "active")
        self.assertIn("created_at", body)
        self.assertIn("updated_at", body)

    def test_create_project_blank_name_returns_422(self):
        response = self.client.post("/api/projects", json={"name": "   "})
        self.assertEqual(response.status_code, 422)

    def test_create_project_missing_name_returns_422(self):
        response = self.client.post("/api/projects", json={"description": "no name"})
        self.assertEqual(response.status_code, 422)

    def test_create_project_cannot_override_id(self):
        response = self.client.post(
            "/api/projects", json={"name": "Valid", "id": "11111111-1111-1111-1111-111111111111"}
        )
        self.assertEqual(response.status_code, 422)

    def test_get_project_returns_created_project(self):
        created = self.client.post("/api/projects", json={"name": "Fetch Me"}).json()
        response = self.client.get(f"/api/projects/{created['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], created["id"])

    def test_get_unknown_project_returns_404_without_stack_trace(self):
        response = self.client.get(f"/api/projects/{uuid.uuid4()}")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("Traceback", response.text)

    def test_list_projects_returns_all_created(self):
        for name in ("List A", "List B", "List C"):
            self.client.post("/api/projects", json={"name": name})
        response = self.client.get("/api/projects")
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.json()}
        self.assertEqual(names, {"List A", "List B", "List C"})

    def test_patch_project_updates_name_and_description(self):
        created = self.client.post("/api/projects", json={"name": "Before", "description": "Before desc"}).json()
        response = self.client.patch(
            f"/api/projects/{created['id']}", json={"name": "After", "description": "After desc"}
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["name"], "After")
        self.assertEqual(body["description"], "After desc")

    def test_patch_project_partial_update_keeps_omitted_fields(self):
        created = self.client.post("/api/projects", json={"name": "Before", "description": "Keep me"}).json()
        response = self.client.patch(f"/api/projects/{created['id']}", json={"name": "After"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["description"], "Keep me")

    def test_patch_unknown_project_returns_404(self):
        response = self.client.patch(f"/api/projects/{uuid.uuid4()}", json={"name": "Doesn't matter"})
        self.assertEqual(response.status_code, 404)

    def test_existing_health_endpoint_still_registered(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)

    def test_existing_root_endpoint_still_registered(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
