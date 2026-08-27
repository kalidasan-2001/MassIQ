"""Pure data structures for the Hatch Feature Engine -- deliberately not
SQLAlchemy models. `app.models.hatch_feature_set.HatchFeatureSet` (the
persisted row) is a separate, thin translation of `HatchFeatures` into a
database table; nothing in this module touches the database, FastAPI, or
any other framework, so it stays trivially unit-testable in isolation
(R4 section 3's "the CV logic must remain separately testable").
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AngleEvidence:
    """Output of dominant-angle extraction. `primary_angle_deg` /
    `secondary_angle_deg` are None when there isn't enough reliable line
    evidence to report an angle at all -- see config.MIN_ANGLE_EVIDENCE_PX.
    Angles are normalized into [0, 180) (see normalization.py)."""

    primary_angle_deg: float | None
    primary_evidence_px: float
    secondary_angle_deg: float | None
    secondary_evidence_px: float
    line_count: int


@dataclass(frozen=True)
class HatchFeatures:
    """One deterministic feature extraction result for a single hatch
    pattern crop. `feature_version` records which algorithm revision
    produced these values -- see config.FEATURE_VERSION and
    HATCH_FEATURE_ENGINE.md's "Feature versioning" section."""

    feature_version: str

    source_width: int
    source_height: int

    # Angle: 0, 1 (single direction), or 2 (cross-hatch) entries, each in
    # [0, 180). Empty when no reliable line evidence was found at all.
    dominant_angles: list[float] = field(default_factory=list)
    is_cross_hatch: bool | None = None  # None = undetermined (no reliable primary angle)

    normalized_line_spacing: float | None = None
    line_density: float = 0.0
    normalized_line_width: float | None = None
    periodicity: float | None = None

    color_mean_l: float = 0.0
    color_mean_a: float = 0.0
    color_mean_b: float = 0.0
    color_std_l: float = 0.0
    color_std_a: float = 0.0
    color_std_b: float = 0.0

    # Quality/evidence metadata -- see R4 section 18. Never a fabricated
    # "confidence percentage"; each field corresponds to a directly
    # measured quantity from the extraction itself.
    detected_line_count: int = 0
    angle_evidence_strength: float = 0.0
    spacing_available: bool = False
    periodicity_available: bool = False
