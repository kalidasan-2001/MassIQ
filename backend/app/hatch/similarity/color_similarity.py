"""Color similarity (R5 section 17) -- low-weight supporting evidence.

Construction-drawing crops vary in apparent color for reasons that have
nothing to do with the actual hatch pattern or material: scanner
brightness/exposure, grayscale-only printing, a different PDF export
pipeline. Color must never be allowed to overwhelm structural (angle/
spacing) evidence -- see config.py's COLOR_WEIGHT, deliberately the
lowest weight in the combined score.

Uses CIE76 (plain Euclidean) distance in the same OpenCV 8-bit LAB space
`hatch/color.py` already computes features in -- not the textbook LAB
ranges. Always available: `color_mean_l/a/b` are never None (see
hatch/color.py), so there is no missing-evidence case here, only more or
less similar color.
"""

from __future__ import annotations

import math

from .config import COLOR_MAX_LAB_DISTANCE
from .models import ComponentScore


def color_similarity(
    reference_lab: tuple[float, float, float],
    candidate_lab: tuple[float, float, float],
) -> ComponentScore:
    l1, a1, b1 = reference_lab
    l2, a2, b2 = candidate_lab
    distance = math.sqrt((l1 - l2) ** 2 + (a1 - a2) ** 2 + (b1 - b2) ** 2)
    similarity = max(0.0, min(1.0, 1.0 - distance / COLOR_MAX_LAB_DISTANCE))
    return ComponentScore(available=True, score=similarity)
