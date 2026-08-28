"""Pure data structures for the R6 Detection Engine V2 -- deliberately not
SQLAlchemy models (mirrors R4's `hatch.models`/R5's `hatch.similarity.models`
separation of CV data structures from persistence). Nothing in
`app/detection/` (this module included) touches the database, FastAPI, or
the filesystem directly -- `DetectionService`
(backend/app/services/detection_service.py) is the only thing that
resolves a page image and persists results.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Tile:
    """One tile's geometry -- both pixel (for cropping the source image)
    and normalized page-fraction (for persistence/display, matching the
    R3 coordinate contract every other overlay in this app already uses)."""

    row: int
    col: int
    x_px: int
    y_px: int
    width_px: int
    height_px: int
    x: float  # normalized [0, 1]
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class TileEvaluation:
    """One tile's result -- the "similarity map" R6 section 11 requires,
    at minimum: location, similarity, evidence coverage. `scored=False`
    means the tile was skipped by quality gating (R6 section 9) before
    ever being compared against the reference -- `similarity` and
    `evidence_coverage` are then meaningless placeholders, never a
    fabricated low score standing in for "we didn't check this tile."
    """

    tile: Tile
    scored: bool
    similarity: float = 0.0
    evidence_coverage: float = 0.0
    is_candidate: bool = False


@dataclass(frozen=True)
class CandidateRegion:
    """One merged group of adjacent candidate tiles -- a bounding box in
    both pixel and normalized coordinates, plus a defensible region-level
    score (see detection/scoring.py). `tile_count` and `contributing_tiles`
    exist for debugging/explainability, mirroring R4/R5's own quality-
    metadata discipline -- never a fabricated confidence, just what was
    actually measured."""

    x: float
    y: float
    width: float
    height: float
    similarity: float
    evidence_coverage: float
    tile_count: int
    contributing_tiles: list[TileEvaluation] = field(default_factory=list)


@dataclass(frozen=True)
class DetectionResult:
    """The full, pure output of one detection run over one page image --
    everything `DetectionService` needs to persist, and nothing more."""

    tiles_evaluated: int
    tiles_skipped: int
    candidate_regions: list[CandidateRegion]
