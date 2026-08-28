from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class QuantityResultStatus(str, enum.Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"


class QuantityResult(Base):
    """R7 scope: the one authoritative, backend-computed, persisted
    quantity for a DetectionRun's reviewed geometry (R7 section 18).
    Unique on detection_run_id -- recalculation UPDATES this same row in
    place rather than accumulating duplicate rows (R7 section 21's
    idempotence policy: same persisted review state always produces the
    same result, and asking again reuses/refreshes the current row).

    Deliberately does NOT duplicate region/correction geometry (R7 section
    18) -- DetectedRegion/ManualRegionCorrection remain the provenance;
    this row stores only the computed numbers plus enough summary counts
    (accepted/manual add/manual subtract) to make the result auditable
    (R7 section 46) without re-querying three tables just to sanity-check
    what went into it.

    `calculation_version` (see app.geometry.config.CALCULATION_VERSION) is
    recorded on every row for the same reason DetectionRun records
    `detector_version` -- a future change to the union/subtraction or
    rounding semantics must never be silently compared against an older
    result as if equivalent.
    """

    __tablename__ = "quantity_results"

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
        UUID(as_uuid=True),
        sa.ForeignKey("detection_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    final_area_m2: Mapped[float] = mapped_column(sa.Float, nullable=False)
    confirmed_dimension_m: Mapped[float] = mapped_column(sa.Float, nullable=False)
    volume_m3: Mapped[float] = mapped_column(sa.Float, nullable=False)

    calculation_version: Mapped[str] = mapped_column(sa.String(20), nullable=False)

    status: Mapped[QuantityResultStatus] = mapped_column(
        sa.Enum(
            QuantityResultStatus,
            name="quantity_result_status",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=QuantityResultStatus.DRAFT,
        server_default=QuantityResultStatus.DRAFT.value,
    )

    # Auditability summary (R7 section 46) -- cheap denormalized counts,
    # not a duplicate of the actual geometry rows.
    accepted_region_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    manual_add_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    manual_subtract_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
