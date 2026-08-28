from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.plan_scale import PlanScaleMethod
from app.schemas.plan_scale import ConfirmPlanScaleRequest, PlanScaleResponse
from app.services.plan_scale_service import InvalidScaleError, PlanScaleNotFoundError, PlanScaleService
from app.services.plan_service import PlanNotFoundError, PlanPageNotFoundError
from app.services.project_service import ProjectNotFoundError

# Page-scoped (R7 section 13: scale belongs to the PlanPage, reused by
# every DetectionRun computed against it), mirroring detection_runs.py's
# page_router nesting.
router = APIRouter(
    prefix="/api/projects/{project_id}/plans/{plan_id}/pages/{page_number}/scale",
    tags=["plan-scale"],
)


def get_plan_scale_service(db: Session = Depends(get_db)) -> PlanScaleService:
    return PlanScaleService(db)


def _not_found(exc: Exception) -> HTTPException:
    if isinstance(exc, ProjectNotFoundError):
        return HTTPException(status_code=404, detail="Project not found")
    if isinstance(exc, PlanNotFoundError):
        return HTTPException(status_code=404, detail="Plan not found")
    if isinstance(exc, PlanPageNotFoundError):
        return HTTPException(status_code=404, detail="Page not found")
    if isinstance(exc, PlanScaleNotFoundError):
        return HTTPException(status_code=404, detail="No confirmed scale for this page")
    return HTTPException(status_code=404, detail="Not found")


@router.get("", response_model=PlanScaleResponse)
async def get_plan_scale(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    page_number: int,
    service: PlanScaleService = Depends(get_plan_scale_service),
) -> PlanScaleResponse:
    try:
        return service.get_scale(project_id, plan_id, page_number)  # type: ignore[return-value]
    except (ProjectNotFoundError, PlanNotFoundError, PlanPageNotFoundError, PlanScaleNotFoundError) as exc:
        raise _not_found(exc) from exc


@router.put("", response_model=PlanScaleResponse)
async def confirm_plan_scale(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    page_number: int,
    payload: ConfirmPlanScaleRequest,
    service: PlanScaleService = Depends(get_plan_scale_service),
) -> PlanScaleResponse:
    try:
        if payload.method == PlanScaleMethod.DECLARED_SCALE:
            return service.confirm_declared_scale(  # type: ignore[return-value]
                project_id, plan_id, page_number, payload.declared_ratio
            )
        return service.confirm_calibrated_distance(  # type: ignore[return-value]
            project_id,
            plan_id,
            page_number,
            payload.calibrated_distance_plan_points,
            payload.calibrated_distance_real_m,
        )
    except (ProjectNotFoundError, PlanNotFoundError, PlanPageNotFoundError) as exc:
        raise _not_found(exc) from exc
    except InvalidScaleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
