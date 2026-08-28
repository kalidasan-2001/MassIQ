from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.quantity_result import QuantityResultStatus


class ResultRowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quantity_result_id: uuid.UUID
    project_id: uuid.UUID
    plan_id: uuid.UUID
    plan_name: str
    plan_page_id: uuid.UUID
    page_number: int
    material_name: str
    material_code: str | None
    area_m2: float
    confirmed_dimension_m: float
    volume_m3: float
    status: QuantityResultStatus
    calculation_version: str
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None
    detection_run_id: uuid.UUID
    reference_type: str
    reference_id: uuid.UUID
    accepted_region_count: int
    rejected_region_count: int
    manual_add_count: int
    manual_subtract_count: int
    scale_method: str | None
