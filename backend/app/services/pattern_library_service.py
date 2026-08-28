from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

from app.hatch.similarity.combined_similarity import compare
from app.hatch.similarity.config import DEFAULT_TOP_K
from app.hatch.similarity.models import ComparableFeatures, SimilarityResult
from app.models.hatch_feature_set import HatchFeatureSet
from app.models.legend_entry import LegendEntry, LegendEntryStatus
from app.models.pattern_library_entry import PatternLibraryEntry
from app.models.pattern_match_decision import MatchDecision, PatternMatchDecision
from app.services.legend_service import LegendService
from app.services.project_service import ProjectService
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)

__all__ = [
    "PatternLibraryService",
    "MatchCandidate",
    "MatchSearchResult",
    "LegendEntryNotConfirmedForLibraryError",
    "MaterialNotConfirmedError",
    "FeatureSetRequiredError",
    "SuggestedLibraryEntryNotFoundError",
    "REASON_EMPTY_LIBRARY",
    "REASON_NO_COMPARABLE_CANDIDATES",
]

# R5 section 24's two distinct "nothing to show" reasons -- neither is an
# error. An empty project library and "every candidate was version-
# incompatible" are different facts a caller might want to distinguish.
REASON_EMPTY_LIBRARY = "empty_library"
REASON_NO_COMPARABLE_CANDIDATES = "no_comparable_candidates"


class LegendEntryNotConfirmedForLibraryError(Exception):
    """A library entry may only be created from a CONFIRMED LegendEntry
    (R5 section 6) -- distinct from R4's own confirmed-status gate so the
    two features can report accurate, specific error messages."""

    def __init__(self, legend_entry_id: uuid.UUID):
        self.legend_entry_id = legend_entry_id
        super().__init__(f"LegendEntry {legend_entry_id} must be confirmed before joining the pattern library")


class MaterialNotConfirmedError(Exception):
    def __init__(self, legend_entry_id: uuid.UUID):
        self.legend_entry_id = legend_entry_id
        super().__init__(f"LegendEntry {legend_entry_id} has no confirmed material name")


class FeatureSetRequiredError(Exception):
    """Raised whenever a library operation needs a HatchFeatureSet that
    does not yet exist. R5 section 6 is explicit: do not silently compute
    features during an unrelated call -- the caller must have already run
    R4's own explicit POST .../features step."""

    def __init__(self, legend_entry_id: uuid.UUID):
        self.legend_entry_id = legend_entry_id
        super().__init__(
            f"LegendEntry {legend_entry_id} has no computed HatchFeatureSet yet -- "
            "compute features explicitly before using the pattern library"
        )


class SuggestedLibraryEntryNotFoundError(Exception):
    """Raised when a match-decision payload references a
    suggested_library_entry_id that either doesn't exist or belongs to a
    different project -- the same cross-project isolation discipline
    applied everywhere else in the app."""

    def __init__(self, library_entry_id: uuid.UUID):
        self.library_entry_id = library_entry_id
        super().__init__(f"Pattern library entry {library_entry_id} not found in this project")


@dataclass(frozen=True)
class MatchCandidate:
    """One scored library entry, ready for API serialization. Carries
    `plan_id` (looked up via the entry's source LegendEntry, never stored
    redundantly on PatternLibraryEntry) so the caller can build a pattern
    preview URL through the existing, already-tested crop-serving route."""

    library_entry: PatternLibraryEntry
    similarity: SimilarityResult
    source_plan_id: uuid.UUID
    source_legend_entry_id: uuid.UUID


@dataclass(frozen=True)
class MatchSearchResult:
    candidates: list[MatchCandidate] = field(default_factory=list)
    incompatible_count: int = 0
    reason: str | None = None  # REASON_EMPTY_LIBRARY / REASON_NO_COMPARABLE_CANDIDATES / None


class PatternLibraryService:
    """Owns the R5 Project Pattern Library: adding a confirmed LegendEntry
    to the project-scoped library, project-scoped Top-K similarity search
    against it, and persisting user match decisions.

    Deliberately does NOT do CV feature extraction (that's
    HatchFeatureService/app.hatch's job) and does NOT introduce any
    scope beyond the current project -- see R5 section 1's explicit
    "project-scoped library only" principle. Composes LegendService (for
    ownership/status) and HatchFeatureService (for read-only feature
    lookup -- this class never triggers feature computation itself).
    """

    def __init__(self, db, storage: StorageService | None = None):
        self._db = db
        self._storage = storage or StorageService()
        self._legend_service = LegendService(db, storage=self._storage)
        self._project_service = ProjectService(db)

    # -- add to library ----------------------------------------------

    def add_entry(self, project_id: uuid.UUID, plan_id: uuid.UUID, legend_entry_id: uuid.UUID) -> PatternLibraryEntry:
        entry = self._legend_service.get_entry(project_id, plan_id, legend_entry_id)
        if entry.status != LegendEntryStatus.CONFIRMED:
            raise LegendEntryNotConfirmedForLibraryError(legend_entry_id)
        if not (entry.material_name or "").strip():
            raise MaterialNotConfirmedError(legend_entry_id)

        feature_set = self._db.query(HatchFeatureSet).filter_by(legend_entry_id=legend_entry_id).one_or_none()
        if feature_set is None:
            raise FeatureSetRequiredError(legend_entry_id)

        existing = (
            self._db.query(PatternLibraryEntry).filter_by(source_legend_entry_id=legend_entry_id).one_or_none()
        )
        if existing is not None:
            # Duplicate policy (R5 section 7): re-adding the same source
            # LegendEntry updates the one existing row intentionally,
            # rather than creating a second, ambiguous entry.
            existing.canonical_material_name = entry.material_name
            existing.material_code = entry.material_code
            existing.thickness_mm = entry.thickness_mm
            existing.original_label = entry.corrected_text
            existing.hatch_feature_set_id = feature_set.id
            existing.confirmation_count += 1
            existing.active = True
            self._db.commit()
            self._db.refresh(existing)
            existing.source_plan_id = plan_id  # transient enrichment, see list_entries
            logger.info(
                "pattern_library_entry_updated project_id=%s legend_entry_id=%s library_entry_id=%s "
                "confirmation_count=%d",
                project_id, legend_entry_id, existing.id, existing.confirmation_count,
            )
            return existing

        row = PatternLibraryEntry(
            project_id=project_id,
            source_legend_entry_id=legend_entry_id,
            hatch_feature_set_id=feature_set.id,
            canonical_material_name=entry.material_name,
            material_code=entry.material_code,
            thickness_mm=entry.thickness_mm,
            original_label=entry.corrected_text,
            confirmation_count=1,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        row.source_plan_id = plan_id  # transient enrichment, see list_entries
        logger.info(
            "pattern_library_entry_created project_id=%s legend_entry_id=%s library_entry_id=%s",
            project_id, legend_entry_id, row.id,
        )
        return row

    # -- listing -------------------------------------------------------

    def list_entries(self, project_id: uuid.UUID) -> list[PatternLibraryEntry]:
        self._project_service.get_project(project_id)  # raises ProjectNotFoundError if unowned/missing
        entries = (
            self._db.query(PatternLibraryEntry)
            .filter_by(project_id=project_id)
            .order_by(PatternLibraryEntry.created_at.desc())
            .all()
        )
        # A library entry's source LegendEntry can belong to any plan in
        # the project -- enrich each row with a transient (never
        # persisted) `source_plan_id` attribute so the API response can
        # build a pattern-preview URL through the existing crop-serving
        # route, without denormalizing plan_id onto the table itself.
        if entries:
            source_ids = {entry.source_legend_entry_id for entry in entries}
            plan_ids_by_legend_entry = {
                row.id: row.plan_id
                for row in self._db.query(LegendEntry).filter(LegendEntry.id.in_(source_ids)).all()
            }
            for entry in entries:
                entry.source_plan_id = plan_ids_by_legend_entry.get(entry.source_legend_entry_id)
        return entries

    # -- Top-K search --------------------------------------------------

    def find_matches(
        self, project_id: uuid.UUID, plan_id: uuid.UUID, legend_entry_id: uuid.UUID, top_k: int = DEFAULT_TOP_K
    ) -> MatchSearchResult:
        start = time.perf_counter()
        entry = self._legend_service.get_entry(project_id, plan_id, legend_entry_id)
        reference_set = self._db.query(HatchFeatureSet).filter_by(legend_entry_id=legend_entry_id).one_or_none()
        if reference_set is None:
            raise FeatureSetRequiredError(legend_entry_id)
        reference = ComparableFeatures.from_features(reference_set)

        library_entries = (
            self._db.query(PatternLibraryEntry)
            .filter_by(project_id=project_id, active=True)
            .filter(PatternLibraryEntry.source_legend_entry_id != legend_entry_id)
            .all()
        )
        if not library_entries:
            logger.info(
                "pattern_match_search project_id=%s legend_entry_id=%s candidate_count=0 "
                "feature_version=%s duration_ms=%.1f reason=%s",
                project_id, legend_entry_id, reference.feature_version,
                (time.perf_counter() - start) * 1000, REASON_EMPTY_LIBRARY,
            )
            return MatchSearchResult(candidates=[], incompatible_count=0, reason=REASON_EMPTY_LIBRARY)

        scored: list[tuple[PatternLibraryEntry, SimilarityResult]] = []
        incompatible_count = 0
        for library_entry in library_entries:
            candidate_set = self._db.get(HatchFeatureSet, library_entry.hatch_feature_set_id)
            if candidate_set is None:
                # Defensive: the referenced HatchFeatureSet row is gone
                # (should not happen given the FK, but never crash a
                # search over one stale row).
                incompatible_count += 1
                continue
            candidate = ComparableFeatures.from_features(candidate_set)
            result = compare(reference, candidate)
            if not result.comparable:
                incompatible_count += 1
                continue
            scored.append((library_entry, result))

        if not scored:
            reason = REASON_NO_COMPARABLE_CANDIDATES if incompatible_count > 0 else REASON_EMPTY_LIBRARY
            logger.info(
                "pattern_match_search project_id=%s legend_entry_id=%s candidate_count=%d "
                "feature_version=%s duration_ms=%.1f reason=%s",
                project_id, legend_entry_id, len(library_entries), reference.feature_version,
                (time.perf_counter() - start) * 1000, reason,
            )
            return MatchSearchResult(candidates=[], incompatible_count=incompatible_count, reason=reason)

        # Deterministic ranking (R5 section 44): similarity DESC, then
        # created_at ASC, then id ASC as a final stable tie-break -- never
        # left to whatever order the database happened to return rows in.
        scored.sort(key=lambda pair: (-pair[1].overall_similarity, pair[0].created_at, str(pair[0].id)))
        top = scored[:top_k]

        # A library entry's source LegendEntry can belong to any plan in
        # this project -- the library is project-scoped, not plan-scoped
        # (R5 section 1) -- so plan_id is looked up per source entry
        # directly, never assumed to be the querying legend_entry_id's
        # own plan_id.
        source_ids = {library_entry.source_legend_entry_id for library_entry, _ in top}
        source_entries = {
            row.id: row
            for row in self._db.query(LegendEntry).filter(LegendEntry.id.in_(source_ids)).all()
        }
        candidates = [
            MatchCandidate(
                library_entry=library_entry,
                similarity=result,
                source_plan_id=source_entries[library_entry.source_legend_entry_id].plan_id,
                source_legend_entry_id=library_entry.source_legend_entry_id,
            )
            for library_entry, result in top
        ]

        logger.info(
            "pattern_match_search project_id=%s legend_entry_id=%s candidate_count=%d "
            "feature_version=%s duration_ms=%.1f top_k=%d returned=%d incompatible=%d",
            project_id, legend_entry_id, len(library_entries), reference.feature_version,
            (time.perf_counter() - start) * 1000, top_k, len(candidates), incompatible_count,
        )
        return MatchSearchResult(candidates=candidates, incompatible_count=incompatible_count, reason=None)

    # -- decisions -------------------------------------------------------

    def record_decision(
        self,
        project_id: uuid.UUID,
        plan_id: uuid.UUID,
        legend_entry_id: uuid.UUID,
        suggested_library_entry_id: uuid.UUID | None,
        similarity_at_decision: float | None,
        decision: MatchDecision,
        confirmed_material_name: str | None,
    ) -> PatternMatchDecision:
        self._legend_service.get_entry(project_id, plan_id, legend_entry_id)  # ownership check

        if suggested_library_entry_id is not None:
            suggested = self._db.get(PatternLibraryEntry, suggested_library_entry_id)
            if suggested is None or suggested.project_id != project_id:
                raise SuggestedLibraryEntryNotFoundError(suggested_library_entry_id)

        row = PatternMatchDecision(
            project_id=project_id,
            candidate_legend_entry_id=legend_entry_id,
            suggested_library_entry_id=suggested_library_entry_id,
            similarity_at_decision=similarity_at_decision,
            decision=decision,
            confirmed_material_name=confirmed_material_name,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        logger.info(
            "pattern_match_decision_recorded project_id=%s legend_entry_id=%s decision=%s "
            "suggested_library_entry_id=%s",
            project_id, legend_entry_id, decision.value, suggested_library_entry_id,
        )
        return row

    def list_decisions(
        self, project_id: uuid.UUID, plan_id: uuid.UUID, legend_entry_id: uuid.UUID
    ) -> list[PatternMatchDecision]:
        self._legend_service.get_entry(project_id, plan_id, legend_entry_id)  # ownership check
        return (
            self._db.query(PatternMatchDecision)
            .filter_by(project_id=project_id, candidate_legend_entry_id=legend_entry_id)
            .order_by(PatternMatchDecision.created_at.desc())
            .all()
        )
