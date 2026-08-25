from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.plan import PlanDetailResponse, PlanPageResponse, PlanResponse
from app.services.pdf_inspection_service import InvalidPdfError
from app.services.plan_service import PlanNotFoundError, PlanService
from app.services.project_service import ProjectNotFoundError

router = APIRouter(prefix="/api/projects/{project_id}/plans", tags=["plans"])


def get_plan_service(db: Session = Depends(get_db)) -> PlanService:
    return PlanService(db)


@router.post("", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def upload_plan(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    service: PlanService = Depends(get_plan_service),
) -> PlanResponse:
    content = await file.read()
    try:
        return service.upload_plan(project_id, file.filename or "upload.pdf", content)  # type: ignore[return-value]
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except InvalidPdfError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[PlanResponse])
async def list_plans(project_id: uuid.UUID, service: PlanService = Depends(get_plan_service)) -> list[PlanResponse]:
    try:
        return service.list_plans(project_id)  # type: ignore[return-value]
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@router.get("/{plan_id}", response_model=PlanDetailResponse)
async def get_plan(
    project_id: uuid.UUID, plan_id: uuid.UUID, service: PlanService = Depends(get_plan_service)
) -> PlanDetailResponse:
    try:
        return service.get_plan(project_id, plan_id)  # type: ignore[return-value]
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Plan not found") from exc


@router.get("/{plan_id}/pages", response_model=list[PlanPageResponse])
async def list_plan_pages(
    project_id: uuid.UUID, plan_id: uuid.UUID, service: PlanService = Depends(get_plan_service)
) -> list[PlanPageResponse]:
    try:
        plan = service.get_plan(project_id, plan_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Plan not found") from exc
    return plan.pages  # type: ignore[return-value]
