from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.manual_region_correction import ManualCorrectionType


class ManualCorrectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correction_type: ManualCorrectionType
    # Same normalized [0,1] page-fraction contract as every other
    # geometry field in this app (R7 section 9) -- schema-layer bounds
    # match RegionSelectionRequest's own precedent (R3's legend_entry.py).
    x: float = Field(ge=0, lt=1)
    y: float = Field(ge=0, lt=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


class ManualCorrectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    detection_run_id: uuid.UUID
    correction_type: ManualCorrectionType
    x: float
    y: float
    width: float
    height: float
    created_at: datetime
    updated_at: datetime
