from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PlanProcessingStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    INSPECTING = "inspecting"
    READY = "ready"
    FAILED = "failed"


class PdfType(str, enum.Enum):
    VECTOR = "vector"
    RASTER = "raster"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class Plan(Base):
    """R2 scope: Plan only extends Project with PDF ingestion. LegendEntry,
    HatchPattern, Analysis, Material, Measurement, Export remain R3+.

    A Plan only ever reaches READY once every one of its PlanPage rows and
    page previews exists -- see PlanService.upload_plan for the transaction
    boundary that guarantees this."""

    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # ondelete=CASCADE: a Plan cannot outlive its Project. There is no
    # project-delete endpoint yet (R1 deliberately omitted it), so this is
    # currently unreachable via the API, but it keeps the schema itself from
    # ever allowing an orphaned Plan if deletion is added later at the DB
    # layer without every caller remembering to cascade manually.
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Client-supplied original filename, preserved as display metadata only
    # -- never used to construct a filesystem path (see StorageService).
    original_filename: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    # Storage-root-relative reference (e.g. "plans/<uuid>/original.pdf"),
    # never an absolute machine path -- resolved through StorageService.
    stored_file_reference: Mapped[str] = mapped_column(sa.String(1000), nullable=False)
    page_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    processing_status: Mapped[PlanProcessingStatus] = mapped_column(
        sa.Enum(
            PlanProcessingStatus,
            name="plan_processing_status",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=PlanProcessingStatus.UPLOADED,
        server_default=PlanProcessingStatus.UPLOADED.value,
    )
    pdf_type: Mapped[PdfType] = mapped_column(
        sa.Enum(
            PdfType,
            name="plan_pdf_type",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=PdfType.UNKNOWN,
        server_default=PdfType.UNKNOWN.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

    # Unidirectional (no back_populates on Project) -- avoids touching the
    # R1-approved project.py at all. order_by keeps .pages naturally in
    # page-number order without callers needing to sort.
    pages: Mapped[list["PlanPage"]] = relationship(
        "PlanPage", cascade="all, delete-orphan", order_by="PlanPage.page_number", passive_deletes=True
    )
