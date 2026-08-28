"""Dominant-angle similarity (R5 section 12).

Reuses `hatch.normalization.circular_angle_distance` directly -- angle
comparison logic is never duplicated outside that one function, so the
179-vs-1-degree wraparound behaves identically everywhere in the codebase.

Multi-angle matching: a HatchFeatureSet stores 0, 1, or 2 dominant angles
(see hatch/cross_hatch.py). Comparing them positionally (index 0 to index
0, index 1 to index 1) would be wrong whenever the two patterns' angles
happen to be reported in a different order -- there is no guaranteed
canonical ordering beyond "primary is the strongest peak," and a
reference's primary orientation is not guaranteed to correspond to a
candidate's primary orientation just because both are cross-hatch. This
module instead finds the best (lowest-total-distance) pairing between the
two angle sets, trying every reasonable assignment rather than assuming
one.

Cross-hatch orientation *count* mismatches (one side single-direction, the
other genuinely cross-hatch) are deliberately NOT penalized here -- that
is cross_hatch_similarity's job (see R5 section 15). This module only
answers "how close are the orientations that ARE present," using the best
available matching.
"""

from __future__ import annotations

from itertools import permutations

from ..normalization import circular_angle_distance
from .config import ANGLE_MAX_CIRCULAR_DISTANCE_DEG
from .models import ComponentScore


def _distance_to_similarity(distance_deg: float) -> float:
    similarity = 1.0 - (distance_deg / ANGLE_MAX_CIRCULAR_DISTANCE_DEG)
    return max(0.0, min(1.0, similarity))


def _best_average_distance(reference: list[float], candidate: list[float]) -> float:
    """Finds the pairing between the shorter and longer angle list that
    minimizes total circular distance, then averages over the shorter
    list's length -- i.e. "how well does every angle we have evidence for
    on the smaller side find a good match on the other side."""
    if len(reference) <= len(candidate):
        smaller, larger = reference, candidate
    else:
        smaller, larger = candidate, reference

    best_total = None
    # len(larger) is 1 or 2 in practice (R4 never reports more than 2
    # dominant angles), so trying every assignment of `smaller` onto a
    # subset of `larger`'s positions is trivially cheap -- no need for a
    # general Hungarian-algorithm dependency for at most 2 items.
    for larger_subset in permutations(larger, len(smaller)):
        total = sum(circular_angle_distance(a, b) for a, b in zip(smaller, larger_subset))
        if best_total is None or total < best_total:
            best_total = total
    return best_total / len(smaller)


def angle_similarity(reference_angles: list[float], candidate_angles: list[float]) -> ComponentScore:
    """Missing evidence (either side reports zero dominant angles -- i.e.
    R4 found no reliable line structure at all) excludes this component
    entirely, rather than scoring it as a fabricated 0.0 "total
    mismatch" -- see R4's own "missing vs. negative evidence" distinction,
    which R5 must respect identically."""
    if not reference_angles or not candidate_angles:
        return ComponentScore(available=False)

    avg_distance = _best_average_distance(reference_angles, candidate_angles)
    return ComponentScore(available=True, score=_distance_to_similarity(avg_distance))
