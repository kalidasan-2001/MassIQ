from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ManualCorrectionType(str, enum.Enum):
    ADD = "add"
    SUBTRACT = "subtract"


class ManualRegionCorrection(Base):
    """R7 scope: one human-drawn geometry correction layered onto a
    specific DetectionRun's review -- either geometry Detection V2 missed
    (ADD) or geometry it wrongly included (SUBTRACT). Deliberately its own
    table, not a fake `DetectedRegion` with a special status (R7 section
    8): a manual correction has no similarity/evidence_coverage/tile_count
    -- it is not a CV result at all, and encoding it as one would blur
    provenance (R6's independent review would have every right to reject
    a "candidate" that was never actually detected).

    Scoped to one DetectionRun (not just one PlanPage): the review
    workflow this supports is "review THIS run's candidates, then add
    what it missed / remove what it wrongly found" -- a second detection
    run on the same page starts a fresh review session with its own
    corrections, exactly as R6 already treats a second run as a fresh set
    of DetectedRegions (see DetectionService.list_runs_for_page).

    Same normalized [0,1] page-fraction coordinate contract as
    LegendEntry/DetectedRegion (R7 section 9) -- no second coordinate
    convention. A plain rectangle, not a polygon, matching DetectedRegion
    and RegionEditor.jsx's own precedent (R7 section 8's geometry field is
    x/y/width/height, not a point list).
    """

    __tablename__ = "manual_region_corrections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("plan_pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    detection_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("detection_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    correction_type: Mapped[ManualCorrectionType] = mapped_column(
        sa.Enum(
            ManualCorrectionType,
            name="manual_correction_type",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )

    x: Mapped[float] = mapped_column(sa.Float, nullable=False)
    y: Mapped[float] = mapped_column(sa.Float, nullable=False)
    width: Mapped[float] = mapped_column(sa.Float, nullable=False)
    height: Mapped[float] = mapped_column(sa.Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )
