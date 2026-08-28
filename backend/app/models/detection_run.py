from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DetectionRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DetectionRun(Base):
    """R6 scope: one execution of Detection Engine V2 over a single
    PlanPage, scanning for regions that resemble a reference hatch
    pattern. Produces CANDIDATE `DetectedRegion` rows only -- see
    app.services.detection_service's module docstring for the explicit,
    structural guarantee that nothing here ever touches a quantity/area/
    volume field (R6 section 23's non-negotiable separation).

    Reference provenance (R6 section 3): exactly one of
    `reference_legend_entry_id` / `reference_pattern_library_entry_id` is
    set, enforced by a DB CHECK constraint (not just application code) --
    a run always originates from a confirmed LegendEntry with a
    current-version HatchFeatureSet, or a project's own PatternLibraryEntry
    (which itself already traces back through the same chain, per R5). No
    arbitrary image path is ever accepted (R6 section 3).

    `detector_version` + `feature_version` + `parameters` (the exact
    tile_size_px/stride_px/candidate_threshold/min_evidence_coverage used)
    together make every run's algorithm semantics fully reproducible --
    R6 section 5's explicit "do not silently change tile size/threshold/
    merging rules later without versioning."
    """

    __tablename__ = "detection_runs"
    __table_args__ = (
        sa.CheckConstraint(
            "(reference_legend_entry_id IS NOT NULL) != (reference_pattern_library_entry_id IS NOT NULL)",
            name="ck_detection_runs_exactly_one_reference",
        ),
    )

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

    reference_legend_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("legend_entries.id", ondelete="CASCADE"), nullable=True, index=True
    )
    reference_pattern_library_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("pattern_library_entries.id", ondelete="CASCADE"), nullable=True, index=True
    )

    feature_version: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    detector_version: Mapped[str] = mapped_column(sa.String(20), nullable=False)

    status: Mapped[DetectionRunStatus] = mapped_column(
        sa.Enum(
            DetectionRunStatus,
            name="detection_run_status",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=DetectionRunStatus.PENDING,
        server_default=DetectionRunStatus.PENDING.value,
    )

    # The exact parameters this run used (tile_size_px, stride_px,
    # candidate_threshold, min_evidence_coverage) -- see the class
    # docstring's reproducibility note. JSON, not individual columns:
    # deliberately schema-flexible so a future detector_version can add a
    # parameter without a migration, while detector_version itself still
    # gates *interpretation* of what's in here.
    parameters: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)

    tile_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    tiles_evaluated: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    tiles_skipped: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    candidate_region_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    # Safe, human-readable failure reason only -- never a raw traceback
    # (R6 section 27/35's explicit "do not expose raw stack traces").
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
