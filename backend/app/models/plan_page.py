from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlanPage(Base):
    """One row per PDF page belonging to a Plan.

    page_number convention: 1-based. page_number == 1 is the first page of
    the source PDF (fitz/PyMuPDF's own page index 0). Every reader of this
    column (PdfInspectionService, PlanService, StorageService's preview
    filenames, API responses) uses this same 1-based convention -- there is
    no zero-based numbering anywhere in the R2 pipeline.

    width/height are the PDF page's own geometry in PDF points (1/72 inch),
    taken from PyMuPDF's rotation-adjusted `page.rect` -- i.e. these are the
    page's logical dimensions, not the rendered preview image's pixel
    dimensions (which depend on Settings.plan_render_dpi and can change if
    that setting changes; width/height here do not).
    """

    __tablename__ = "plan_pages"
    __table_args__ = (
        sa.UniqueConstraint("plan_id", "page_number", name="uq_plan_pages_plan_id_page_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    width: Mapped[float] = mapped_column(sa.Float, nullable=False)
    height: Mapped[float] = mapped_column(sa.Float, nullable=False)
    rotation: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    vector_content_available: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    # Storage-root-relative reference (e.g. "plans/<uuid>/pages/0001.png"),
    # nullable only because a row is never actually persisted without one in
    # practice (PlanService creates the preview before the row) -- nullable
    # is kept for schema flexibility per the R2 field spec, not because a
    # committed row is expected to lack a preview.
    preview_reference: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
