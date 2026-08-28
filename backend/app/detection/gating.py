"""Tile quality gating (R6 section 9).

Decides whether a tile's extracted HatchFeatures carry enough evidence to
be worth comparing against the reference at all. A blank margin, a patch
of dimension-line text, or a mostly-empty tile at a page edge should never
be scored as if it were a real candidate -- but it must still be counted
(never silently dropped), so callers can see how many tiles were skipped
and why, for debugging and for the benchmark doc's honest reporting.
"""

from __future__ import annotations

from app.hatch.models import HatchFeatures

from .config import REQUIRE_ANGLE_EVIDENCE_TO_SCORE


def tile_passes_quality_gate(features: HatchFeatures) -> bool:
    """Mirrors R4's own angle-evidence gate (MIN_ANGLE_EVIDENCE_PX) rather
    than reintroducing a second, independently-tuned threshold: a tile
    with an empty `dominant_angles` list already means R4's extractor
    found no reliable line-orientation evidence at all, which is exactly
    the "meaningless blank tile" case R6 section 9 asks to filter out."""
    if not REQUIRE_ANGLE_EVIDENCE_TO_SCORE:
        return True
    return len(features.dominant_angles) > 0
