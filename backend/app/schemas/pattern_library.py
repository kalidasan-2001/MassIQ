from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.hatch.similarity.config import (
    DEFAULT_TOP_K,
    HIGH_SIMILARITY_THRESHOLD,
    MEDIUM_SIMILARITY_THRESHOLD,
    MIN_COVERAGE_FOR_HIGH_BAND,
)
from app.models.pattern_match_decision import MatchDecision


class PatternLibraryEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    source_legend_entry_id: uuid.UUID
    # Enrichment field, looked up via the source LegendEntry -- never a
    # real column on pattern_library_entries (see
    # PatternLibraryService.list_entries). Lets the frontend build a
    # pattern-preview URL through the existing crop-serving route.
    source_plan_id: uuid.UUID
    hatch_feature_set_id: uuid.UUID

    canonical_material_name: str
    material_code: str | None
    thickness_mm: float | None
    original_label: str | None

    confirmation_count: int
    active: bool

    created_at: datetime
    updated_at: datetime


class MatchesRequest(BaseModel):
    """Empty-body-friendly: `top_k` is optional, defaulting to R5's
    conservative default (see similarity/config.py::DEFAULT_TOP_K)."""

    model_config = ConfigDict(extra="forbid")

    top_k: int = Field(default=DEFAULT_TOP_K, ge=1, le=50)


def similarity_band(score: float, evidence_coverage: float = 1.0) -> str:
    """Purely descriptive qualitative label -- never called "confidence"
    anywhere in this app. See docs/architecture/PATTERN_LIBRARY.md's
    "Thresholds" section for the documented cutoffs.

    `evidence_coverage` caps the band at MEDIUM even for a numerically
    high raw score, when too little of the intended feature comparison
    was actually available (see similarity/config.py's
    MIN_COVERAGE_FOR_HIGH_BAND and its own docstring for the negative-
    control evidence this was calibrated against) -- a high score built
    from only 1-2 low-weight components (e.g. density and color alone,
    when a candidate has no reliable angle/spacing/periodicity evidence
    at all) is not the same thing as a high score built from the full
    comparison, and must not be presented to a user identically."""
    if score >= HIGH_SIMILARITY_THRESHOLD:
        return "high" if evidence_coverage >= MIN_COVERAGE_FOR_HIGH_BAND else "medium"
    if score >= MEDIUM_SIMILARITY_THRESHOLD:
        return "medium"
    return "low"


class MatchCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    library_entry_id: uuid.UUID
    canonical_material_name: str
    material_code: str | None
    thickness_mm: float | None
    original_label: str | None

    # Explicitly "similarity" everywhere -- never "probability" or
    # "confidence" (R5 section 29). Describes structural/visual
    # resemblance only; the material association still requires the
    # user's own confirmation.
    similarity: float = Field(ge=0, le=1)
    similarity_band: str
    components: dict[str, float]
    # Fraction (0-1) of the total feature weight budget that actually had
    # evidence on both sides -- quality metadata, not a confidence score.
    # See similarity/models.py::SimilarityResult.evidence_coverage.
    evidence_coverage: float = Field(ge=0, le=1)

    source_project_id: uuid.UUID
    source_plan_id: uuid.UUID
    source_legend_entry_id: uuid.UUID

    confirmation_count: int


class MatchesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[MatchCandidateResponse]
    incompatible_count: int
    reason: str | None  # "empty_library" / "no_comparable_candidates" / None


class RecordDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: MatchDecision
    suggested_library_entry_id: uuid.UUID | None = None
    similarity_at_decision: float | None = Field(default=None, ge=0, le=1)
    confirmed_material_name: str | None = None


class MatchDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    candidate_legend_entry_id: uuid.UUID
    suggested_library_entry_id: uuid.UUID | None
    similarity_at_decision: float | None
    decision: MatchDecision
    confirmed_material_name: str | None
    created_at: datetime
