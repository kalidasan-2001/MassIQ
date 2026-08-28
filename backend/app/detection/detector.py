"""Detection V2 orchestrator (R6 sections 6-15) -- the one entry point that
wires tiling, R4 feature extraction, quality gating, R5 similarity
scoring, and merging together into a single deterministic
`run_detection(page_image, reference_features) -> DetectionResult` call.
Mirrors R4's `HatchFeatureExtractor`/R5's `combined_similarity.compare`:
a thin, near-pure orchestrator -- every actual algorithm lives in its own
small module (tiler, gating, merging, scoring), and this class holds no
state between calls.

Never touches the database, FastAPI, or the filesystem -- `DetectionService`
(backend/app/services/detection_service.py) is the only thing that
resolves a page image, resolves a reference, and persists results.

Feature-version consistency (R6 section 8) is automatic, not incidental:
every tile is extracted with the exact same `HatchFeatureExtractor`
instance/class the reference was (or would be) extracted with, so a tile's
`feature_version` always matches `hatch.config.FEATURE_VERSION` at run
time -- there is no separate, potentially-drifting tile-specific
extractor. `combined_similarity.compare`'s own feature-version gate is
still consulted (never bypassed) for defense in depth.
"""

from __future__ import annotations

import logging

import numpy as np

from app.hatch.feature_extractor import HatchFeatureExtractor
from app.hatch.preprocessing import InvalidHatchImageError
from app.hatch.similarity.combined_similarity import compare
from app.hatch.similarity.models import ComparableFeatures

from .config import CANDIDATE_SIMILARITY_THRESHOLD, MAX_TILES_PER_RUN, MIN_EVIDENCE_COVERAGE_FOR_CANDIDATE
from .gating import tile_passes_quality_gate
from .merging import group_candidate_tiles
from .models import DetectionResult, Tile, TileEvaluation
from .scoring import score_regions
from .tiler import generate_tiles

logger = logging.getLogger(__name__)


class TooManyTilesError(ValueError):
    """Raised when a page would produce more tiles than MAX_TILES_PER_RUN
    -- a controlled, explicit rejection rather than an unbounded synchronous
    request (R6 section 26's safety concern)."""


def _extract_tile_features(page_image: np.ndarray, tile: Tile, extractor: HatchFeatureExtractor):
    crop = page_image[tile.y_px : tile.y_px + tile.height_px, tile.x_px : tile.x_px + tile.width_px]
    try:
        return extractor.extract(crop)
    except InvalidHatchImageError:
        # A degenerate tile (below hatch.config.MIN_IMAGE_DIMENSION_PX --
        # only possible for a clipped tile at the page's own edge, see
        # tiler.py) is a legitimate skip, not a run failure.
        return None


def run_detection(
    page_image: np.ndarray,
    reference_features,  # ComparableFeatures
    tile_size_px: int | None = None,
    stride_px: int | None = None,
    candidate_threshold: float = CANDIDATE_SIMILARITY_THRESHOLD,
    min_evidence_coverage: float = MIN_EVIDENCE_COVERAGE_FOR_CANDIDATE,
) -> DetectionResult:
    page_height_px, page_width_px = page_image.shape[:2]
    tile_kwargs = {}
    if tile_size_px is not None:
        tile_kwargs["tile_size_px"] = tile_size_px
    if stride_px is not None:
        tile_kwargs["stride_px"] = stride_px
    tiles = generate_tiles(page_width_px, page_height_px, **tile_kwargs)

    if len(tiles) > MAX_TILES_PER_RUN:
        raise TooManyTilesError(
            f"Page would produce {len(tiles)} tiles, exceeding the {MAX_TILES_PER_RUN} safety cap"
        )

    extractor = HatchFeatureExtractor()
    evaluations: list[TileEvaluation] = []
    tiles_evaluated = 0
    tiles_skipped = 0

    for tile in tiles:
        features = _extract_tile_features(page_image, tile, extractor)
        if features is None or not tile_passes_quality_gate(features):
            tiles_skipped += 1
            evaluations.append(TileEvaluation(tile=tile, scored=False))
            continue

        candidate_features = ComparableFeatures.from_features(features)
        result = compare(reference_features, candidate_features)
        tiles_evaluated += 1
        if not result.comparable:
            # Defense in depth (see module docstring) -- should not occur
            # in practice since tiles and the reference share the same
            # FEATURE_VERSION at run time, but never treated as a match.
            evaluations.append(TileEvaluation(tile=tile, scored=True, similarity=0.0, evidence_coverage=0.0))
            continue

        is_candidate = (
            result.overall_similarity >= candidate_threshold
            and result.evidence_coverage >= min_evidence_coverage
        )
        evaluations.append(
            TileEvaluation(
                tile=tile,
                scored=True,
                similarity=result.overall_similarity,
                evidence_coverage=result.evidence_coverage,
                is_candidate=is_candidate,
            )
        )

    groups = group_candidate_tiles(evaluations)
    candidate_regions = score_regions(groups)

    logger.info(
        "detection_run_core tiles_total=%d tiles_evaluated=%d tiles_skipped=%d candidate_regions=%d",
        len(tiles), tiles_evaluated, tiles_skipped, len(candidate_regions),
    )

    return DetectionResult(
        tiles_evaluated=tiles_evaluated,
        tiles_skipped=tiles_skipped,
        candidate_regions=candidate_regions,
    )
