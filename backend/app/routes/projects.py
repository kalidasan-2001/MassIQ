from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services.project_service import ProjectNotFoundError, ProjectService

router = APIRouter(prefix="/api/projects", tags=["projects"])


def get_project_service(db: Session = Depends(get_db)) -> ProjectService:
    return ProjectService(db)


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, service: ProjectService = Depends(get_project_service)
) -> ProjectResponse:
    return service.create_project(payload)  # type: ignore[return-value]


@router.get("", response_model=list[ProjectResponse])
async def list_projects(service: ProjectService = Depends(get_project_service)) -> list[ProjectResponse]:
    return service.list_projects()  # type: ignore[return-value]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID, service: ProjectService = Depends(get_project_service)
) -> ProjectResponse:
    try:
        return service.get_project(project_id)  # type: ignore[return-value]
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    service: ProjectService = Depends(get_project_service),
) -> ProjectResponse:
    try:
        return service.update_project(project_id, payload)  # type: ignore[return-value]
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
