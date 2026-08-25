from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.plan import PdfType, PlanProcessingStatus


class PlanPageResponse(BaseModel):
    """Internal storage references (preview_reference) are deliberately not
    exposed here -- R2 does not add a preview-serving HTTP endpoint (out of
    the specified scope), and exposing raw storage layout would leak
    internal filesystem structure to clients for no current benefit."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    page_number: int
    width: float
    height: float
    rotation: int
    vector_content_available: bool
    created_at: datetime


class PlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    original_filename: str
    page_count: int
    processing_status: PlanProcessingStatus
    pdf_type: PdfType
    created_at: datetime
    updated_at: datetime


class PlanDetailResponse(PlanResponse):
    pages: list[PlanPageResponse] = []
