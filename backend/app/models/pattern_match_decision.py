from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MatchDecision(str, enum.Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MANUAL = "manual"


class PatternMatchDecision(Base):
    """R5 section 25-26: an append-only, immutable log of what a user did
    with a library-suggested match (or chose to enter manually instead).

    Deliberately has no `updated_at` and no update path anywhere in
    PatternLibraryService -- every decision is a new row. This is what
    "do not silently overwrite history" (R5 section 26) means concretely:
    if a user first accepts a suggestion and later changes their mind, a
    SECOND row is written recording the correction, not an edit to the
    first. `similarity_at_decision` freezes what the similarity score
    actually was at decision time, independent of whatever the library or
    a future re-scoring might compute later.

    Not used to train anything in R5 (see R5 section 25's explicit
    instruction) -- this is purely a persisted history/audit trail for
    now, intended as future labelled data for evaluating matcher quality.
    """

    __tablename__ = "pattern_match_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Denormalized alongside candidate_legend_entry_id specifically so
    # project-isolation queries/tests never need to join through
    # LegendEntry just to filter by project -- same rationale as
    # PatternLibraryEntry's own project_id.
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_legend_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("legend_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable: a MANUAL decision (the user never looked at or acted on a
    # suggestion) has no suggested entry at all. SET NULL (not CASCADE) on
    # delete -- if the suggested library entry is ever removed later, this
    # historical decision record must survive, only losing the now-dangling
    # reference, never disappearing itself.
    suggested_library_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("pattern_library_entries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    similarity_at_decision: Mapped[float | None] = mapped_column(sa.Float, nullable=True)

    decision: Mapped[MatchDecision] = mapped_column(
        sa.Enum(
            MatchDecision,
            name="pattern_match_decision_kind",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    confirmed_material_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
