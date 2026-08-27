"""Single-direction vs. cross-hatch classification, from angle evidence
alone (angles.py already does the actual line/angle detection -- this
module is just the documented, tested dominance decision, kept separate
per R4 section 15's request for a clear, isolated, testable rule).

Rule: a crop is classified as cross-hatch only if a secondary orientation
was found (angularly separated from the primary -- see angles.py) AND its
evidence is at least config.CROSS_HATCH_SECOND_PEAK_MIN_RATIO of the
primary orientation's evidence. A tiny noise peak in the histogram never
satisfies this ratio, so it never gets misclassified as a second hatch
direction.
"""

from __future__ import annotations

from .config import CROSS_HATCH_SECOND_PEAK_MIN_RATIO
from .models import AngleEvidence


def classify_cross_hatch(evidence: AngleEvidence) -> bool | None:
    """Returns True (cross-hatch), False (single direction), or None
    (undetermined -- no reliable primary angle at all)."""
    if evidence.primary_angle_deg is None:
        return None
    if evidence.secondary_angle_deg is None or evidence.primary_evidence_px <= 0:
        return False
    ratio = evidence.secondary_evidence_px / evidence.primary_evidence_px
    return ratio >= CROSS_HATCH_SECOND_PEAK_MIN_RATIO


def dominant_angles_list(evidence: AngleEvidence, is_cross_hatch: bool | None) -> list[float]:
    """The list of angles worth persisting: empty if undetermined, one
    entry for a single-direction hatch, two for a genuine cross-hatch --
    never forcing every crop to report two angles (R4 section 9)."""
    if evidence.primary_angle_deg is None:
        return []
    if is_cross_hatch and evidence.secondary_angle_deg is not None:
        return [evidence.primary_angle_deg, evidence.secondary_angle_deg]
    return [evidence.primary_angle_deg]
