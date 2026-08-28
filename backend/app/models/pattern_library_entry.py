from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PatternLibraryEntry(Base):
    """R5 scope: one project-scoped, human-confirmed hatch-pattern ->
    material association, reusable as a similarity-search candidate for
    future hatches in the SAME project. Deliberately project-scoped only
    -- no planning-office/company/global library exists yet (see
    docs/architecture/PATTERN_LIBRARY.md's "future hierarchy" section,
    documented but not implemented).

    Provenance is structural, not incidental: `source_legend_entry_id` and
    `hatch_feature_set_id` are the two facts that let every library entry
    be traced back to Project -> Plan -> LegendEntry -> pattern crop ->
    confirmed material -> HatchFeatureSet. R5 does not allow an "anonymous"
    library entry with no such trail (see PatternLibraryService.add_entry).

    Deliberately does NOT duplicate HatchFeatureSet's own columns (angles,
    spacing, etc.) -- `hatch_feature_set_id` is a reference to the single
    authoritative, versioned feature record; the similarity engine always
    reads features from there, never from a stale copy on this table.

    Duplicate policy (R5 section 7): `source_legend_entry_id` carries a
    unique constraint, so at most one PatternLibraryEntry can ever exist
    per source LegendEntry. Re-adding the same LegendEntry to the library
    (e.g. the user re-confirms material info and adds it again) UPDATES
    this same row in place -- refreshing the material fields and the
    `hatch_feature_set_id` reference, and incrementing `confirmation_count`
    -- rather than creating a second, ambiguous entry. See
    PatternLibraryService.add_entry for the exact update-vs-insert logic.
    """

    __tablename__ = "pattern_library_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_legend_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("legend_entries.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    hatch_feature_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("hatch_feature_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # R5 does not introduce a Material Catalog (see R5 section 8) -- these
    # are copied from the source LegendEntry's own confirmed fields at
    # add-time (and refreshed on every subsequent re-add), the same
    # deliberately minimal shape LegendEntry itself uses.
    canonical_material_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    material_code: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    thickness_mm: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    # The source LegendEntry's corrected_text at add-time -- the original,
    # free-text label a human actually saw next to the hatch, kept
    # alongside the more structured canonical_material_name for context.
    original_label: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    # Incremented every time this exact source LegendEntry is (re-)added to
    # the library, rather than creating a duplicate row -- see the
    # class docstring's "Duplicate policy" note.
    confirmation_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)

    # Soft-retirement flag for a future "remove from library" workflow --
    # not exercised by any R5 endpoint yet (no delete/deactivate route),
    # included now because a nullable boolean is free at the schema level
    # and avoids a second migration the first time R6 needs it.
    active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )
