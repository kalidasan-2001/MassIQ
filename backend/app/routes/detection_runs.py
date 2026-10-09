from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.detection import (
    DetectedRegionResponse,
    DetectionRunResponse,
    StartDetectionRunRequest,
    UpdateRegionStatusRequest,
)
from app.services.detection_service import (
    DetectedRegionNotFoundError,
    DetectionRunNotFoundError,
    DetectionService,
    ExactlyOneReferenceRequiredError,
    PagePreviewNotAvailableError,
    ReferenceFeatureSetRequiredError,
    ReferenceFeatureVersionOutdatedError,
    ReferenceNotConfirmedError,
    ReferenceNotFoundError,
)
from app.services.legend_service import LegendEntryNotFoundError
from app.services.plan_service import PlanNotFoundError, PlanPageNotFoundError
from app.services.project_service import ProjectNotFoundError

# Two routers: one nested under a specific page (where a run is started
# from), one nested under the plan only (where an existing run/its
# regions are addressed by run_id) -- mirrors the plan-page-preview vs.
# legend-entry-by-id split already established in routes/plans.py and
# routes/legend_entries.py.
page_router = APIRouter(
    prefix="/api/projects/{project_id}/plans/{plan_id}/pages/{page_number}/detection-runs",
    tags=["detection-runs"],
)
run_router = APIRouter(
    prefix="/api/projects/{project_id}/plans/{plan_id}/detection-runs",
    tags=["detection-runs"],
)


def get_detection_service(db: Session = Depends(get_db)) -> DetectionService:
    return DetectionService(db)


def _not_found(exc: Exception) -> HTTPException:
    if isinstance(exc, ProjectNotFoundError):
        return HTTPException(status_code=404, detail="Project not found")
    if isinstance(exc, PlanNotFoundError):
        return HTTPException(status_code=404, detail="Plan not found")
    if isinstance(exc, PlanPageNotFoundError):
        return HTTPException(status_code=404, detail="Page not found")
    if isinstance(exc, LegendEntryNotFoundError):
        return HTTPException(status_code=404, detail="Legend entry not found")
    if isinstance(exc, DetectionRunNotFoundError):
        return HTTPException(status_code=404, detail="Detection run not found")
    if isinstance(exc, DetectedRegionNotFoundError):
        return HTTPException(status_code=404, detail="Detected region not found")
    return HTTPException(status_code=404, detail="Not found")


@page_router.post("", response_model=DetectionRunResponse, status_code=status.HTTP_201_CREATED)
async def start_detection_run(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    page_number: int,
    payload: StartDetectionRunRequest,
    service: DetectionService = Depends(get_detection_service),
) -> DetectionRunResponse:
    try:
        return service.start_run(  # type: ignore[return-value]
            project_id,
            plan_id,
            page_number,
            legend_entry_id=payload.legend_entry_id,
            pattern_library_entry_id=payload.pattern_library_entry_id,
            tile_size_px=payload.tile_size_px,
            stride_px=payload.stride_px,
            candidate_threshold=payload.candidate_threshold,
            min_evidence_coverage=payload.min_evidence_coverage,
        )
    except (ProjectNotFoundError, PlanNotFoundError, PlanPageNotFoundError, LegendEntryNotFoundError) as exc:
        raise _not_found(exc) from exc
    except ExactlyOneReferenceRequiredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ReferenceNotConfirmedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ReferenceFeatureSetRequiredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ReferenceFeatureVersionOutdatedError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": exc.error_code,
                "message": (
                    "This hatch was analyzed with an older feature version. "
                    "Recompute the hatch features before running analysis."
                ),
                "reference_feature_version": exc.reference_feature_version,
                "current_feature_version": exc.current_feature_version,
            },
        ) from exc
    except ReferenceNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PagePreviewNotAvailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@page_router.get("", response_model=list[DetectionRunResponse])
async def list_page_detection_runs(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    page_number: int,
    service: DetectionService = Depends(get_detection_service),
) -> list[DetectionRunResponse]:
    try:
        return service.list_runs_for_page(project_id, plan_id, page_number)  # type: ignore[return-value]
    except (ProjectNotFoundError, PlanNotFoundError, PlanPageNotFoundError) as exc:
        raise _not_found(exc) from exc


@run_router.get("/{run_id}", response_model=DetectionRunResponse)
async def get_detection_run(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    run_id: uuid.UUID,
    service: DetectionService = Depends(get_detection_service),
) -> DetectionRunResponse:
    try:
        return service.get_run(project_id, plan_id, run_id)  # type: ignore[return-value]
    except (ProjectNotFoundError, PlanNotFoundError, DetectionRunNotFoundError) as exc:
        raise _not_found(exc) from exc


@run_router.get("/{run_id}/regions", response_model=list[DetectedRegionResponse])
async def list_detected_regions(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    run_id: uuid.UUID,
    service: DetectionService = Depends(get_detection_service),
) -> list[DetectedRegionResponse]:
    try:
        return service.list_regions(project_id, plan_id, run_id)  # type: ignore[return-value]
    except (ProjectNotFoundError, PlanNotFoundError, DetectionRunNotFoundError) as exc:
        raise _not_found(exc) from exc


@run_router.patch("/{run_id}/regions/{region_id}", response_model=DetectedRegionResponse)
async def update_detected_region(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    run_id: uuid.UUID,
    region_id: uuid.UUID,
    payload: UpdateRegionStatusRequest,
    service: DetectionService = Depends(get_detection_service),
) -> DetectedRegionResponse:
    try:
        return service.update_region_status(  # type: ignore[return-value]
            project_id, plan_id, run_id, region_id, payload.status
        )
    except (ProjectNotFoundError, PlanNotFoundError, DetectionRunNotFoundError, DetectedRegionNotFoundError) as exc:
        raise _not_found(exc) from exc
