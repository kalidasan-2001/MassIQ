"""Pure data structures for the R5 similarity engine -- deliberately not
SQLAlchemy models and deliberately independent of `HatchFeatureSet`'s
persistence shape, mirroring R4's own separation of CV data structures
from the ORM (see `app.hatch.models`). Nothing in `app/hatch/similarity/`
touches the database, FastAPI, or the filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ComparableFeatures:
    """The subset of a HatchFeatureSet's fields the similarity engine
    actually compares. Deliberately duck-typed via `from_features()`
    rather than importing the SQLAlchemy model -- this lets the same
    similarity code run against a persisted `HatchFeatureSet` row, an
    in-memory `HatchFeatures` dataclass, or a synthetic test fixture,
    with zero coupling to how the caller obtained the data.
    """

    feature_version: str
    dominant_angles: list[float]
    is_cross_hatch: bool | None
    normalized_line_spacing: float | None
    line_density: float
    normalized_line_width: float | None
    periodicity: float | None
    color_mean_l: float
    color_mean_a: float
    color_mean_b: float

    @classmethod
    def from_features(cls, obj) -> "ComparableFeatures":
        """Builds a ComparableFeatures from anything exposing the same
        attribute names as `HatchFeatureSet`/`HatchFeatures` -- an ORM row
        or a plain dataclass both work identically."""
        return cls(
            feature_version=obj.feature_version,
            dominant_angles=list(obj.dominant_angles or []),
            is_cross_hatch=obj.is_cross_hatch,
            normalized_line_spacing=obj.normalized_line_spacing,
            line_density=obj.line_density,
            normalized_line_width=obj.normalized_line_width,
            periodicity=obj.periodicity,
            color_mean_l=obj.color_mean_l,
            color_mean_a=obj.color_mean_a,
            color_mean_b=obj.color_mean_b,
        )


@dataclass(frozen=True)
class ComponentScore:
    """One similarity component's result. `available=False` means this
    component was excluded from the combined score entirely (missing
    evidence on one or both sides) -- `score` is then meaningless (0.0
    placeholder) and must never be included in a weighted average.
    Missing evidence and negative/low evidence are different: a `None`
    feature produces `available=False`, never a fabricated low score."""

    available: bool
    score: float = 0.0


@dataclass(frozen=True)
class SimilarityResult:
    """Result of comparing two feature sets. `comparable=False` (feature
    version mismatch) means `overall_similarity` and `components` carry no
    meaning and must not be sorted/ranked against comparable results --
    see combined_similarity.py's explicit version-compatibility gate.

    `overall_similarity` is a SIMILARITY score, not a probability and not
    a confidence that any material association is correct -- see R5's
    explicit naming requirement in docs/architecture/PATTERN_LIBRARY.md.
    """

    comparable: bool
    reason: str | None = None  # e.g. "feature_version_mismatch" when comparable=False
    overall_similarity: float | None = None
    components: dict[str, ComponentScore] = field(default_factory=dict)
    # Sum of the component weights that were actually available, out of a
    # total weight budget of 1.0 (see similarity/config.py's *_WEIGHT
    # constants). This is quality metadata, exactly like R4's
    # `angle_evidence_strength`/`*_available` flags -- NOT a confidence
    # score, and never presented to a user as one. It exists so a caller
    # can tell "this 0.8 similarity came from comparing nearly every
    # feature" apart from "this 0.8 came from density and color alone
    # because nothing else was measurable" -- see combined_similarity.py's
    # negative-control finding (docs/testing/R5_PATTERN_LIBRARY_BENCHMARK.md).
    evidence_coverage: float = 0.0
