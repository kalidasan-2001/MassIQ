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

import cv2
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.routes.hatch_features as hatch_features_route_module
import app.routes.legend_entries as legend_routes_module
import app.routes.pattern_library as pattern_library_route_module
import app.routes.pattern_matches as pattern_matches_route_module
import app.routes.plans as plans_route_module
from tests import hatch_fixtures as hfx
from tests import pdf_fixtures as fx
from tests.db_test_support import build_test_engine, new_sessionmaker, truncate_all

from app.db.database import get_db
from app.main import app
from app.schemas.project import ProjectCreate
from app.services.hatch_feature_service import HatchFeatureService
from app.services.legend_service import LegendService
from app.services.ocr_service import OcrResult, OcrService
from app.services.pattern_library_service import PatternLibraryService
from app.services.plan_service import PlanService
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


class PatternLibraryRoutesTests(unittest.TestCase):
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

        def _override_feature_service() -> HatchFeatureService:
            return HatchFeatureService(self.session, storage=self.storage)

        def _override_library_service() -> PatternLibraryService:
            return PatternLibraryService(self.session, storage=self.storage)

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[plans_route_module.get_plan_service] = _override_plan_service
        app.dependency_overrides[legend_routes_module.get_legend_service] = _override_legend_service
        app.dependency_overrides[hatch_features_route_module.get_hatch_feature_service] = _override_feature_service
        app.dependency_overrides[pattern_library_route_module.get_pattern_library_service] = _override_library_service
        app.dependency_overrides[pattern_matches_route_module.get_pattern_library_service] = _override_library_service
        self.client = TestClient(app)

        self.legend_service = LegendService(self.session, storage=self.storage, ocr=OcrService(provider=_FakeOcrProvider()))
        self.feature_service = HatchFeatureService(self.session, storage=self.storage)
        project = ProjectService(self.session).create_project(ProjectCreate(name="Pattern Library Route Test"))
        self.project_id = project.id
        plan = PlanService(self.session, storage=self.storage).upload_plan(
            project.id, "vector.pdf", fx.build_vector_pdf_bytes()
        )
        self.plan_id = plan.id

    def tearDown(self):
        for dep in (
            get_db,
            plans_route_module.get_plan_service,
            legend_routes_module.get_legend_service,
            hatch_features_route_module.get_hatch_feature_service,
            pattern_library_route_module.get_pattern_library_service,
            pattern_matches_route_module.get_pattern_library_service,
        ):
            app.dependency_overrides.pop(dep, None)
        self.session.close()
        self._tmp.cleanup()

    def _entry_base(self, project_id=None, plan_id=None, legend_entry_id=""):
        return (
            f"/api/projects/{project_id or self.project_id}/plans/{plan_id or self.plan_id}"
            f"/legend-entries/{legend_entry_id}"
        )

    def _confirmed_entry_id(self, pattern_image, material_name="Stahlbeton C25/30", project_id=None, plan_id=None) -> str:
        from app.schemas.legend_entry import LegendEntryUpdate
        from app.services.legend_crop_service import RegionSelection

        project_id = project_id or self.project_id
        plan_id = plan_id or self.plan_id
        entry = self.legend_service.create_draft(project_id, plan_id, page_number=1)
        self.legend_service.save_pattern_selection(
            project_id, plan_id, entry.id, RegionSelection(x=0.05, y=0.05, width=0.2, height=0.1)
        )
        self.legend_service.save_description_selection(
            project_id, plan_id, entry.id, RegionSelection(x=0.5, y=0.5, width=0.2, height=0.1)
        )
        self.legend_service.update_entry(
            project_id, plan_id, entry.id,
            LegendEntryUpdate(corrected_text=f"{material_name} label", material_name=material_name),
        )
        confirmed = self.legend_service.confirm(project_id, plan_id, entry.id)
        crop_path = self.storage.resolve_legend_crop(confirmed.pattern_image_reference)
        crop_path.write_bytes(_encode_png(pattern_image))
        return str(confirmed.id)

    def _compute_features(self, entry_id, project_id=None, plan_id=None):
        self.feature_service.compute_features(
            project_id or self.project_id, plan_id or self.plan_id, uuid.UUID(entry_id)
        )

    # -- add to library --------------------------------------------------

    def test_add_to_library_returns_201(self):
        entry_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        self._compute_features(entry_id)
        response = self.client.post(self._entry_base(legend_entry_id=entry_id) + "/library")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["canonical_material_name"], "Stahlbeton C25/30")
        self.assertEqual(body["confirmation_count"], 1)
        self.assertEqual(body["source_plan_id"], str(self.plan_id))
        uuid.UUID(body["id"])

    def test_add_to_library_without_features_returns_400(self):
        entry_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        response = self.client.post(self._entry_base(legend_entry_id=entry_id) + "/library")
        self.assertEqual(response.status_code, 400)

    def test_add_unconfirmed_entry_returns_400(self):
        entry = self.legend_service.create_draft(self.project_id, self.plan_id, page_number=1)
        response = self.client.post(self._entry_base(legend_entry_id=str(entry.id)) + "/library")
        self.assertEqual(response.status_code, 400)

    def test_readding_updates_confirmation_count(self):
        entry_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        self._compute_features(entry_id)
        first = self.client.post(self._entry_base(legend_entry_id=entry_id) + "/library")
        second = self.client.post(self._entry_base(legend_entry_id=entry_id) + "/library")
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(second.json()["confirmation_count"], 2)

    # -- listing -------------------------------------------------------

    def test_list_returns_added_entries(self):
        entry_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        self._compute_features(entry_id)
        self.client.post(self._entry_base(legend_entry_id=entry_id) + "/library")
        response = self.client.get(f"/api/projects/{self.project_id}/pattern-library")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["source_plan_id"], str(self.plan_id))

    def test_list_unknown_project_returns_404(self):
        response = self.client.get(f"/api/projects/{uuid.uuid4()}/pattern-library")
        self.assertEqual(response.status_code, 404)

    def test_list_cross_project_isolation(self):
        entry_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        self._compute_features(entry_id)
        self.client.post(self._entry_base(legend_entry_id=entry_id) + "/library")

        other_project = ProjectService(self.session).create_project(ProjectCreate(name="Other"))
        response = self.client.get(f"/api/projects/{other_project.id}/pattern-library")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    # -- matches ---------------------------------------------------------

    def test_matches_on_empty_library_returns_reason(self):
        entry_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        self._compute_features(entry_id)
        response = self.client.post(self._entry_base(legend_entry_id=entry_id) + "/matches")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["candidates"], [])
        self.assertEqual(body["reason"], "empty_library")

    def test_matches_without_features_returns_400(self):
        entry_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        response = self.client.post(self._entry_base(legend_entry_id=entry_id) + "/matches")
        self.assertEqual(response.status_code, 400)

    def test_matches_returns_ranked_candidates(self):
        query_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        self._compute_features(query_id)

        candidate_id = self._confirmed_entry_id(hfx.variant_blur(hfx.family_a_parallel_45()), material_name="Close Match")
        self._compute_features(candidate_id)
        self.client.post(self._entry_base(legend_entry_id=candidate_id) + "/library")

        response = self.client.post(self._entry_base(legend_entry_id=query_id) + "/matches")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["candidates"]), 1)
        candidate = body["candidates"][0]
        self.assertEqual(candidate["canonical_material_name"], "Close Match")
        self.assertGreater(candidate["similarity"], 0.0)
        self.assertLessEqual(candidate["similarity"], 1.0)
        self.assertIn("angle", candidate["components"])
        self.assertIn(candidate["similarity_band"], ("high", "medium", "low"))

    def test_matches_never_leak_a_filesystem_path(self):
        query_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        self._compute_features(query_id)
        candidate_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        self._compute_features(candidate_id)
        self.client.post(self._entry_base(legend_entry_id=candidate_id) + "/library")

        response = self.client.post(self._entry_base(legend_entry_id=query_id) + "/matches")
        self.assertNotIn(str(self._tmp.name), response.text)

    def test_matches_cross_project_access_returns_404(self):
        entry_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        self._compute_features(entry_id)
        other_project = ProjectService(self.session).create_project(ProjectCreate(name="Other2"))
        response = self.client.post(
            self._entry_base(project_id=other_project.id, legend_entry_id=entry_id) + "/matches"
        )
        self.assertEqual(response.status_code, 404)

    # -- decisions -------------------------------------------------------

    def test_record_and_list_decision(self):
        entry_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        self._compute_features(entry_id)
        response = self.client.post(
            self._entry_base(legend_entry_id=entry_id) + "/match-decision",
            json={"decision": "manual", "confirmed_material_name": "Stahlbeton C25/30"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["decision"], "manual")

        listed = self.client.get(self._entry_base(legend_entry_id=entry_id) + "/match-decisions")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)

    def test_decision_referencing_unknown_library_entry_returns_400(self):
        entry_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        response = self.client.post(
            self._entry_base(legend_entry_id=entry_id) + "/match-decision",
            json={
                "decision": "accepted",
                "suggested_library_entry_id": str(uuid.uuid4()),
                "similarity_at_decision": 0.9,
                "confirmed_material_name": "Stahlbeton C25/30",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_existing_r4_and_r3_routes_unaffected(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get(f"/api/projects/{self.project_id}").status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/projects/{self.project_id}/plans/{self.plan_id}/legend-entries").status_code, 200
        )


if __name__ == "__main__":
    unittest.main()
