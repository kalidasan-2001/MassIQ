from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlanScaleMethod(str, enum.Enum):
    DECLARED_SCALE = "declared_scale"
    CALIBRATED_DISTANCE = "calibrated_distance"


class PlanScale(Base):
    """R7 scope: one confirmed, persisted drawing scale per PlanPage --
    closing the gap the R6 independent review's own audit found (R7
    section 13): the legacy MVP's `scale.pixelsPerMeter` lives only in
    ephemeral `PlanViewer.jsx` React state and is never sent to the
    backend at all. Scale is a property of the page's own drawing, not of
    any one DetectionRun, so it is confirmed once per PlanPage and reused
    by every DetectionRun/QuantityResult computed against that page
    (unique constraint on plan_page_id -- re-confirming replaces the
    existing row in place, matching HatchFeatureSet's own "recompute
    replaces" precedent rather than accumulating history).

    Single authoritative derived number: `real_meters_per_plan_point`.
    QuantityService reads ONLY this field -- it never needs to know which
    method produced it. Both supported methods ultimately resolve to it:

    - DECLARED_SCALE (e.g. "1:100"): assumes the PlanPage's own PDF-point
      geometry (see PlanPage.width/height) represents genuine 100%-print
      physical size -- i.e. 1 PDF point = 1/72 inch of real printed paper
      -- and `declared_ratio` (100) is the printed-paper-to-real-world
      reduction factor architectural drawings conventionally declare.
      real_meters_per_plan_point = POINTS_TO_METERS * declared_ratio.
      This is a documented assumption (see
      docs/architecture/REVIEW_AND_QUANTITY_ENGINE.md), not a guess
      dressed up as fact -- a plan that was NOT exported at 100% print
      scale would need CALIBRATED_DISTANCE instead.
    - CALIBRATED_DISTANCE: the user selects two points on the page and
      enters the true real-world distance between them.
      real_meters_per_plan_point = calibrated_distance_real_m /
      calibrated_distance_plan_points. Never trusts OCR/AI-derived scale
      automatically (R7 section 14) -- both raw calibration inputs are
      kept for reproducibility even though only the derived ratio is
      actually used by QuantityService.

    Confirmation is always an explicit user action -- there is no
    endpoint that writes this row from an OCR/VLM suggestion.
    """

    __tablename__ = "plan_scales"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("plan_pages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    method: Mapped[PlanScaleMethod] = mapped_column(
        sa.Enum(
            PlanScaleMethod,
            name="plan_scale_method",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )

    # Raw method-specific inputs -- kept for reproducibility/auditability
    # (R7 section 15) even though QuantityService never reads them
    # directly. Exactly one method's inputs are populated per row.
    declared_ratio: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    calibrated_distance_plan_points: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    calibrated_distance_real_m: Mapped[float | None] = mapped_column(sa.Float, nullable=True)

    # The single derived number every quantity calculation actually uses.
    real_meters_per_plan_point: Mapped[float] = mapped_column(sa.Float, nullable=False)

    confirmed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )
