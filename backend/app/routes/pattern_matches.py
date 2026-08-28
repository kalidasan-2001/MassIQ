from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.pattern_library import (
    MatchCandidateResponse,
    MatchDecisionResponse,
    MatchesRequest,
    MatchesResponse,
    PatternLibraryEntryResponse,
    RecordDecisionRequest,
    similarity_band,
)
from app.services.legend_service import LegendEntryNotFoundError
from app.services.pattern_library_service import (
    FeatureSetRequiredError,
    LegendEntryNotConfirmedForLibraryError,
    MaterialNotConfirmedError,
    PatternLibraryService,
    SuggestedLibraryEntryNotFoundError,
)
from app.services.plan_service import PlanNotFoundError, PlanPageNotFoundError
from app.services.project_service import ProjectNotFoundError

router = APIRouter(
    prefix="/api/projects/{project_id}/plans/{plan_id}/legend-entries/{legend_entry_id}",
    tags=["pattern-matches"],
)


def get_pattern_library_service(db: Session = Depends(get_db)) -> PatternLibraryService:
    return PatternLibraryService(db)


def _not_found(exc: Exception) -> HTTPException:
    if isinstance(exc, ProjectNotFoundError):
        return HTTPException(status_code=404, detail="Project not found")
    if isinstance(exc, PlanNotFoundError):
        return HTTPException(status_code=404, detail="Plan not found")
    if isinstance(exc, PlanPageNotFoundError):
        return HTTPException(status_code=404, detail="Page not found")
    return HTTPException(status_code=404, detail="Legend entry not found")


@router.post("/library", response_model=PatternLibraryEntryResponse, status_code=status.HTTP_201_CREATED)
async def add_to_pattern_library(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    legend_entry_id: uuid.UUID,
    service: PatternLibraryService = Depends(get_pattern_library_service),
) -> PatternLibraryEntryResponse:
    try:
        return service.add_entry(project_id, plan_id, legend_entry_id)  # type: ignore[return-value]
    except (ProjectNotFoundError, PlanNotFoundError, LegendEntryNotFoundError) as exc:
        raise _not_found(exc) from exc
    except LegendEntryNotConfirmedForLibraryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MaterialNotConfirmedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FeatureSetRequiredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _candidate_to_response(candidate) -> MatchCandidateResponse:
    entry = candidate.library_entry
    available_components = {name: comp.score for name, comp in candidate.similarity.components.items() if comp.available}
    return MatchCandidateResponse(
        library_entry_id=entry.id,
        canonical_material_name=entry.canonical_material_name,
        material_code=entry.material_code,
        thickness_mm=entry.thickness_mm,
        original_label=entry.original_label,
        similarity=candidate.similarity.overall_similarity,
        similarity_band=similarity_band(candidate.similarity.overall_similarity, candidate.similarity.evidence_coverage),
        components=available_components,
        evidence_coverage=candidate.similarity.evidence_coverage,
        source_project_id=entry.project_id,
        source_plan_id=candidate.source_plan_id,
        source_legend_entry_id=candidate.source_legend_entry_id,
        confirmation_count=entry.confirmation_count,
    )


@router.post("/matches", response_model=MatchesResponse)
async def compute_pattern_matches(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    legend_entry_id: uuid.UUID,
    payload: MatchesRequest = MatchesRequest(),
    service: PatternLibraryService = Depends(get_pattern_library_service),
) -> MatchesResponse:
    try:
        result = service.find_matches(project_id, plan_id, legend_entry_id, top_k=payload.top_k)
    except (ProjectNotFoundError, PlanNotFoundError, LegendEntryNotFoundError) as exc:
        raise _not_found(exc) from exc
    except FeatureSetRequiredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MatchesResponse(
        candidates=[_candidate_to_response(candidate) for candidate in result.candidates],
        incompatible_count=result.incompatible_count,
        reason=result.reason,
    )


@router.post("/match-decision", response_model=MatchDecisionResponse, status_code=status.HTTP_201_CREATED)
async def record_match_decision(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    legend_entry_id: uuid.UUID,
    payload: RecordDecisionRequest,
    service: PatternLibraryService = Depends(get_pattern_library_service),
) -> MatchDecisionResponse:
    try:
        return service.record_decision(  # type: ignore[return-value]
            project_id,
            plan_id,
            legend_entry_id,
            suggested_library_entry_id=payload.suggested_library_entry_id,
            similarity_at_decision=payload.similarity_at_decision,
            decision=payload.decision,
            confirmed_material_name=payload.confirmed_material_name,
        )
    except (ProjectNotFoundError, PlanNotFoundError, LegendEntryNotFoundError) as exc:
        raise _not_found(exc) from exc
    except SuggestedLibraryEntryNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/match-decisions", response_model=list[MatchDecisionResponse])
async def list_match_decisions(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    legend_entry_id: uuid.UUID,
    service: PatternLibraryService = Depends(get_pattern_library_service),
) -> list[MatchDecisionResponse]:
    try:
        return service.list_decisions(project_id, plan_id, legend_entry_id)  # type: ignore[return-value]
    except (ProjectNotFoundError, PlanNotFoundError, LegendEntryNotFoundError) as exc:
        raise _not_found(exc) from exc
