from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.detected_region import DetectedRegionStatus
from app.models.detection_run import DetectionRunStatus


class StartDetectionRunRequest(BaseModel):
    """Exactly one of `legend_entry_id` / `pattern_library_entry_id` must
    be provided (R6 section 3) -- validated here at the schema boundary
    AND again in DetectionService (defense in depth, same pattern R3's
    RegionSelection uses)."""

    model_config = ConfigDict(extra="forbid")

    legend_entry_id: uuid.UUID | None = None
    pattern_library_entry_id: uuid.UUID | None = None

    # Optional overrides of app.detection.config's named defaults --
    # exposed for benchmarking/calibration, never required for normal use.
    tile_size_px: int | None = Field(default=None, gt=0)
    stride_px: int | None = Field(default=None, gt=0)
    candidate_threshold: float | None = Field(default=None, ge=0, le=1)
    min_evidence_coverage: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def _exactly_one_reference(self) -> "StartDetectionRunRequest":
        if (self.legend_entry_id is None) == (self.pattern_library_entry_id is None):
            raise ValueError("Exactly one of legend_entry_id or pattern_library_entry_id is required")
        return self


class DetectionRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    plan_id: uuid.UUID
    plan_page_id: uuid.UUID
    reference_legend_entry_id: uuid.UUID | None
    reference_pattern_library_entry_id: uuid.UUID | None

    feature_version: str
    detector_version: str
    status: DetectionRunStatus
    parameters: dict

    tile_count: int
    tiles_evaluated: int
    tiles_skipped: int
    candidate_region_count: int
    error_message: str | None

    created_at: datetime
    completed_at: datetime | None


class DetectedRegionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    detection_run_id: uuid.UUID

    x: float
    y: float
    width: float
    height: float

    # Explicitly "similarity" -- same R5 naming discipline (never
    # confidence/probability). A region-level structural resemblance
    # score, not a statement that the material association is correct.
    similarity: float = Field(ge=0, le=1)
    evidence_coverage: float = Field(ge=0, le=1)
    tile_count: int

    status: DetectedRegionStatus
    created_at: datetime
    updated_at: datetime


class UpdateRegionStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: DetectedRegionStatus
