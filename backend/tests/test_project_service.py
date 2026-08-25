"""Integration tests against a real Postgres database (see db_test_support.py).
Requires the docker-compose Postgres service to be running:
    docker compose up -d postgres
"""

from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests.db_test_support import build_test_engine, new_sessionmaker, test_database_url, truncate_projects

from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.project_service import ProjectNotFoundError, ProjectService


class ProjectServiceTests(unittest.TestCase):
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
        self.service = ProjectService(self.session)

    def tearDown(self):
        self.session.close()

    def test_create_project_generates_uuid_name_timestamps_and_default_status(self):
        project = self.service.create_project(ProjectCreate(name="Warehouse Extension"))
        self.assertIsInstance(project.id, uuid.UUID)
        self.assertEqual(project.name, "Warehouse Extension")
        self.assertIsNone(project.description)
        self.assertEqual(project.status.value, "active")
        self.assertIsNotNone(project.created_at)
        self.assertIsNotNone(project.updated_at)

    def test_get_project_returns_created_project(self):
        created = self.service.create_project(ProjectCreate(name="Retrieve Me"))
        fetched = self.service.get_project(created.id)
        self.assertEqual(fetched.id, created.id)
        self.assertEqual(fetched.name, "Retrieve Me")

    def test_get_unknown_project_raises_not_found(self):
        with self.assertRaises(ProjectNotFoundError):
            self.service.get_project(uuid.uuid4())

    def test_list_projects_returns_all_created(self):
        names = {"Project A", "Project B", "Project C"}
        for name in names:
            self.service.create_project(ProjectCreate(name=name))
        listed = self.service.list_projects()
        self.assertEqual({p.name for p in listed}, names)

    def test_update_project_name_and_description_persist(self):
        created = self.service.create_project(ProjectCreate(name="Old Name", description="Old description"))
        updated = self.service.update_project(
            created.id, ProjectUpdate(name="New Name", description="New description")
        )
        self.assertEqual(updated.name, "New Name")
        self.assertEqual(updated.description, "New description")
        refetched = self.service.get_project(created.id)
        self.assertEqual(refetched.name, "New Name")
        self.assertEqual(refetched.description, "New description")

    def test_partial_update_does_not_clear_omitted_fields(self):
        created = self.service.create_project(ProjectCreate(name="Keep Description", description="Keep me"))
        updated = self.service.update_project(created.id, ProjectUpdate(name="Renamed"))
        self.assertEqual(updated.name, "Renamed")
        self.assertEqual(updated.description, "Keep me")

    def test_update_unknown_project_raises_not_found(self):
        with self.assertRaises(ProjectNotFoundError):
            self.service.update_project(uuid.uuid4(), ProjectUpdate(name="Doesn't matter"))

    def test_project_persists_across_a_brand_new_engine_and_session(self):
        """Persistence proof at the SQLAlchemy layer: data written through one
        engine/session must be visible through a completely independent
        second engine/session against the same database -- not merely
        re-readable from this test's own identity map/cache. The full
        cross-process proof (separate `python` invocations) is captured in
        docs/releases/R1_PROJECT_PERSISTENCE_CHECKLIST.md.
        """
        created = self.service.create_project(ProjectCreate(name="Survives Restart"))
        self.session.close()

        from sqlalchemy import create_engine

        fresh_engine = create_engine(test_database_url(), future=True)
        try:
            fresh_session = new_sessionmaker(fresh_engine)()
            try:
                fresh_service = ProjectService(fresh_session)
                reloaded = fresh_service.get_project(created.id)
                self.assertEqual(reloaded.id, created.id)
                self.assertEqual(reloaded.name, "Survives Restart")
            finally:
                fresh_session.close()
        finally:
            fresh_engine.dispose()


if __name__ == "__main__":
    unittest.main()
