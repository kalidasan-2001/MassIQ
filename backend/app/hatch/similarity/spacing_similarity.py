"""Normalized line-spacing similarity (R5 section 13).

R4 documented a real, measured ~15% residual normalized-spacing deviation
at the 2.0x scale extreme (see docs/testing/R4_HATCH_FEATURE_BENCHMARK.md
section 3) -- R4's scale invariance is good, not perfect. R5 must not
pretend otherwise: an exact-equality or extremely tight-threshold
comparison would incorrectly treat the *same* physical hatch pattern,
rendered at a different scale, as dissimilar.

Uses a smooth relative-difference formula rather than a hard cutoff:

    relative_error = abs(a - b) / max(a, b)
    similarity = 1 - relative_error

This is deliberately calibrated against R4's own measured evidence, not a
default guess: R4's worst documented same-pattern deviation (~15% at the
2.0x scale extreme) maps to a similarity of ~0.85 under this formula --
still a high, clearly-a-match score, while a genuinely different spacing
(e.g. a 2x or 3x difference in hatch density) maps to a similarity well
below that. See docs/testing/R5_PATTERN_LIBRARY_BENCHMARK.md for the
measured scores this formula produces across the R4 scale-variant fixtures.
"""

from __future__ import annotations

from .models import ComponentScore


def spacing_similarity(reference_spacing: float | None, candidate_spacing: float | None) -> ComponentScore:
    """Missing evidence (either side has no available normalized spacing
    -- R4's `spacing_available=False`, e.g. fewer than 2 detected line
    peaks) excludes this component -- never substituted with 0.0."""
    if reference_spacing is None or candidate_spacing is None:
        return ComponentScore(available=False)

    larger = max(reference_spacing, candidate_spacing)
    if larger <= 0:
        # Both exactly zero (degenerate, but not impossible for a
        # pathological crop) -- identical by definition, not a division
        # by zero.
        return ComponentScore(available=True, score=1.0)

    relative_error = abs(reference_spacing - candidate_spacing) / larger
    similarity = max(0.0, min(1.0, 1.0 - relative_error))
    return ComponentScore(available=True, score=similarity)
