"""API-level integration tests against a real Postgres database. Requires
the docker-compose Postgres service to be running:
    docker compose up -d postgres

Covers the R7 HTTP surface: plan-scale confirm/get, manual-corrections
create/list/delete, and quantity calculate/get/confirm -- proving the
domain-error -> HTTP-status mapping and real request/response contracts,
not just that a 200 comes back.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
import uuid
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.routes.manual_corrections as manual_corrections_route_module
import app.routes.plan_scale as plan_scale_route_module
import app.routes.quantity as quantity_route_module
from tests import hatch_fixtures as hfx
from tests import pdf_fixtures as fx
from tests.db_test_support import build_test_engine, new_sessionmaker, truncate_all

from app.db.database import get_db
from app.main import app
from app.models.detected_region import DetectedRegion, DetectedRegionStatus
from app.schemas.legend_entry import LegendEntryUpdate
from app.schemas.project import ProjectCreate
from app.services.hatch_feature_service import HatchFeatureService
from app.services.legend_crop_service import RegionSelection
from app.services.legend_service import LegendService
from app.services.manual_correction_service import ManualCorrectionService
from app.services.ocr_service import OcrResult, OcrService
from app.services.plan_scale_service import PlanScaleService
from app.services.plan_service import PlanService
from app.services.project_service import ProjectService
from app.services.quantity_service import QuantityService
from app.services.storage_service import StorageService


class _FakeOcrProvider:
    name = "fake"

    def extract_text(self, image_path):
        return OcrResult(text="Stahlbeton C25/30", provider=self.name, confidence=0.9)


def _encode_png(image) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return buffer.tobytes()


class ReviewQuantityRoutesTests(unittest.TestCase):
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

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[manual_corrections_route_module.get_manual_correction_service] = (
            lambda: ManualCorrectionService(self.session, storage=self.storage)
        )
        app.dependency_overrides[plan_scale_route_module.get_plan_scale_service] = (
            lambda: PlanScaleService(self.session, storage=self.storage)
        )
        app.dependency_overrides[quantity_route_module.get_quantity_service] = (
            lambda: QuantityService(self.session, storage=self.storage)
        )

        self.client = TestClient(app)

        self.project_service = ProjectService(self.session)
        self.plan_service = PlanService(self.session, storage=self.storage)
        self.legend_service = LegendService(self.session, storage=self.storage, ocr=OcrService(provider=_FakeOcrProvider()))
        self.feature_service = HatchFeatureService(self.session, storage=self.storage)

        self.project = self.project_service.create_project(ProjectCreate(name="Route Test Project"))
        self.plan = self.plan_service.upload_plan(self.project.id, "vector.pdf", fx.build_vector_pdf_bytes())
        self.run = self._make_completed_run()

    def tearDown(self):
        app.dependency_overrides.clear()
        self.session.close()
        self._tmp.cleanup()

    def _make_completed_run(self):
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

        crop_path = self.storage.resolve_legend_crop(confirmed.pattern_image_reference)
        crop_path.write_bytes(_encode_png(hfx.family_a_parallel_45()))
        self.feature_service.compute_features(self.project.id, self.plan.id, confirmed.id)

        page = self.plan_service.get_page(self.project.id, self.plan.id, 1)
        preview_path = self.storage.resolve_preview(page.preview_reference)
        preview_path.write_bytes(_encode_png(np.full((700, 900, 3), 255, dtype=np.uint8)))

        from app.services.detection_service import DetectionService

        detection_service = DetectionService(self.session, storage=self.storage)
        return detection_service.start_run(self.project.id, self.plan.id, 1, legend_entry_id=confirmed.id)

    def _urls(self):
        base = f"/api/projects/{self.project.id}/plans/{self.plan.id}"
        return {
            "scale": f"{base}/pages/1/scale",
            "corrections": f"{base}/detection-runs/{self.run.id}/manual-corrections",
            "quantity": f"{base}/detection-runs/{self.run.id}/quantity",
        }

    # -- Plan scale -----------------------------------------------------

    def test_get_scale_before_confirm_is_404(self):
        response = self.client.get(self._urls()["scale"])
        self.assertEqual(response.status_code, 404)

    def test_confirm_declared_scale_then_get(self):
        urls = self._urls()
        response = self.client.put(urls["scale"], json={"method": "declared_scale", "declared_ratio": 100})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["method"], "declared_scale")
        self.assertGreater(body["real_meters_per_plan_point"], 0)

        fetched = self.client.get(urls["scale"])
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["id"], body["id"])

    def test_confirm_scale_missing_required_fields_is_422(self):
        response = self.client.put(self._urls()["scale"], json={"method": "declared_scale"})
        self.assertEqual(response.status_code, 422)

    def test_confirm_invalid_declared_ratio_is_400(self):
        response = self.client.put(
            self._urls()["scale"], json={"method": "declared_scale", "declared_ratio": -5}
        )
        self.assertIn(response.status_code, (400, 422))

    # -- Manual corrections -----------------------------------------------

    def test_create_list_delete_manual_correction(self):
        urls = self._urls()
        create = self.client.post(
            urls["corrections"], json={"correction_type": "add", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1}
        )
        self.assertEqual(create.status_code, 201)
        correction_id = create.json()["id"]

        listed = self.client.get(urls["corrections"])
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)

        deleted = self.client.delete(f"{urls['corrections']}/{correction_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get(urls["corrections"]).json(), [])

    def test_create_manual_correction_invalid_geometry_is_400(self):
        response = self.client.post(
            self._urls()["corrections"], json={"correction_type": "add", "x": 0.9, "y": 0, "width": 0.5, "height": 0.1}
        )
        self.assertEqual(response.status_code, 400)

    def test_create_manual_correction_zero_area_is_422(self):
        response = self.client.post(
            self._urls()["corrections"], json={"correction_type": "add", "x": 0, "y": 0, "width": 0, "height": 0.1}
        )
        self.assertEqual(response.status_code, 422)

    def test_manual_correction_cross_project_run_is_404(self):
        other_project = self.project_service.create_project(ProjectCreate(name="Other"))
        other_plan = self.plan_service.upload_plan(other_project.id, "b.pdf", fx.build_vector_pdf_bytes())
        url = f"/api/projects/{other_project.id}/plans/{other_plan.id}/detection-runs/{self.run.id}/manual-corrections"
        response = self.client.post(url, json={"correction_type": "add", "x": 0, "y": 0, "width": 0.1, "height": 0.1})
        self.assertEqual(response.status_code, 404)

    # -- Quantity -----------------------------------------------------------

    def test_calculate_quantity_without_scale_is_400(self):
        self.session.add(
            DetectedRegion(
                detection_run_id=self.run.id, x=0, y=0, width=0.1, height=0.1,
                similarity=0.9, evidence_coverage=0.9, tile_count=1, status=DetectedRegionStatus.ACCEPTED,
            )
        )
        self.session.commit()
        response = self.client.post(self._urls()["quantity"], json={"confirmed_dimension_m": 2.0})
        self.assertEqual(response.status_code, 400)

    def test_calculate_quantity_invalid_dimension_is_422(self):
        response = self.client.post(self._urls()["quantity"], json={"confirmed_dimension_m": -1})
        self.assertEqual(response.status_code, 422)

    def test_full_calculate_get_confirm_flow(self):
        urls = self._urls()
        self.client.put(urls["scale"], json={"method": "declared_scale", "declared_ratio": 100})
        self.session.add(
            DetectedRegion(
                detection_run_id=self.run.id, x=0, y=0, width=0.1, height=0.1,
                similarity=0.9, evidence_coverage=0.9, tile_count=1, status=DetectedRegionStatus.ACCEPTED,
            )
        )
        self.session.commit()

        calc = self.client.post(urls["quantity"], json={"confirmed_dimension_m": 2.0})
        self.assertEqual(calc.status_code, 200)
        body = calc.json()
        self.assertGreater(body["final_area_m2"], 0)
        self.assertEqual(body["status"], "draft")
        self.assertEqual(body["accepted_region_count"], 1)

        fetched = self.client.get(urls["quantity"])
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["id"], body["id"])

        confirmed = self.client.post(f"{urls['quantity']}/confirm")
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json()["status"], "confirmed")

    def test_get_quantity_before_calculation_is_404(self):
        response = self.client.get(self._urls()["quantity"])
        self.assertEqual(response.status_code, 404)

    def test_quantity_cross_project_run_is_404(self):
        other_project = self.project_service.create_project(ProjectCreate(name="Other"))
        other_plan = self.plan_service.upload_plan(other_project.id, "b.pdf", fx.build_vector_pdf_bytes())
        url = f"/api/projects/{other_project.id}/plans/{other_plan.id}/detection-runs/{self.run.id}/quantity"
        response = self.client.post(url, json={"confirmed_dimension_m": 1.0})
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
