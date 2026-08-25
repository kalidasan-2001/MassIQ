from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.plan import PlanDetailResponse, PlanPageResponse, PlanResponse
from app.services.pdf_inspection_service import InvalidPdfError
from app.services.plan_service import PlanNotFoundError, PlanPageNotFoundError, PlanService
from app.services.project_service import ProjectNotFoundError
from app.services.storage_service import StorageError, StorageService

router = APIRouter(prefix="/api/projects/{project_id}/plans", tags=["plans"])


def get_plan_service(db: Session = Depends(get_db)) -> PlanService:
    return PlanService(db)


def get_storage_service() -> StorageService:
    return StorageService()


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


@router.get("/{plan_id}/pages/{page_number}/preview")
async def get_plan_page_preview(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    page_number: int,
    service: PlanService = Depends(get_plan_service),
    storage: StorageService = Depends(get_storage_service),
) -> FileResponse:
    """R2.5: the smallest prerequisite endpoint the new Plan pipeline needs
    before R3 can display a persisted Plan's rendered page. The only path
    ever touched on disk is `page.preview_reference`, a server-generated,
    DB-stored, storage-root-relative string -- project_id/plan_id/page_number
    from the URL are used purely as DB lookup keys (via PlanService.get_page,
    which enforces the same project/plan ownership check as every other
    plans route), never as filesystem path input. StorageService.resolve_preview
    re-validates the resolved path stays under the storage root regardless.
    No absolute path is ever returned to the caller -- only the file's bytes.
    """
    try:
        page = service.get_page(project_id, plan_id, page_number)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Plan not found") from exc
    except PlanPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Page not found") from exc

    if not page.preview_reference:
        raise HTTPException(status_code=404, detail="Preview not available for this page")
    try:
        preview_path = storage.resolve_preview(page.preview_reference)
    except StorageError as exc:
        raise HTTPException(status_code=404, detail="Preview not available for this page") from exc

    return FileResponse(
        preview_path,
        media_type="image/png",
        filename=f"page-{page_number}.png",
    )
