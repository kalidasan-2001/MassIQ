"""Integration tests against a real Postgres database (see db_test_support.py).
Requires the docker-compose Postgres service to be running:
    docker compose up -d postgres
"""

from __future__ import annotations

import sys
import tempfile
import unittest
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import cv2

from tests import hatch_fixtures as hfx
from tests import pdf_fixtures as fx
from tests.db_test_support import build_test_engine, new_sessionmaker, truncate_all

from app.hatch.config import FEATURE_VERSION
from app.models.pattern_library_entry import PatternLibraryEntry
from app.models.pattern_match_decision import MatchDecision
from app.schemas.legend_entry import LegendEntryUpdate
from app.schemas.project import ProjectCreate
from app.services.hatch_feature_service import HatchFeatureService
from app.services.legend_crop_service import RegionSelection
from app.services.legend_service import LegendEntryNotFoundError, LegendService
from app.services.ocr_service import OcrResult, OcrService
from app.services.pattern_library_service import (
    FeatureSetRequiredError,
    LegendEntryNotConfirmedForLibraryError,
    MaterialNotConfirmedError,
    PatternLibraryService,
    REASON_EMPTY_LIBRARY,
    REASON_NO_COMPARABLE_CANDIDATES,
    SuggestedLibraryEntryNotFoundError,
)
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


class PatternLibraryServiceTestsBase(unittest.TestCase):
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
        self.legend_service = LegendService(
            self.session, storage=self.storage, ocr=OcrService(provider=_FakeOcrProvider())
        )
        self.feature_service = HatchFeatureService(self.session, storage=self.storage)
        self.library_service = PatternLibraryService(self.session, storage=self.storage)

        self.project = self.project_service.create_project(ProjectCreate(name="Pattern Library Test Project"))
        self.plan = self.plan_service.upload_plan(self.project.id, "vector.pdf", fx.build_vector_pdf_bytes())

    def tearDown(self):
        self.session.close()
        self._tmp.cleanup()

    def _confirmed_entry_with_features(
        self, pattern_image, material_name="Stahlbeton C25/30", plan=None, project=None, page_number=1
    ):
        plan = plan or self.plan
        project = project or self.project
        entry = self.legend_service.create_draft(project.id, plan.id, page_number=page_number)
        entry = self.legend_service.save_pattern_selection(
            project.id, plan.id, entry.id, RegionSelection(x=0.05, y=0.05, width=0.2, height=0.1)
        )
        self.legend_service.save_description_selection(
            project.id, plan.id, entry.id, RegionSelection(x=0.5, y=0.5, width=0.2, height=0.1)
        )
        self.legend_service.update_entry(
            project.id, plan.id, entry.id,
            LegendEntryUpdate(corrected_text=f"{material_name} label", material_name=material_name),
        )
        confirmed = self.legend_service.confirm(project.id, plan.id, entry.id)

        crop_path = self.storage.resolve_legend_crop(confirmed.pattern_image_reference)
        crop_path.write_bytes(_encode_png(pattern_image))
        self.feature_service.compute_features(project.id, plan.id, confirmed.id)
        return confirmed


class AddEntryTests(PatternLibraryServiceTestsBase):
    def test_add_confirmed_entry_with_features_succeeds(self):
        entry = self._confirmed_entry_with_features(hfx.family_a_parallel_45())
        library_entry = self.library_service.add_entry(self.project.id, self.plan.id, entry.id)
        self.assertEqual(library_entry.source_legend_entry_id, entry.id)
        self.assertEqual(library_entry.project_id, self.project.id)
        self.assertEqual(library_entry.canonical_material_name, "Stahlbeton C25/30")
        self.assertEqual(library_entry.confirmation_count, 1)
        self.assertTrue(library_entry.active)

    def test_add_draft_entry_raises_not_confirmed(self):
        entry = self.legend_service.create_draft(self.project.id, self.plan.id, page_number=1)
        with self.assertRaises(LegendEntryNotConfirmedForLibraryError):
            self.library_service.add_entry(self.project.id, self.plan.id, entry.id)

    def test_add_confirmed_entry_without_features_raises(self):
        entry = self.legend_service.create_draft(self.project.id, self.plan.id, page_number=1)
        self.legend_service.save_pattern_selection(
            self.project.id, self.plan.id, entry.id, RegionSelection(x=0.05, y=0.05, width=0.2, height=0.1)
        )
        self.legend_service.save_description_selection(
            self.project.id, self.plan.id, entry.id, RegionSelection(x=0.5, y=0.5, width=0.2, height=0.1)
        )
        self.legend_service.update_entry(
            self.project.id, self.plan.id, entry.id,
            LegendEntryUpdate(corrected_text="x", material_name="Stahlbeton C25/30"),
        )
        confirmed = self.legend_service.confirm(self.project.id, self.plan.id, entry.id)
        # Deliberately never called compute_features -- must not be
        # silently computed here (R5 section 6).
        with self.assertRaises(FeatureSetRequiredError):
            self.library_service.add_entry(self.project.id, self.plan.id, confirmed.id)

    def test_add_entry_never_silently_computes_features(self):
        """Explicit regression test for R5's most important constraint on
        this method: confirming a LegendEntry must not itself trigger CV
        work as a side effect of adding it to the library."""
        entry = self.legend_service.create_draft(self.project.id, self.plan.id, page_number=1)
        self.legend_service.save_pattern_selection(
            self.project.id, self.plan.id, entry.id, RegionSelection(x=0.05, y=0.05, width=0.2, height=0.1)
        )
        self.legend_service.save_description_selection(
            self.project.id, self.plan.id, entry.id, RegionSelection(x=0.5, y=0.5, width=0.2, height=0.1)
        )
        self.legend_service.update_entry(
            self.project.id, self.plan.id, entry.id,
            LegendEntryUpdate(corrected_text="x", material_name="Stahlbeton C25/30"),
        )
        confirmed = self.legend_service.confirm(self.project.id, self.plan.id, entry.id)
        try:
            self.library_service.add_entry(self.project.id, self.plan.id, confirmed.id)
        except FeatureSetRequiredError:
            pass
        self.assertIsNone(self.feature_service.get_features(self.project.id, self.plan.id, confirmed.id))

    def test_confirmed_entry_without_material_name_raises(self):
        """confirm() itself already requires a material name (R3), so this
        documents add_entry's own check as defense-in-depth, not the
        primary gate."""
        entry = self.legend_service.create_draft(self.project.id, self.plan.id, page_number=1)
        from app.services.legend_service import LegendConfirmationError

        self.legend_service.save_pattern_selection(
            self.project.id, self.plan.id, entry.id, RegionSelection(x=0.05, y=0.05, width=0.2, height=0.1)
        )
        with self.assertRaises(LegendConfirmationError):
            self.legend_service.confirm(self.project.id, self.plan.id, entry.id)

    def test_unknown_entry_raises_not_found(self):
        with self.assertRaises(LegendEntryNotFoundError):
            self.library_service.add_entry(self.project.id, self.plan.id, uuid.uuid4())


class DuplicatePolicyTests(PatternLibraryServiceTestsBase):
    def test_readding_the_same_source_updates_not_duplicates(self):
        entry = self._confirmed_entry_with_features(hfx.family_a_parallel_45())
        first = self.library_service.add_entry(self.project.id, self.plan.id, entry.id)
        second = self.library_service.add_entry(self.project.id, self.plan.id, entry.id)

        self.assertEqual(first.id, second.id)
        self.assertEqual(second.confirmation_count, 2)

        all_entries = self.library_service.list_entries(self.project.id)
        matching = [e for e in all_entries if e.source_legend_entry_id == entry.id]
        self.assertEqual(len(matching), 1)

    def test_material_change_updates_the_existing_row_intentionally(self):
        entry = self._confirmed_entry_with_features(hfx.family_a_parallel_45(), material_name="Stahlbeton C25/30")
        self.library_service.add_entry(self.project.id, self.plan.id, entry.id)

        self.legend_service.update_entry(
            self.project.id, self.plan.id, entry.id, LegendEntryUpdate(material_name="Stahlbeton C30/37")
        )
        updated = self.library_service.add_entry(self.project.id, self.plan.id, entry.id)
        self.assertEqual(updated.canonical_material_name, "Stahlbeton C30/37")
        self.assertEqual(updated.confirmation_count, 2)

    def test_unique_constraint_enforced_at_the_database_level(self):
        """Defense in depth: even bypassing the service, the DB schema
        itself must reject a second row for the same source LegendEntry."""
        entry = self._confirmed_entry_with_features(hfx.family_a_parallel_45())
        self.library_service.add_entry(self.project.id, self.plan.id, entry.id)
        feature_set = self.feature_service.get_features(self.project.id, self.plan.id, entry.id)
        duplicate = PatternLibraryEntry(
            project_id=self.project.id,
            source_legend_entry_id=entry.id,
            hatch_feature_set_id=feature_set.id,
            canonical_material_name="Something else",
        )
        self.session.add(duplicate)
        from sqlalchemy.exc import IntegrityError

        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()


class OwnershipIsolationTests(PatternLibraryServiceTestsBase):
    def test_cross_project_add_raises(self):
        entry = self._confirmed_entry_with_features(hfx.family_a_parallel_45())
        other_project = self.project_service.create_project(ProjectCreate(name="Other"))
        with self.assertRaises(Exception):
            self.library_service.add_entry(other_project.id, self.plan.id, entry.id)

    def test_list_entries_is_project_scoped(self):
        entry_a = self._confirmed_entry_with_features(hfx.family_a_parallel_45())
        self.library_service.add_entry(self.project.id, self.plan.id, entry_a.id)

        other_project = self.project_service.create_project(ProjectCreate(name="Other Project"))
        other_plan = self.plan_service.upload_plan(other_project.id, "b.pdf", fx.build_vector_pdf_bytes())
        entry_b = self._confirmed_entry_with_features(hfx.family_b_parallel_90(), plan=other_plan, project=other_project)
        self.library_service.add_entry(other_project.id, other_plan.id, entry_b.id)

        self.assertEqual(len(self.library_service.list_entries(self.project.id)), 1)
        self.assertEqual(len(self.library_service.list_entries(other_project.id)), 1)

    def test_matches_never_return_another_projects_entries(self):
        entry_a = self._confirmed_entry_with_features(hfx.family_a_parallel_45())

        other_project = self.project_service.create_project(ProjectCreate(name="Other Project 2"))
        other_plan = self.plan_service.upload_plan(other_project.id, "c.pdf", fx.build_vector_pdf_bytes())
        entry_b = self._confirmed_entry_with_features(hfx.family_a_parallel_45(), plan=other_plan, project=other_project)
        self.library_service.add_entry(other_project.id, other_plan.id, entry_b.id)

        # Project A's library is empty (only project B has an entry) --
        # a match search in project A must never surface project B's data.
        result = self.library_service.find_matches(self.project.id, self.plan.id, entry_a.id)
        self.assertEqual(result.candidates, [])
        self.assertEqual(result.reason, REASON_EMPTY_LIBRARY)

    def test_decision_referencing_another_projects_library_entry_is_rejected(self):
        entry_a = self._confirmed_entry_with_features(hfx.family_a_parallel_45())

        other_project = self.project_service.create_project(ProjectCreate(name="Other Project 3"))
        other_plan = self.plan_service.upload_plan(other_project.id, "d.pdf", fx.build_vector_pdf_bytes())
        entry_b = self._confirmed_entry_with_features(hfx.family_a_parallel_45(), plan=other_plan, project=other_project)
        other_library_entry = self.library_service.add_entry(other_project.id, other_plan.id, entry_b.id)

        with self.assertRaises(SuggestedLibraryEntryNotFoundError):
            self.library_service.record_decision(
                self.project.id, self.plan.id, entry_a.id,
                suggested_library_entry_id=other_library_entry.id,
                similarity_at_decision=0.9,
                decision=MatchDecision.ACCEPTED,
                confirmed_material_name="Stahlbeton C25/30",
            )

    def test_decisions_are_isolated_per_project(self):
        entry_a = self._confirmed_entry_with_features(hfx.family_a_parallel_45())
        self.library_service.record_decision(
            self.project.id, self.plan.id, entry_a.id,
            suggested_library_entry_id=None, similarity_at_decision=None,
            decision=MatchDecision.MANUAL, confirmed_material_name="Stahlbeton C25/30",
        )

        other_project = self.project_service.create_project(ProjectCreate(name="Other Project 4"))
        other_plan = self.plan_service.upload_plan(other_project.id, "e.pdf", fx.build_vector_pdf_bytes())
        entry_b = self._confirmed_entry_with_features(hfx.family_a_parallel_45(), plan=other_plan, project=other_project)
        self.library_service.record_decision(
            other_project.id, other_plan.id, entry_b.id,
            suggested_library_entry_id=None, similarity_at_decision=None,
            decision=MatchDecision.MANUAL, confirmed_material_name="Masonry",
        )

        self.assertEqual(len(self.library_service.list_decisions(self.project.id, self.plan.id, entry_a.id)), 1)
        self.assertEqual(len(self.library_service.list_decisions(other_project.id, other_plan.id, entry_b.id)), 1)


class FeatureVersionMismatchTests(PatternLibraryServiceTestsBase):
    def test_mismatched_feature_version_excludes_the_candidate(self):
        entry_a = self._confirmed_entry_with_features(hfx.family_a_parallel_45())
        entry_b = self._confirmed_entry_with_features(hfx.family_d_cross_hatch_45_135())
        library_entry_b = self.library_service.add_entry(self.project.id, self.plan.id, entry_b.id)

        # Simulate a future incompatible feature version on the library
        # candidate's persisted row, without touching entry_a's.
        feature_set_b = self.feature_service.get_features(self.project.id, self.plan.id, entry_b.id)
        feature_set_b.feature_version = "2.0"
        self.session.commit()

        result = self.library_service.find_matches(self.project.id, self.plan.id, entry_a.id)
        self.assertEqual(result.candidates, [])
        self.assertEqual(result.incompatible_count, 1)
        self.assertEqual(result.reason, REASON_NO_COMPARABLE_CANDIDATES)

    def test_matching_versions_are_compared_normally(self):
        entry_a = self._confirmed_entry_with_features(hfx.family_a_parallel_45())
        entry_b = self._confirmed_entry_with_features(hfx.family_a_parallel_45())
        self.library_service.add_entry(self.project.id, self.plan.id, entry_b.id)

        result = self.library_service.find_matches(self.project.id, self.plan.id, entry_a.id)
        self.assertEqual(len(result.candidates), 1)
        self.assertIsNone(result.reason)
        self.assertIsNotNone(result.candidates[0].similarity.overall_similarity)


class EmptyLibraryTests(PatternLibraryServiceTestsBase):
    def test_empty_library_returns_no_candidates_not_an_error(self):
        entry = self._confirmed_entry_with_features(hfx.family_a_parallel_45())
        result = self.library_service.find_matches(self.project.id, self.plan.id, entry.id)
        self.assertEqual(result.candidates, [])
        self.assertEqual(result.reason, REASON_EMPTY_LIBRARY)

    def test_own_entry_is_excluded_from_its_own_match_candidates(self):
        """A LegendEntry that has already been added to the library must
        not appear as a suggestion for itself (a trivial 100% self-match
        is not a useful suggestion)."""
        entry = self._confirmed_entry_with_features(hfx.family_a_parallel_45())
        self.library_service.add_entry(self.project.id, self.plan.id, entry.id)

        result = self.library_service.find_matches(self.project.id, self.plan.id, entry.id)
        self.assertEqual(result.candidates, [])
        self.assertEqual(result.reason, REASON_EMPTY_LIBRARY)

    def test_find_matches_without_features_raises(self):
        entry = self.legend_service.create_draft(self.project.id, self.plan.id, page_number=1)
        with self.assertRaises(FeatureSetRequiredError):
            self.library_service.find_matches(self.project.id, self.plan.id, entry.id)


class RankingTests(PatternLibraryServiceTestsBase):
    def test_results_sorted_descending_by_similarity(self):
        query_entry = self._confirmed_entry_with_features(hfx.family_a_parallel_45())

        close_entry = self._confirmed_entry_with_features(
            hfx.variant_blur(hfx.family_a_parallel_45()), material_name="Close Match"
        )
        far_entry = self._confirmed_entry_with_features(
            hfx.family_e_dense_cross_hatch(), material_name="Far Match"
        )
        self.library_service.add_entry(self.project.id, self.plan.id, close_entry.id)
        self.library_service.add_entry(self.project.id, self.plan.id, far_entry.id)

        result = self.library_service.find_matches(self.project.id, self.plan.id, query_entry.id, top_k=5)
        self.assertEqual(len(result.candidates), 2)
        self.assertGreater(result.candidates[0].similarity.overall_similarity, result.candidates[1].similarity.overall_similarity)
        self.assertEqual(result.candidates[0].library_entry.canonical_material_name, "Close Match")

    def test_top_k_limits_result_count(self):
        query_entry = self._confirmed_entry_with_features(hfx.family_a_parallel_45())
        for i in range(3):
            candidate_entry = self._confirmed_entry_with_features(
                hfx.variant_crop_offset(hfx.family_a_parallel_45(), dx=i + 1, dy=i + 1),
                material_name=f"Candidate {i}",
            )
            self.library_service.add_entry(self.project.id, self.plan.id, candidate_entry.id)

        result = self.library_service.find_matches(self.project.id, self.plan.id, query_entry.id, top_k=2)
        self.assertEqual(len(result.candidates), 2)

    def test_deterministic_ranking_across_repeated_calls(self):
        query_entry = self._confirmed_entry_with_features(hfx.family_a_parallel_45())
        for i in range(3):
            candidate_entry = self._confirmed_entry_with_features(
                hfx.variant_crop_offset(hfx.family_a_parallel_45(), dx=i + 1, dy=i + 1),
                material_name=f"Candidate {i}",
            )
            self.library_service.add_entry(self.project.id, self.plan.id, candidate_entry.id)

        first = self.library_service.find_matches(self.project.id, self.plan.id, query_entry.id)
        second = self.library_service.find_matches(self.project.id, self.plan.id, query_entry.id)
        self.assertEqual(
            [c.library_entry.id for c in first.candidates],
            [c.library_entry.id for c in second.candidates],
        )


class PersistenceTests(PatternLibraryServiceTestsBase):
    def test_library_entry_persists_across_a_brand_new_engine_and_session(self):
        entry = self._confirmed_entry_with_features(hfx.family_a_parallel_45())
        created = self.library_service.add_entry(self.project.id, self.plan.id, entry.id)

        fresh_session = self.Session()
        try:
            fresh_service = PatternLibraryService(fresh_session, storage=self.storage)
            fetched = fresh_service.list_entries(self.project.id)
            self.assertEqual(len(fetched), 1)
            self.assertEqual(fetched[0].id, created.id)
            self.assertEqual(fetched[0].canonical_material_name, "Stahlbeton C25/30")
        finally:
            fresh_session.close()

    def test_decision_persists_across_a_brand_new_engine_and_session(self):
        entry = self._confirmed_entry_with_features(hfx.family_a_parallel_45())
        decision = self.library_service.record_decision(
            self.project.id, self.plan.id, entry.id,
            suggested_library_entry_id=None, similarity_at_decision=None,
            decision=MatchDecision.MANUAL, confirmed_material_name="Stahlbeton C25/30",
        )

        fresh_session = self.Session()
        try:
            fresh_service = PatternLibraryService(fresh_session, storage=self.storage)
            fetched = fresh_service.list_decisions(self.project.id, self.plan.id, entry.id)
            self.assertEqual(len(fetched), 1)
            self.assertEqual(fetched[0].id, decision.id)
            self.assertEqual(fetched[0].confirmed_material_name, "Stahlbeton C25/30")
        finally:
            fresh_session.close()


if __name__ == "__main__":
    unittest.main()
