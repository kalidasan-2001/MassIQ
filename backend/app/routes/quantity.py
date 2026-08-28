from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.quantity import CalculateQuantityRequest, QuantityResultResponse
from app.services.detection_service import DetectionRunNotFoundError
from app.services.plan_service import PlanNotFoundError
from app.services.project_service import ProjectNotFoundError
from app.services.quantity_service import (
    InvalidDimensionError,
    QuantityResultNotFoundError,
    QuantityService,
    ScaleNotConfirmedError,
)

router = APIRouter(
    prefix="/api/projects/{project_id}/plans/{plan_id}/detection-runs/{run_id}/quantity",
    tags=["quantity"],
)


def get_quantity_service(db: Session = Depends(get_db)) -> QuantityService:
    return QuantityService(db)


def _not_found(exc: Exception) -> HTTPException:
    if isinstance(exc, ProjectNotFoundError):
        return HTTPException(status_code=404, detail="Project not found")
    if isinstance(exc, PlanNotFoundError):
        return HTTPException(status_code=404, detail="Plan not found")
    if isinstance(exc, DetectionRunNotFoundError):
        return HTTPException(status_code=404, detail="Detection run not found")
    if isinstance(exc, QuantityResultNotFoundError):
        return HTTPException(status_code=404, detail="No quantity result for this detection run yet")
    return HTTPException(status_code=404, detail="Not found")


@router.post("", response_model=QuantityResultResponse, status_code=status.HTTP_200_OK)
async def calculate_quantity(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    run_id: uuid.UUID,
    payload: CalculateQuantityRequest,
    service: QuantityService = Depends(get_quantity_service),
) -> QuantityResultResponse:
    try:
        return service.calculate(  # type: ignore[return-value]
            project_id, plan_id, run_id, payload.confirmed_dimension_m
        )
    except (ProjectNotFoundError, PlanNotFoundError, DetectionRunNotFoundError) as exc:
        raise _not_found(exc) from exc
    except InvalidDimensionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ScaleNotConfirmedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=QuantityResultResponse)
async def get_quantity(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    run_id: uuid.UUID,
    service: QuantityService = Depends(get_quantity_service),
) -> QuantityResultResponse:
    try:
        return service.get_result(project_id, plan_id, run_id)  # type: ignore[return-value]
    except (ProjectNotFoundError, PlanNotFoundError, DetectionRunNotFoundError, QuantityResultNotFoundError) as exc:
        raise _not_found(exc) from exc


@router.post("/confirm", response_model=QuantityResultResponse)
async def confirm_quantity(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    run_id: uuid.UUID,
    service: QuantityService = Depends(get_quantity_service),
) -> QuantityResultResponse:
    try:
        return service.confirm(project_id, plan_id, run_id)  # type: ignore[return-value]
    except (ProjectNotFoundError, PlanNotFoundError, DetectionRunNotFoundError, QuantityResultNotFoundError) as exc:
        raise _not_found(exc) from exc
