"""Integration tests against a real Postgres database (see db_test_support.py)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests import pdf_fixtures as fx
from tests.db_test_support import build_test_engine, new_sessionmaker, truncate_all

from app.models.plan_scale import PlanScaleMethod
from app.schemas.project import ProjectCreate
from app.services.plan_scale_service import InvalidScaleError, PlanScaleNotFoundError, PlanScaleService
from app.services.plan_service import PlanService
from app.services.project_service import ProjectService


class PlanScaleServiceTests(unittest.TestCase):
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
        self.project_service = ProjectService(self.session)
        self.plan_service = PlanService(self.session)
        self.scale_service = PlanScaleService(self.session)
        self.project = self.project_service.create_project(ProjectCreate(name="Scale Test Project"))
        self.plan = self.plan_service.upload_plan(self.project.id, "vector.pdf", fx.build_vector_pdf_bytes())

    def tearDown(self):
        self.session.close()

    def test_no_scale_raises_not_found(self):
        with self.assertRaises(PlanScaleNotFoundError):
            self.scale_service.get_scale(self.project.id, self.plan.id, 1)
        self.assertIsNone(self.scale_service.get_scale_or_none(self.project.id, self.plan.id, 1))

    def test_declared_scale_derives_real_meters_per_plan_point(self):
        scale = self.scale_service.confirm_declared_scale(self.project.id, self.plan.id, 1, declared_ratio=100)
        self.assertEqual(scale.method, PlanScaleMethod.DECLARED_SCALE)
        self.assertEqual(scale.declared_ratio, 100)
        # 1 point = 1/72 inch = 0.0254/72 m; * 100 ratio.
        expected = (0.0254 / 72.0) * 100
        self.assertAlmostEqual(scale.real_meters_per_plan_point, expected, places=9)
        self.assertIsNotNone(scale.confirmed_at)

    def test_calibrated_distance_derives_real_meters_per_plan_point(self):
        scale = self.scale_service.confirm_calibrated_distance(
            self.project.id, self.plan.id, 1,
            calibrated_distance_plan_points=50.0,
            calibrated_distance_real_m=5.0,
        )
        self.assertEqual(scale.method, PlanScaleMethod.CALIBRATED_DISTANCE)
        self.assertAlmostEqual(scale.real_meters_per_plan_point, 0.1, places=9)

    def test_invalid_declared_ratio_raises(self):
        for bad in (0, -5, float("nan"), None):
            with self.assertRaises(InvalidScaleError):
                self.scale_service.confirm_declared_scale(self.project.id, self.plan.id, 1, declared_ratio=bad)

    def test_invalid_calibrated_distance_raises(self):
        with self.assertRaises(InvalidScaleError):
            self.scale_service.confirm_calibrated_distance(
                self.project.id, self.plan.id, 1,
                calibrated_distance_plan_points=0,
                calibrated_distance_real_m=5.0,
            )
        with self.assertRaises(InvalidScaleError):
            self.scale_service.confirm_calibrated_distance(
                self.project.id, self.plan.id, 1,
                calibrated_distance_plan_points=50.0,
                calibrated_distance_real_m=-1.0,
            )

    def test_reconfirming_replaces_the_existing_row_not_a_duplicate(self):
        first = self.scale_service.confirm_declared_scale(self.project.id, self.plan.id, 1, declared_ratio=100)
        second = self.scale_service.confirm_calibrated_distance(
            self.project.id, self.plan.id, 1,
            calibrated_distance_plan_points=10.0,
            calibrated_distance_real_m=1.0,
        )
        self.assertEqual(first.id, second.id)
        current = self.scale_service.get_scale(self.project.id, self.plan.id, 1)
        self.assertEqual(current.method, PlanScaleMethod.CALIBRATED_DISTANCE)

    def test_scale_persists_across_a_fresh_session(self):
        self.scale_service.confirm_declared_scale(self.project.id, self.plan.id, 1, declared_ratio=50)
        fresh_session = self.Session()
        try:
            fresh_service = PlanScaleService(fresh_session)
            scale = fresh_service.get_scale(self.project.id, self.plan.id, 1)
            self.assertEqual(scale.declared_ratio, 50)
        finally:
            fresh_session.close()

    def test_cross_project_page_is_not_found(self):
        other_project = self.project_service.create_project(ProjectCreate(name="Other"))
        other_plan = self.plan_service.upload_plan(other_project.id, "b.pdf", fx.build_vector_pdf_bytes())
        self.scale_service.confirm_declared_scale(self.project.id, self.plan.id, 1, declared_ratio=100)
        # Confirming against a DIFFERENT project/plan's page 1 must create
        # its own independent row, never touch the first project's scale.
        self.scale_service.confirm_declared_scale(other_project.id, other_plan.id, 1, declared_ratio=200)
        first = self.scale_service.get_scale(self.project.id, self.plan.id, 1)
        second = self.scale_service.get_scale(other_project.id, other_plan.id, 1)
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(first.declared_ratio, 100)
        self.assertEqual(second.declared_ratio, 200)


if __name__ == "__main__":
    unittest.main()
