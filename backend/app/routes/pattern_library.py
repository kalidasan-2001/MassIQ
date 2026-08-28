from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.pattern_library import PatternLibraryEntryResponse
from app.services.pattern_library_service import PatternLibraryService
from app.services.project_service import ProjectNotFoundError

router = APIRouter(prefix="/api/projects/{project_id}/pattern-library", tags=["pattern-library"])


def get_pattern_library_service(db: Session = Depends(get_db)) -> PatternLibraryService:
    return PatternLibraryService(db)


@router.get("", response_model=list[PatternLibraryEntryResponse])
async def list_pattern_library_entries(
    project_id: uuid.UUID,
    service: PatternLibraryService = Depends(get_pattern_library_service),
) -> list[PatternLibraryEntryResponse]:
    try:
        return service.list_entries(project_id)  # type: ignore[return-value]
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
