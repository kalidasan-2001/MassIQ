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
import app.routes.plans as plans_route_module
from tests import hatch_fixtures as hfx
from tests import pdf_fixtures as fx
from tests.db_test_support import build_test_engine, new_sessionmaker, truncate_all

from app.db.database import get_db
from app.hatch.config import FEATURE_VERSION
from app.main import app
from app.schemas.project import ProjectCreate
from app.services.hatch_feature_service import HatchFeatureService
from app.services.legend_service import LegendService
from app.services.ocr_service import OcrResult, OcrService
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


class HatchFeatureRoutesTests(unittest.TestCase):
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

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[plans_route_module.get_plan_service] = _override_plan_service
        app.dependency_overrides[legend_routes_module.get_legend_service] = _override_legend_service
        app.dependency_overrides[hatch_features_route_module.get_hatch_feature_service] = _override_feature_service
        self.client = TestClient(app)

        self.legend_service = LegendService(self.session, storage=self.storage, ocr=OcrService(provider=_FakeOcrProvider()))
        project = ProjectService(self.session).create_project(ProjectCreate(name="Hatch Feature Route Test"))
        self.project_id = project.id
        plan = PlanService(self.session, storage=self.storage).upload_plan(
            project.id, "vector.pdf", fx.build_vector_pdf_bytes()
        )
        self.plan_id = plan.id

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(plans_route_module.get_plan_service, None)
        app.dependency_overrides.pop(legend_routes_module.get_legend_service, None)
        app.dependency_overrides.pop(hatch_features_route_module.get_hatch_feature_service, None)
        self.session.close()
        self._tmp.cleanup()

    def _features_base(self, project_id=None, plan_id=None, legend_entry_id=""):
        return (
            f"/api/projects/{project_id or self.project_id}/plans/{plan_id or self.plan_id}"
            f"/legend-entries/{legend_entry_id}/features"
        )

    def _confirmed_entry_id(self, pattern_image=None) -> str:
        from app.schemas.legend_entry import LegendEntryUpdate
        from app.services.legend_crop_service import RegionSelection

        entry = self.legend_service.create_draft(self.project_id, self.plan_id, page_number=1)
        confirmed = self.legend_service.save_pattern_selection(
            self.project_id, self.plan_id, entry.id, RegionSelection(x=0.05, y=0.05, width=0.2, height=0.1)
        )
        self.legend_service.save_description_selection(
            self.project_id, self.plan_id, entry.id, RegionSelection(x=0.5, y=0.5, width=0.2, height=0.1)
        )
        self.legend_service.update_entry(
            self.project_id, self.plan_id, entry.id,
            LegendEntryUpdate(corrected_text="Stahlbeton C25/30", material_name="Stahlbeton C25/30"),
        )
        confirmed = self.legend_service.confirm(self.project_id, self.plan_id, entry.id)
        if pattern_image is not None:
            crop_path = self.storage.resolve_legend_crop(confirmed.pattern_image_reference)
            crop_path.write_bytes(_encode_png(pattern_image))
        return str(confirmed.id)

    # -- POST (compute) --------------------------------------------------

    def test_compute_returns_201_with_feature_payload(self):
        entry_id = self._confirmed_entry_id(hfx.family_d_cross_hatch_45_135())
        response = self.client.post(self._features_base(legend_entry_id=entry_id) + "")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["feature_version"], FEATURE_VERSION)
        self.assertTrue(body["is_cross_hatch"])
        self.assertEqual(len(body["dominant_angles"]), 2)
        uuid.UUID(body["id"])

    def test_compute_on_draft_entry_returns_400(self):
        entry = self.legend_service.create_draft(self.project_id, self.plan_id, page_number=1)
        response = self.client.post(self._features_base(legend_entry_id=str(entry.id)))
        self.assertEqual(response.status_code, 400)

    def test_compute_unknown_entry_returns_404(self):
        response = self.client.post(self._features_base(legend_entry_id=str(uuid.uuid4())))
        self.assertEqual(response.status_code, 404)

    def test_compute_unknown_project_returns_404(self):
        entry_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        response = self.client.post(self._features_base(project_id=str(uuid.uuid4()), legend_entry_id=entry_id))
        self.assertEqual(response.status_code, 404)

    def test_compute_cross_project_access_returns_404(self):
        entry_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        other_project = ProjectService(self.session).create_project(ProjectCreate(name="Other"))
        response = self.client.post(self._features_base(project_id=str(other_project.id), legend_entry_id=entry_id))
        self.assertEqual(response.status_code, 404)

    def test_compute_with_corrupt_crop_returns_400_not_a_stack_trace(self):
        entry = self.legend_service.create_draft(self.project_id, self.plan_id, page_number=1)
        from app.schemas.legend_entry import LegendEntryUpdate
        from app.services.legend_crop_service import RegionSelection

        confirmed = self.legend_service.save_pattern_selection(
            self.project_id, self.plan_id, entry.id, RegionSelection(x=0.05, y=0.05, width=0.2, height=0.1)
        )
        self.legend_service.save_description_selection(
            self.project_id, self.plan_id, entry.id, RegionSelection(x=0.5, y=0.5, width=0.2, height=0.1)
        )
        self.legend_service.update_entry(
            self.project_id, self.plan_id, entry.id,
            LegendEntryUpdate(corrected_text="x", material_name="x"),
        )
        confirmed = self.legend_service.confirm(self.project_id, self.plan_id, entry.id)
        crop_path = self.storage.resolve_legend_crop(confirmed.pattern_image_reference)
        crop_path.write_bytes(b"not a real image")

        response = self.client.post(self._features_base(legend_entry_id=str(confirmed.id)))
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())

    def test_recompute_without_force_is_a_no_op(self):
        entry_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        first = self.client.post(self._features_base(legend_entry_id=entry_id)).json()

        crop_path = self.storage.resolve_legend_crop(
            self.legend_service.get_entry(self.project_id, self.plan_id, uuid.UUID(entry_id)).pattern_image_reference
        )
        crop_path.write_bytes(_encode_png(hfx.family_d_cross_hatch_45_135()))

        second = self.client.post(self._features_base(legend_entry_id=entry_id), json={"force": False}).json()
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["dominant_angles"], second["dominant_angles"])

    def test_recompute_with_force_updates_the_result(self):
        entry_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        first = self.client.post(self._features_base(legend_entry_id=entry_id)).json()

        crop_path = self.storage.resolve_legend_crop(
            self.legend_service.get_entry(self.project_id, self.plan_id, uuid.UUID(entry_id)).pattern_image_reference
        )
        crop_path.write_bytes(_encode_png(hfx.family_d_cross_hatch_45_135()))

        second = self.client.post(self._features_base(legend_entry_id=entry_id), json={"force": True}).json()
        self.assertEqual(first["id"], second["id"])
        self.assertTrue(second["is_cross_hatch"])

    # -- GET (retrieval) ---------------------------------------------------

    def test_get_before_compute_returns_404(self):
        entry_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        response = self.client.get(self._features_base(legend_entry_id=entry_id))
        self.assertEqual(response.status_code, 404)

    def test_get_after_compute_returns_the_persisted_result(self):
        entry_id = self._confirmed_entry_id(hfx.family_b_parallel_90())
        self.client.post(self._features_base(legend_entry_id=entry_id))
        response = self.client.get(self._features_base(legend_entry_id=entry_id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["feature_version"], FEATURE_VERSION)

    def test_get_unknown_entry_returns_404(self):
        response = self.client.get(self._features_base(legend_entry_id=str(uuid.uuid4())))
        self.assertEqual(response.status_code, 404)

    def test_no_local_filesystem_path_is_ever_exposed(self):
        entry_id = self._confirmed_entry_id(hfx.family_a_parallel_45())
        response = self.client.post(self._features_base(legend_entry_id=entry_id))
        body_text = response.text
        self.assertNotIn(str(self._tmp.name), body_text)

    def test_existing_legend_and_plan_routes_unaffected(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get(f"/api/projects/{self.project_id}").status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/projects/{self.project_id}/plans/{self.plan_id}/legend-entries").status_code, 200
        )


if __name__ == "__main__":
    unittest.main()
