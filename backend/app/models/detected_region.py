from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DetectedRegionStatus(str, enum.Enum):
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class DetectedRegion(Base):
    """R6 scope: one merged candidate region produced by a DetectionRun --
    a rectangle (the same normalized page-fraction coordinate contract
    every other overlay in this app uses, see LegendEntry's own pattern_x/
    y/width/height), a region-level similarity/evidence_coverage score
    (see app.detection.scoring's median/mean choice), and a review status
    a human explicitly changes via PATCH.

    Deliberately a bounding box, not a polygon (R6 section 14) -- the
    existing correction/quantity pipeline (RegionEditor.jsx,
    quantityEngine.js) already works with rectangles.

    `status` starts CANDIDATE and is changed only by an explicit user
    action (ACCEPTED/REJECTED) -- see DetectionService.update_region_status.
    Nothing in R6 ever changes this automatically, and nothing in R6 ever
    reads an ACCEPTED region to compute area/volume itself -- that
    remains entirely the existing frontend quantityEngine's job, over
    user-supplied state, per R6 section 23.
    """

    __tablename__ = "detected_regions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    detection_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("detection_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    x: Mapped[float] = mapped_column(sa.Float, nullable=False)
    y: Mapped[float] = mapped_column(sa.Float, nullable=False)
    width: Mapped[float] = mapped_column(sa.Float, nullable=False)
    height: Mapped[float] = mapped_column(sa.Float, nullable=False)

    similarity: Mapped[float] = mapped_column(sa.Float, nullable=False)
    evidence_coverage: Mapped[float] = mapped_column(sa.Float, nullable=False)
    tile_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    status: Mapped[DetectedRegionStatus] = mapped_column(
        sa.Enum(
            DetectedRegionStatus,
            name="detected_region_status",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=DetectedRegionStatus.CANDIDATE,
        server_default=DetectedRegionStatus.CANDIDATE.value,
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )
