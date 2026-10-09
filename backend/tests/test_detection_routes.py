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

import app.routes.detection_runs as detection_runs_route_module
import app.routes.hatch_features as hatch_features_route_module
import app.routes.legend_entries as legend_routes_module
import app.routes.pattern_library as pattern_library_route_module
import app.routes.pattern_matches as pattern_matches_route_module
import app.routes.plans as plans_route_module
from tests import detection_fixtures as df
from tests import hatch_fixtures as hfx
from tests import pdf_fixtures as fx
from tests.db_test_support import build_test_engine, new_sessionmaker, truncate_all

from app.db.database import get_db
from app.main import app
from app.models.hatch_feature_set import HatchFeatureSet
from app.schemas.legend_entry import LegendEntryUpdate
from app.schemas.project import ProjectCreate
from app.services.detection_service import DetectionService
from app.services.hatch_feature_service import HatchFeatureService
from app.services.legend_crop_service import RegionSelection
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


class DetectionRoutesTests(unittest.TestCase):
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

        def _override_detection_service() -> DetectionService:
            return DetectionService(self.session, storage=self.storage)

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[plans_route_module.get_plan_service] = _override_plan_service
        app.dependency_overrides[legend_routes_module.get_legend_service] = _override_legend_service
        app.dependency_overrides[hatch_features_route_module.get_hatch_feature_service] = _override_feature_service
        app.dependency_overrides[pattern_library_route_module.get_pattern_library_service] = _override_library_service
        app.dependency_overrides[pattern_matches_route_module.get_pattern_library_service] = _override_library_service
        app.dependency_overrides[detection_runs_route_module.get_detection_service] = _override_detection_service
        self.client = TestClient(app)

        self.legend_service = LegendService(self.session, storage=self.storage, ocr=OcrService(provider=_FakeOcrProvider()))
        self.feature_service = HatchFeatureService(self.session, storage=self.storage)
        project = ProjectService(self.session).create_project(ProjectCreate(name="Detection Route Test"))
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
            detection_runs_route_module.get_detection_service,
        ):
            app.dependency_overrides.pop(dep, None)
        self.session.close()
        self._tmp.cleanup()

    def _confirmed_reference_id(self, pattern_image, material_name="Stahlbeton C25/30") -> str:
        entry = self.legend_service.create_draft(self.project_id, self.plan_id, page_number=1)
        self.legend_service.save_pattern_selection(
            self.project_id, self.plan_id, entry.id, RegionSelection(x=0.05, y=0.05, width=0.2, height=0.1)
        )
        self.legend_service.save_description_selection(
            self.project_id, self.plan_id, entry.id, RegionSelection(x=0.5, y=0.5, width=0.2, height=0.1)
        )
        self.legend_service.update_entry(
            self.project_id, self.plan_id, entry.id,
            LegendEntryUpdate(corrected_text=f"{material_name} label", material_name=material_name),
        )
        confirmed = self.legend_service.confirm(self.project_id, self.plan_id, entry.id)
        crop_path = self.storage.resolve_legend_crop(confirmed.pattern_image_reference)
        crop_path.write_bytes(_encode_png(pattern_image))
        self.feature_service.compute_features(self.project_id, self.plan_id, confirmed.id)
        return str(confirmed.id)

    def _set_page_preview(self, page_image):
        plan_service = PlanService(self.session, storage=self.storage)
        page = plan_service.get_page(self.project_id, self.plan_id, 1)
        preview_path = self.storage.resolve_preview(page.preview_reference)
        preview_path.write_bytes(_encode_png(page_image))

    def _run_base(self, project_id=None, plan_id=None):
        return f"/api/projects/{project_id or self.project_id}/plans/{plan_id or self.plan_id}/detection-runs"

    def _page_base(self, page_number=1, project_id=None, plan_id=None):
        return (
            f"/api/projects/{project_id or self.project_id}/plans/{plan_id or self.plan_id}"
            f"/pages/{page_number}/detection-runs"
        )

    # -- start run ---------------------------------------------------

    def test_start_run_returns_201_with_completed_status(self):
        reference_id = self._confirmed_reference_id(hfx.family_a_parallel_45())
        page_image, _ = df.build_single_target_page()
        self._set_page_preview(page_image)

        response = self.client.post(self._page_base(), json={"legend_entry_id": reference_id})
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "completed")
        self.assertGreater(body["candidate_region_count"], 0)
        self.assertEqual(body["detector_version"], "1.0")
        uuid.UUID(body["id"])

    def test_start_run_without_any_reference_returns_422(self):
        response = self.client.post(self._page_base(), json={})
        self.assertEqual(response.status_code, 422)  # Pydantic model_validator rejection

    def test_start_run_with_both_references_returns_422(self):
        response = self.client.post(
            self._page_base(),
            json={"legend_entry_id": str(uuid.uuid4()), "pattern_library_entry_id": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 422)

    def test_start_run_unconfirmed_reference_returns_400(self):
        entry = self.legend_service.create_draft(self.project_id, self.plan_id, page_number=1)
        response = self.client.post(self._page_base(), json={"legend_entry_id": str(entry.id)})
        self.assertEqual(response.status_code, 400)

    def test_start_run_unknown_page_returns_404(self):
        reference_id = self._confirmed_reference_id(hfx.family_a_parallel_45())
        response = self.client.post(self._page_base(page_number=99), json={"legend_entry_id": reference_id})
        self.assertEqual(response.status_code, 404)

    def test_start_run_cross_project_returns_404_or_400(self):
        reference_id = self._confirmed_reference_id(hfx.family_a_parallel_45())
        other_project = ProjectService(self.session).create_project(ProjectCreate(name="Other"))
        response = self.client.post(
            self._page_base(project_id=other_project.id), json={"legend_entry_id": reference_id}
        )
        self.assertIn(response.status_code, (400, 404))

    def test_start_run_outdated_feature_version_returns_structured_400(self):
        """R9 section 15 -- the route must return a structured, actionable
        error (error_code + human message), not just a raw exception
        string, so the frontend can render a specific fix-it action
        instead of dumping backend internals."""
        reference_id = self._confirmed_reference_id(hfx.family_a_parallel_45())
        feature_set = self.session.query(HatchFeatureSet).filter_by(legend_entry_id=uuid.UUID(reference_id)).one()
        feature_set.feature_version = "0.9-outdated"
        self.session.commit()

        response = self.client.post(self._page_base(), json={"legend_entry_id": reference_id})
        self.assertEqual(response.status_code, 400)
        detail = response.json()["detail"]
        self.assertEqual(detail["error_code"], "REFERENCE_FEATURE_VERSION_OUTDATED")
        self.assertIn("Recompute the hatch features", detail["message"])
        self.assertEqual(detail["reference_feature_version"], "0.9-outdated")
        self.assertNotEqual(detail["current_feature_version"], "0.9-outdated")

    # -- get run / regions -----------------------------------------------

    def test_get_run_and_list_regions(self):
        reference_id = self._confirmed_reference_id(hfx.family_a_parallel_45())
        page_image, _ = df.build_multi_target_page()
        self._set_page_preview(page_image)
        created = self.client.post(self._page_base(), json={"legend_entry_id": reference_id}).json()
        run_id = created["id"]

        get_response = self.client.get(f"{self._run_base()}/{run_id}")
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["status"], "completed")

        regions_response = self.client.get(f"{self._run_base()}/{run_id}/regions")
        self.assertEqual(regions_response.status_code, 200)
        regions = regions_response.json()
        self.assertGreater(len(regions), 0)
        for region in regions:
            self.assertEqual(region["status"], "candidate")
            self.assertIn("similarity", region)
            self.assertIn("evidence_coverage", region)

    def test_get_unknown_run_returns_404(self):
        response = self.client.get(f"{self._run_base()}/{uuid.uuid4()}")
        self.assertEqual(response.status_code, 404)

    def test_run_cross_project_access_returns_404(self):
        reference_id = self._confirmed_reference_id(hfx.family_a_parallel_45())
        page_image, _ = df.build_single_target_page()
        self._set_page_preview(page_image)
        run_id = self.client.post(self._page_base(), json={"legend_entry_id": reference_id}).json()["id"]

        other_project = ProjectService(self.session).create_project(ProjectCreate(name="Other2"))
        other_plan = PlanService(self.session, storage=self.storage).upload_plan(
            other_project.id, "d.pdf", fx.build_vector_pdf_bytes()
        )
        response = self.client.get(
            f"/api/projects/{other_project.id}/plans/{other_plan.id}/detection-runs/{run_id}"
        )
        self.assertEqual(response.status_code, 404)

    # -- region review ---------------------------------------------------

    def test_accept_region(self):
        reference_id = self._confirmed_reference_id(hfx.family_a_parallel_45())
        page_image, _ = df.build_single_target_page()
        self._set_page_preview(page_image)
        run_id = self.client.post(self._page_base(), json={"legend_entry_id": reference_id}).json()["id"]
        region_id = self.client.get(f"{self._run_base()}/{run_id}/regions").json()[0]["id"]

        response = self.client.patch(
            f"{self._run_base()}/{run_id}/regions/{region_id}", json={"status": "accepted"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "accepted")

    def test_reject_region(self):
        reference_id = self._confirmed_reference_id(hfx.family_a_parallel_45())
        page_image, _ = df.build_single_target_page()
        self._set_page_preview(page_image)
        run_id = self.client.post(self._page_base(), json={"legend_entry_id": reference_id}).json()["id"]
        region_id = self.client.get(f"{self._run_base()}/{run_id}/regions").json()[0]["id"]

        response = self.client.patch(
            f"{self._run_base()}/{run_id}/regions/{region_id}", json={"status": "rejected"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "rejected")

    def test_update_unknown_region_returns_404(self):
        reference_id = self._confirmed_reference_id(hfx.family_a_parallel_45())
        page_image, _ = df.build_single_target_page()
        self._set_page_preview(page_image)
        run_id = self.client.post(self._page_base(), json={"legend_entry_id": reference_id}).json()["id"]

        response = self.client.patch(
            f"{self._run_base()}/{run_id}/regions/{uuid.uuid4()}", json={"status": "accepted"}
        )
        self.assertEqual(response.status_code, 404)

    def test_no_local_filesystem_path_is_ever_exposed(self):
        reference_id = self._confirmed_reference_id(hfx.family_a_parallel_45())
        page_image, _ = df.build_single_target_page()
        self._set_page_preview(page_image)
        response = self.client.post(self._page_base(), json={"legend_entry_id": reference_id})
        self.assertNotIn(str(self._tmp.name), response.text)

    def test_existing_routes_unaffected(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get(f"/api/projects/{self.project_id}").status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/projects/{self.project_id}/plans/{self.plan_id}/legend-entries").status_code, 200
        )


if __name__ == "__main__":
    unittest.main()
