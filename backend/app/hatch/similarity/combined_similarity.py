"""Combined, explainable similarity score (R5 sections 19-20).

Orchestrates every component module into one deterministic
`compare(reference, candidate) -> SimilarityResult` call -- deliberately a
thin orchestrator (mirrors `HatchFeatureExtractor.extract`'s own role in
R4): every actual formula lives in its own small module, this file only
wires them together and does the weighted combination.

Architecture note (why a weighted AVERAGE, never a product/AND-gate):
combining components multiplicatively (overall = a * b * c * ...) would
let ANY single component at 0.0 force the entire result to 0.0, which R5
explicitly forbids for cross-hatch disagreement (section 15) and which
would also be wrong for any other single low-evidence component. A
weighted average, renormalized over only the components that were
actually available, guarantees that a single component's score can only
move the overall result by that component's own weight share -- never
zero it out on its own, and never let a missing feature silently count as
a zero either (see each component module's own missing-evidence handling).

Feature-version compatibility (R5 section 11) is checked FIRST, before any
component is computed: comparing HatchFeatureSets computed under
different algorithm versions would silently mix incompatible feature
semantics (a v1.0 normalized_line_spacing and a hypothetical v2.0 one are
not guaranteed to mean the same thing). R5 does not attempt to bridge
this -- an explicit `comparable=False` result is returned instead of a
number that would look meaningful but isn't.
"""

from __future__ import annotations

from .angle_similarity import angle_similarity
from .color_similarity import color_similarity
from .config import (
    ANGLE_WEIGHT,
    COLOR_WEIGHT,
    CROSS_HATCH_WEIGHT,
    DENSITY_WEIGHT,
    LINE_WIDTH_WEIGHT,
    PERIODICITY_WEIGHT,
    SPACING_WEIGHT,
)
from .cross_hatch_similarity import cross_hatch_similarity
from .density_similarity import density_similarity
from .line_width_similarity import line_width_similarity
from .models import ComparableFeatures, ComponentScore, SimilarityResult
from .periodicity_similarity import periodicity_similarity
from .spacing_similarity import spacing_similarity

_WEIGHTS: dict[str, float] = {
    "angle": ANGLE_WEIGHT,
    "spacing": SPACING_WEIGHT,
    "periodicity": PERIODICITY_WEIGHT,
    "density": DENSITY_WEIGHT,
    "cross_hatch": CROSS_HATCH_WEIGHT,
    "line_width": LINE_WIDTH_WEIGHT,
    "color": COLOR_WEIGHT,
}

FEATURE_VERSION_MISMATCH_REASON = "feature_version_mismatch"


def compare(reference: ComparableFeatures, candidate: ComparableFeatures) -> SimilarityResult:
    """Deterministic and pure -- same two inputs always produce the same
    SimilarityResult, and this function never touches the database or any
    external state."""
    if reference.feature_version != candidate.feature_version:
        return SimilarityResult(comparable=False, reason=FEATURE_VERSION_MISMATCH_REASON)

    components: dict[str, ComponentScore] = {
        "angle": angle_similarity(reference.dominant_angles, candidate.dominant_angles),
        "spacing": spacing_similarity(reference.normalized_line_spacing, candidate.normalized_line_spacing),
        "periodicity": periodicity_similarity(reference.periodicity, candidate.periodicity),
        "density": density_similarity(reference.line_density, candidate.line_density),
        "cross_hatch": cross_hatch_similarity(reference.is_cross_hatch, candidate.is_cross_hatch),
        "line_width": line_width_similarity(reference.normalized_line_width, candidate.normalized_line_width),
        "color": color_similarity(
            (reference.color_mean_l, reference.color_mean_a, reference.color_mean_b),
            (candidate.color_mean_l, candidate.color_mean_a, candidate.color_mean_b),
        ),
    }

    available_weight = sum(_WEIGHTS[name] for name, comp in components.items() if comp.available)
    if available_weight <= 0:
        # Degenerate in practice (density and color are always available,
        # so this can only happen if their weights were both set to 0) --
        # handled explicitly rather than dividing by zero.
        return SimilarityResult(comparable=True, overall_similarity=0.0, components=components, evidence_coverage=0.0)

    weighted_sum = sum(
        _WEIGHTS[name] * comp.score for name, comp in components.items() if comp.available
    )
    overall = weighted_sum / available_weight
    overall = max(0.0, min(1.0, overall))

    return SimilarityResult(
        comparable=True, overall_similarity=overall, components=components, evidence_coverage=available_weight
    )
