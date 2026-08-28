from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.plan_scale import PlanScaleMethod


class ConfirmPlanScaleRequest(BaseModel):
    """Exactly one method's inputs must be provided (R7 sections 13-14) --
    validated here AND again in PlanScaleService (defense in depth, same
    pattern every other R3-R6 write endpoint in this codebase uses)."""

    model_config = ConfigDict(extra="forbid")

    method: PlanScaleMethod
    declared_ratio: float | None = Field(default=None, gt=0)
    calibrated_distance_plan_points: float | None = Field(default=None, gt=0)
    calibrated_distance_real_m: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _matching_inputs_for_method(self) -> "ConfirmPlanScaleRequest":
        if self.method == PlanScaleMethod.DECLARED_SCALE:
            if self.declared_ratio is None:
                raise ValueError("declared_ratio is required for method=declared_scale")
        else:
            if self.calibrated_distance_plan_points is None or self.calibrated_distance_real_m is None:
                raise ValueError(
                    "calibrated_distance_plan_points and calibrated_distance_real_m are required "
                    "for method=calibrated_distance"
                )
        return self


class PlanScaleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_page_id: uuid.UUID
    method: PlanScaleMethod
    declared_ratio: float | None
    calibrated_distance_plan_points: float | None
    calibrated_distance_real_m: float | None
    real_meters_per_plan_point: float
    confirmed_at: datetime
