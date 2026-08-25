from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.legend_entry import LegendEntryStatus


class LegendEntryCreate(BaseModel):
    """Client-writable fields only. plan_page_id is deliberately NOT
    accepted here -- the service resolves it server-side from page_number
    via PlanService.get_page, so a client can never assert an inconsistent
    project/plan/page combination."""

    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)


class LegendEntryUpdate(BaseModel):
    """PATCH semantics -- only fields explicitly present in the request are
    applied (see LegendService.update_entry, same exclude_unset pattern as
    ProjectService.update_project)."""

    model_config = ConfigDict(extra="forbid")

    corrected_text: str | None = None
    material_name: str | None = None
    material_code: str | None = None
    thickness_mm: float | None = Field(default=None, ge=0)


class RegionSelectionRequest(BaseModel):
    """Normalized page-fraction coordinates -- see the R3 coordinate
    contract. x/y must be within [0, 1); width/height must be strictly
    positive and at most 1 -- this alone rejects negative coordinates and
    zero-size selections before LegendCropService's own defensive check
    ever runs. "Selection extends beyond the page" (x + width > 1) is
    still only checked in RegionSelection.__post_init__, since it's a
    relationship between two fields Pydantic's per-field constraints can't
    express here."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0, lt=1)
    y: float = Field(ge=0, lt=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


class LegendEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    plan_id: uuid.UUID
    plan_page_id: uuid.UUID

    pattern_x: float | None
    pattern_y: float | None
    pattern_width: float | None
    pattern_height: float | None
    # Presence only -- pattern_image_reference itself is never exposed
    # (same precedent as PlanPageResponse not exposing preview_reference).
    has_pattern_selection: bool

    description_x: float | None
    description_y: float | None
    description_width: float | None
    description_height: float | None
    has_description_selection: bool

    raw_ocr_text: str | None
    corrected_text: str | None

    material_name: str | None
    material_code: str | None
    thickness_mm: float | None

    status: LegendEntryStatus
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LegendOcrResponse(LegendEntryResponse):
    """Extends the persisted entry state with ephemeral OCR metadata that
    is never stored beyond raw_ocr_text itself -- provider/confidence/error
    are informational for the UI's trust signal, not a business record."""

    ocr_provider: str
    ocr_confidence: float | None
    ocr_error: str | None
