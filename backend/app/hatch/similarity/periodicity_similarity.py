"""Periodicity similarity (R5 section 16).

R4's `periodicity` is a bounded, nullable [0.0, 1.0] autocorrelation score
(see hatch/periodicity.py); `periodicity_available=False` when the
projection signal was too short/degenerate to estimate at all -- that
case excludes this component entirely, never substituting a fabricated
0.0.

This is deliberately weighted as important supporting evidence (see
config.py's PERIODICITY_WEIGHT, medium-high): R4's own benchmark found
that the synthetic "irregular lines" control can, purely by chance,
produce angle/cross-hatch evidence that superficially resembles a real
hatch (see docs/testing/R4_HATCH_FEATURE_BENCHMARK.md's documented
limitation) -- but its periodicity stays low (~0.29 measured) while every
genuine hatch family measured 0.84-0.97. A bounded absolute-difference
comparison, like density's, correctly and automatically penalizes exactly
this case: a regular hatch (periodicity ~0.9) compared against an
irregular control (periodicity ~0.29) differs by ~0.6, mapping to a
similarity around 0.4 -- a real, meaningful similarity loss, tested
explicitly in test_periodicity_similarity.py.
"""

from __future__ import annotations

from .models import ComponentScore


def periodicity_similarity(reference_periodicity: float | None, candidate_periodicity: float | None) -> ComponentScore:
    if reference_periodicity is None or candidate_periodicity is None:
        return ComponentScore(available=False)

    difference = abs(reference_periodicity - candidate_periodicity)
    similarity = max(0.0, min(1.0, 1.0 - difference))
    return ComponentScore(available=True, score=similarity)
