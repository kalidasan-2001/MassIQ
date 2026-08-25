from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LegendEntryStatus(str, enum.Enum):
    DRAFT = "draft"
    OCR_COMPLETE = "ocr_complete"
    CONFIRMED = "confirmed"


class LegendEntry(Base):
    """R3 scope: one confirmed (or in-progress) hatch-pattern -> material
    mapping for a single PlanPage. Deliberately NOT the Pattern Library,
    NOT hatch feature extraction, NOT automatic material classification --
    every field that ends up on a CONFIRMED entry passed through an
    explicit user action (see LegendService.confirm's required-field check).

    Provenance is structural: `raw_ocr_text` is written exactly once, by
    the /ocr endpoint, and never overwritten afterward; `corrected_text` is
    written only by the user-facing PATCH. This distinction is preserved on
    purpose -- it is what lets a later release evaluate OCR quality.

    Unidirectional FKs only (no relationship/back_populates added to Plan or
    PlanPage), matching Plan's own precedent of not touching Project when it
    was introduced. All three of project_id/plan_id/plan_page_id are stored
    for query convenience and defense-in-depth, but a client never supplies
    plan_page_id directly -- LegendService always resolves it via
    PlanService.get_page(project_id, plan_id, page_number), so the three
    IDs are mutually consistent by construction, not by trusting the client.
    """

    __tablename__ = "legend_entries"

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

    # Hatch-pattern selection -- normalized page-fraction coordinates in
    # [0, 1], relative to the persisted preview image's own pixel
    # dimensions (see LegendCropService). Never DOM/screen pixels.
    pattern_x: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    pattern_y: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    pattern_width: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    pattern_height: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    # Storage-root-relative reference (e.g. "plans/<plan_id>/legend/<id>/pattern.png"),
    # resolved only through StorageService -- never an absolute machine path.
    pattern_image_reference: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)

    # Description/text selection -- same coordinate contract as pattern_*.
    description_x: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    description_y: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    description_width: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    description_height: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    description_image_reference: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)

    # Text provenance: raw OCR output, then the user's corrected version.
    raw_ocr_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    corrected_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    # Material confirmation -- deliberately just these three fields for R3.
    # No Materials table, no taxonomy: see LegendService.confirm and the R3
    # checklist's "Do not build a global taxonomy" note.
    material_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    material_code: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    thickness_mm: Mapped[float | None] = mapped_column(sa.Float, nullable=True)

    status: Mapped[LegendEntryStatus] = mapped_column(
        sa.Enum(
            LegendEntryStatus,
            name="legend_entry_status",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=LegendEntryStatus.DRAFT,
        server_default=LegendEntryStatus.DRAFT.value,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

    @property
    def has_pattern_selection(self) -> bool:
        """Plain (non-mapped) property, not a column -- read by
        LegendEntryResponse's from_attributes serialization. Deliberately
        exposes only presence, not `pattern_image_reference` itself, same
        precedent as PlanPageResponse not exposing `preview_reference`:
        internal storage layout is never handed to the client."""
        return self.pattern_image_reference is not None

    @property
    def has_description_selection(self) -> bool:
        return self.description_image_reference is not None
