from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.legend_entry import (
    LegendEntryCreate,
    LegendEntryResponse,
    LegendEntryUpdate,
    LegendOcrResponse,
    RegionSelectionRequest,
)
from app.services.legend_crop_service import CropBoundsError, RegionSelection
from app.services.legend_service import (
    DescriptionNotSelectedError,
    LegendConfirmationError,
    LegendEntryNotFoundError,
    LegendService,
)
from app.services.plan_service import PlanNotFoundError, PlanPageNotFoundError
from app.services.project_service import ProjectNotFoundError
from app.services.storage_service import StorageError

router = APIRouter(prefix="/api/projects/{project_id}/plans/{plan_id}/legend-entries", tags=["legend-entries"])


def get_legend_service(db: Session = Depends(get_db)) -> LegendService:
    return LegendService(db)


def _not_found(exc: Exception) -> HTTPException:
    if isinstance(exc, ProjectNotFoundError):
        return HTTPException(status_code=404, detail="Project not found")
    if isinstance(exc, PlanNotFoundError):
        return HTTPException(status_code=404, detail="Plan not found")
    if isinstance(exc, PlanPageNotFoundError):
        return HTTPException(status_code=404, detail="Page not found")
    return HTTPException(status_code=404, detail="Legend entry not found")


@router.post("", response_model=LegendEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_legend_entry(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    payload: LegendEntryCreate,
    service: LegendService = Depends(get_legend_service),
) -> LegendEntryResponse:
    try:
        return service.create_draft(project_id, plan_id, payload.page_number)  # type: ignore[return-value]
    except (ProjectNotFoundError, PlanNotFoundError, PlanPageNotFoundError) as exc:
        raise _not_found(exc) from exc


@router.get("", response_model=list[LegendEntryResponse])
async def list_legend_entries(
    project_id: uuid.UUID, plan_id: uuid.UUID, service: LegendService = Depends(get_legend_service)
) -> list[LegendEntryResponse]:
    try:
        return service.list_entries(project_id, plan_id)  # type: ignore[return-value]
    except (ProjectNotFoundError, PlanNotFoundError) as exc:
        raise _not_found(exc) from exc


@router.get("/{legend_entry_id}", response_model=LegendEntryResponse)
async def get_legend_entry(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    legend_entry_id: uuid.UUID,
    service: LegendService = Depends(get_legend_service),
) -> LegendEntryResponse:
    try:
        return service.get_entry(project_id, plan_id, legend_entry_id)  # type: ignore[return-value]
    except (ProjectNotFoundError, PlanNotFoundError, LegendEntryNotFoundError) as exc:
        raise _not_found(exc) from exc


@router.patch("/{legend_entry_id}", response_model=LegendEntryResponse)
async def update_legend_entry(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    legend_entry_id: uuid.UUID,
    payload: LegendEntryUpdate,
    service: LegendService = Depends(get_legend_service),
) -> LegendEntryResponse:
    try:
        return service.update_entry(project_id, plan_id, legend_entry_id, payload)  # type: ignore[return-value]
    except (ProjectNotFoundError, PlanNotFoundError, LegendEntryNotFoundError) as exc:
        raise _not_found(exc) from exc


@router.post("/{legend_entry_id}/pattern", response_model=LegendEntryResponse)
async def save_pattern_selection(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    legend_entry_id: uuid.UUID,
    payload: RegionSelectionRequest,
    service: LegendService = Depends(get_legend_service),
) -> LegendEntryResponse:
    try:
        selection = RegionSelection(x=payload.x, y=payload.y, width=payload.width, height=payload.height)
        return service.save_pattern_selection(project_id, plan_id, legend_entry_id, selection)  # type: ignore[return-value]
    except (ProjectNotFoundError, PlanNotFoundError, LegendEntryNotFoundError) as exc:
        raise _not_found(exc) from exc
    except CropBoundsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(status_code=404, detail="Page preview not available") from exc


@router.get("/{legend_entry_id}/pattern")
async def get_pattern_crop(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    legend_entry_id: uuid.UUID,
    service: LegendService = Depends(get_legend_service),
) -> FileResponse:
    try:
        crop_path = service.get_crop_path(project_id, plan_id, legend_entry_id, "pattern")
    except (ProjectNotFoundError, PlanNotFoundError, LegendEntryNotFoundError) as exc:
        raise _not_found(exc) from exc
    except StorageError as exc:
        raise HTTPException(status_code=404, detail="Pattern crop not available") from exc
    return FileResponse(crop_path, media_type="image/png", filename="pattern.png")


@router.post("/{legend_entry_id}/description", response_model=LegendEntryResponse)
async def save_description_selection(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    legend_entry_id: uuid.UUID,
    payload: RegionSelectionRequest,
    service: LegendService = Depends(get_legend_service),
) -> LegendEntryResponse:
    try:
        selection = RegionSelection(x=payload.x, y=payload.y, width=payload.width, height=payload.height)
        return service.save_description_selection(project_id, plan_id, legend_entry_id, selection)  # type: ignore[return-value]
    except (ProjectNotFoundError, PlanNotFoundError, LegendEntryNotFoundError) as exc:
        raise _not_found(exc) from exc
    except CropBoundsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(status_code=404, detail="Page preview not available") from exc


@router.get("/{legend_entry_id}/description")
async def get_description_crop(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    legend_entry_id: uuid.UUID,
    service: LegendService = Depends(get_legend_service),
) -> FileResponse:
    try:
        crop_path = service.get_crop_path(project_id, plan_id, legend_entry_id, "description")
    except (ProjectNotFoundError, PlanNotFoundError, LegendEntryNotFoundError) as exc:
        raise _not_found(exc) from exc
    except StorageError as exc:
        raise HTTPException(status_code=404, detail="Description crop not available") from exc
    return FileResponse(crop_path, media_type="image/png", filename="description.png")


@router.post("/{legend_entry_id}/ocr", response_model=LegendOcrResponse)
async def run_ocr(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    legend_entry_id: uuid.UUID,
    service: LegendService = Depends(get_legend_service),
) -> LegendOcrResponse:
    try:
        entry, result = service.run_ocr(project_id, plan_id, legend_entry_id)
    except (ProjectNotFoundError, PlanNotFoundError, LegendEntryNotFoundError) as exc:
        raise _not_found(exc) from exc
    except DescriptionNotSelectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LegendOcrResponse(
        **LegendEntryResponse.model_validate(entry).model_dump(),
        ocr_provider=result.provider,
        ocr_confidence=result.confidence,
        ocr_error=result.error,
    )


@router.post("/{legend_entry_id}/confirm", response_model=LegendEntryResponse)
async def confirm_legend_entry(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    legend_entry_id: uuid.UUID,
    service: LegendService = Depends(get_legend_service),
) -> LegendEntryResponse:
    try:
        return service.confirm(project_id, plan_id, legend_entry_id)  # type: ignore[return-value]
    except (ProjectNotFoundError, PlanNotFoundError, LegendEntryNotFoundError) as exc:
        raise _not_found(exc) from exc
    except LegendConfirmationError as exc:
        raise HTTPException(
            status_code=400, detail={"message": "Cannot confirm legend entry", "reasons": exc.reasons}
        ) from exc
