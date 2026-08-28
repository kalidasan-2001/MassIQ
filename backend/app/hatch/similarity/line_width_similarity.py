"""Normalized line-width similarity (R5 section 18).

R4's `normalized_line_width` is nullable and evidence-gated (None unless
`MIN_LINE_WIDTH_SAMPLES` independent measurements succeeded -- see
hatch/line_width.py). R5's rule is explicit: if either side is missing,
EXCLUDE this component from the comparison entirely. Do not substitute
zero -- a missing measurement is not evidence of "line width totally
different," it is simply "no reliable measurement was possible."

Uses the same relative-difference formula as spacing_similarity (both are
normalized-by-diagonal spatial measurements with a comparable, tuned to
comparable scale-sensitivity), documented once there rather than
re-deriving a different formula here for no reason.
"""

from __future__ import annotations

from .models import ComponentScore


def line_width_similarity(reference_width: float | None, candidate_width: float | None) -> ComponentScore:
    if reference_width is None or candidate_width is None:
        return ComponentScore(available=False)

    larger = max(reference_width, candidate_width)
    if larger <= 0:
        return ComponentScore(available=True, score=1.0)

    relative_error = abs(reference_width - candidate_width) / larger
    similarity = max(0.0, min(1.0, 1.0 - relative_error))
    return ComponentScore(available=True, score=similarity)
