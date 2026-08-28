from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.quantity_result import QuantityResultStatus


class CalculateQuantityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # R7 section 17 -- an explicitly confirmed dimension, never silently
    # derived from LegendEntry.thickness_mm/similarity/OCR. The frontend
    # may pre-fill its form with thickness_mm as a suggestion, but this
    # field is what the user actually confirmed.
    confirmed_dimension_m: float = Field(gt=0)


class QuantityResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    detection_run_id: uuid.UUID
    final_area_m2: float
    confirmed_dimension_m: float
    volume_m3: float
    calculation_version: str
    status: QuantityResultStatus
    accepted_region_count: int
    manual_add_count: int
    manual_subtract_count: int
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None
