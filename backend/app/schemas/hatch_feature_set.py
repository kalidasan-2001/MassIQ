from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ComputeFeaturesRequest(BaseModel):
    """`force=True` recomputes even if a feature set already exists at the
    current algorithm version -- see R4's recomputation policy
    (HatchFeatureService.compute_features). Ordinary GETs never trigger
    computation; only this explicit POST does."""

    model_config = ConfigDict(extra="forbid")

    force: bool = False


class HatchFeatureSetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    legend_entry_id: uuid.UUID
    feature_version: str

    source_width: int
    source_height: int

    dominant_angles: list[float]
    is_cross_hatch: bool | None

    normalized_line_spacing: float | None
    line_density: float = Field(ge=0, le=1)
    normalized_line_width: float | None
    periodicity: float | None

    color_mean_l: float
    color_mean_a: float
    color_mean_b: float
    color_std_l: float
    color_std_a: float
    color_std_b: float

    detected_line_count: int
    angle_evidence_strength: float
    spacing_available: bool
    periodicity_available: bool

    created_at: datetime
    updated_at: datetime
