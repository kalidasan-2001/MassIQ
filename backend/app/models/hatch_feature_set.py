from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HatchFeatureSet(Base):
    """R4 scope: one deterministic, versioned feature extraction result for
    a single LegendEntry's confirmed pattern crop. One-to-one with
    LegendEntry (a unique constraint on legend_entry_id enforces this) --
    R4 has no evidence multiple simultaneous feature sets per entry are
    needed; recomputation intentionally *replaces* the existing row rather
    than accumulating history (see HatchFeatureService.compute_features).

    Unidirectional FK only, matching LegendEntry's own precedent of not
    adding a relationship/back_populates onto the model it references.

    `dominant_angles` is a plain JSON array of floats (0, 1, or 2 entries)
    -- deliberately not a Postgres array type or pgvector, per R4's
    explicit "do not introduce pgvector in R4" instruction. JSON is a
    clean, migration-safe, portable choice for a small variable-length
    list that is never queried/filtered on at the SQL level in R4.
    """

    __tablename__ = "hatch_feature_sets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    legend_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("legend_entries.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # See hatch/config.py's FEATURE_VERSION -- a dotted string, not an int,
    # so a future minor retune ("1.1") is distinguishable from a semantics
    # change ("2.0"). Never silently overwritten in place: a recompute at
    # a new algorithm version updates this column explicitly, and old rows
    # remain identifiable as having been computed by whatever version they
    # actually were.
    feature_version: Mapped[str] = mapped_column(sa.String(20), nullable=False)

    source_width: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    source_height: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    # List of 0, 1, or 2 angles in [0, 180) -- see app.hatch.models.HatchFeatures.
    dominant_angles: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    is_cross_hatch: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)

    normalized_line_spacing: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    line_density: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)
    normalized_line_width: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    periodicity: Mapped[float | None] = mapped_column(sa.Float, nullable=True)

    color_mean_l: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)
    color_mean_a: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)
    color_mean_b: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)
    color_std_l: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)
    color_std_a: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)
    color_std_b: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)

    # Quality/evidence metadata -- see R4 section 18. Never a fabricated
    # overall confidence score; each corresponds to a directly measured
    # quantity from the extraction that produced this row.
    detected_line_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    angle_evidence_strength: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)
    spacing_available: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    periodicity_available: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )
