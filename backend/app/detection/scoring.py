"""Region scoring and geometry (R6 section 14-15).

Turns one group of connected candidate tiles (from merging.py) into a
single CandidateRegion: a bounding-box union of the member tiles'
normalized rects, plus a defensible summary score.

Score choice, documented (R6 section 15 requires this): MEDIAN tile
similarity, not max or mean. A single strong tile at a region's edge
should not make a mostly-weak region look confidently scored (max would
do this); a plain mean is more sensitive than the median to a handful of
low-evidence-but-still-candidate tiles the merge step may have included
near a region's boundary. Evidence coverage is aggregated as a plain mean
-- coverage does not carry the same single-outlier risk similarity does,
so there is no reason to prefer the median there.
"""

from __future__ import annotations

import statistics

from .models import CandidateRegion, TileEvaluation


def score_region(group: list[TileEvaluation]) -> CandidateRegion:
    similarities = [e.similarity for e in group]
    coverages = [e.evidence_coverage for e in group]

    left = min(e.tile.x for e in group)
    top = min(e.tile.y for e in group)
    right = max(e.tile.x + e.tile.width for e in group)
    bottom = max(e.tile.y + e.tile.height for e in group)

    return CandidateRegion(
        x=left,
        y=top,
        width=right - left,
        height=bottom - top,
        similarity=statistics.median(similarities),
        evidence_coverage=statistics.mean(coverages),
        tile_count=len(group),
        contributing_tiles=list(group),
    )


def score_regions(groups: list[list[TileEvaluation]]) -> list[CandidateRegion]:
    return [score_region(group) for group in groups]
