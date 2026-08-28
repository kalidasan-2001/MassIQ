"""Cross-hatch agreement (R5 section 15).

R4's `is_cross_hatch` is a nullable bool: `None` means undetermined (no
reliable primary angle at all -- see hatch/cross_hatch.py), which is a
missing-evidence state, not "not cross-hatch." Either side being `None`
excludes this component entirely.

When both sides have a determined value, agreement is scored as a clean,
maximally explainable binary: full agreement (both single-direction, or
both cross-hatch) scores 1.0; disagreement scores 0.0
(config.CROSS_HATCH_DISAGREEMENT_SCORE) -- a real, meaningful penalty, not
a token deduction.

R5's own instruction is explicit that a single boolean field must not be
able to force the *overall* similarity to zero. That protection is
deliberately NOT implemented by softening this component's score (which
would make disagreement less meaningful, the opposite of R5 section 15's
intent) -- it comes from combined_similarity.py's weighted-average
architecture: CROSS_HATCH_WEIGHT is well below 1.0, so a 0.0 score here
can only pull the renormalized overall score down by its own weight
share, never to zero, as long as other components carry evidence. See
combined_similarity.py's own docstring and
docs/architecture/PATTERN_LIBRARY.md.
"""

from __future__ import annotations

from .config import CROSS_HATCH_AGREEMENT_SCORE, CROSS_HATCH_DISAGREEMENT_SCORE
from .models import ComponentScore


def cross_hatch_similarity(reference_is_cross_hatch: bool | None, candidate_is_cross_hatch: bool | None) -> ComponentScore:
    if reference_is_cross_hatch is None or candidate_is_cross_hatch is None:
        return ComponentScore(available=False)

    agrees = reference_is_cross_hatch == candidate_is_cross_hatch
    score = CROSS_HATCH_AGREEMENT_SCORE if agrees else CROSS_HATCH_DISAGREEMENT_SCORE
    return ComponentScore(available=True, score=score)
