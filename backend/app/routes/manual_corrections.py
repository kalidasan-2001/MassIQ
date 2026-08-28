from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.geometry.service import NormalizedRect
from app.schemas.manual_correction import ManualCorrectionCreate, ManualCorrectionResponse
from app.services.detection_service import DetectionRunNotFoundError
from app.services.manual_correction_service import (
    InvalidCorrectionGeometryError,
    ManualCorrectionNotFoundError,
    ManualCorrectionService,
)
from app.services.plan_service import PlanNotFoundError
from app.services.project_service import ProjectNotFoundError

# Nested under a specific DetectionRun (R7 section 8: a manual correction
# is a layer on top of ONE run's review session), mirroring
# routes/detection_runs.py's run_router nesting.
router = APIRouter(
    prefix="/api/projects/{project_id}/plans/{plan_id}/detection-runs/{run_id}/manual-corrections",
    tags=["manual-corrections"],
)


def get_manual_correction_service(db: Session = Depends(get_db)) -> ManualCorrectionService:
    return ManualCorrectionService(db)


def _not_found(exc: Exception) -> HTTPException:
    if isinstance(exc, ProjectNotFoundError):
        return HTTPException(status_code=404, detail="Project not found")
    if isinstance(exc, PlanNotFoundError):
        return HTTPException(status_code=404, detail="Plan not found")
    if isinstance(exc, DetectionRunNotFoundError):
        return HTTPException(status_code=404, detail="Detection run not found")
    if isinstance(exc, ManualCorrectionNotFoundError):
        return HTTPException(status_code=404, detail="Manual correction not found")
    return HTTPException(status_code=404, detail="Not found")


@router.post("", response_model=ManualCorrectionResponse, status_code=status.HTTP_201_CREATED)
async def create_manual_correction(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    run_id: uuid.UUID,
    payload: ManualCorrectionCreate,
    service: ManualCorrectionService = Depends(get_manual_correction_service),
) -> ManualCorrectionResponse:
    try:
        return service.create_correction(  # type: ignore[return-value]
            project_id,
            plan_id,
            run_id,
            payload.correction_type,
            NormalizedRect(payload.x, payload.y, payload.width, payload.height),
        )
    except (ProjectNotFoundError, PlanNotFoundError, DetectionRunNotFoundError) as exc:
        raise _not_found(exc) from exc
    except InvalidCorrectionGeometryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[ManualCorrectionResponse])
async def list_manual_corrections(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    run_id: uuid.UUID,
    service: ManualCorrectionService = Depends(get_manual_correction_service),
) -> list[ManualCorrectionResponse]:
    try:
        return service.list_corrections(project_id, plan_id, run_id)  # type: ignore[return-value]
    except (ProjectNotFoundError, PlanNotFoundError, DetectionRunNotFoundError) as exc:
        raise _not_found(exc) from exc


@router.delete("/{correction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_manual_correction(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    run_id: uuid.UUID,
    correction_id: uuid.UUID,
    service: ManualCorrectionService = Depends(get_manual_correction_service),
) -> None:
    try:
        service.delete_correction(project_id, plan_id, run_id, correction_id)
    except (ProjectNotFoundError, PlanNotFoundError, DetectionRunNotFoundError, ManualCorrectionNotFoundError) as exc:
        raise _not_found(exc) from exc
