"""Line-density similarity (R5 section 14).

R4's `line_density` is always a plain float in [0, 1] -- never nullable
(compute_density returns 0.0 for a blank crop, never None; see
hatch/density.py). So density is always "available" as a comparison, but
is deliberately a supporting signal, not a primary structural one -- its
similarity weight (see config.py's DENSITY_WEIGHT) is set below angle and
spacing so a coincidental density match between structurally different
patterns can't dominate the combined score.

Since both values are already bounded to [0, 1], their absolute difference
is too -- no relative-error formula is needed here (unlike spacing, which
spans a much wider and less bounded range).
"""

from __future__ import annotations

from .models import ComponentScore


def density_similarity(reference_density: float, candidate_density: float) -> ComponentScore:
    difference = abs(reference_density - candidate_density)
    similarity = max(0.0, min(1.0, 1.0 - difference))
    return ComponentScore(available=True, score=similarity)
