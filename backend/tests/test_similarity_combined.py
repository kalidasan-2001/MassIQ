from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.similarity.combined_similarity import FEATURE_VERSION_MISMATCH_REASON, compare
from app.hatch.similarity.models import ComparableFeatures


def _features(**overrides) -> ComparableFeatures:
    defaults = dict(
        feature_version="1.0",
        dominant_angles=[45.0],
        is_cross_hatch=False,
        normalized_line_spacing=0.035,
        line_density=0.3,
        normalized_line_width=0.02,
        periodicity=0.9,
        color_mean_l=200.0,
        color_mean_a=128.0,
        color_mean_b=128.0,
    )
    defaults.update(overrides)
    return ComparableFeatures(**defaults)


class FeatureVersionCompatibilityTests(unittest.TestCase):
    def test_matching_versions_are_comparable(self):
        result = compare(_features(feature_version="1.0"), _features(feature_version="1.0"))
        self.assertTrue(result.comparable)
        self.assertIsNotNone(result.overall_similarity)

    def test_mismatched_versions_are_explicitly_not_comparable(self):
        result = compare(_features(feature_version="1.0"), _features(feature_version="2.0"))
        self.assertFalse(result.comparable)
        self.assertEqual(result.reason, FEATURE_VERSION_MISMATCH_REASON)
        self.assertIsNone(result.overall_similarity)
        self.assertEqual(result.components, {})


class IdenticalAndDeterminismTests(unittest.TestCase):
    def test_identical_features_score_near_perfect(self):
        features = _features()
        result = compare(features, features)
        self.assertTrue(result.comparable)
        self.assertGreater(result.overall_similarity, 0.99)

    def test_deterministic_repeated_calls(self):
        reference = _features()
        candidate = _features(normalized_line_spacing=0.04, line_density=0.35)
        first = compare(reference, candidate)
        second = compare(reference, candidate)
        self.assertEqual(first, second)

    def test_symmetric_overall_score(self):
        a = _features(dominant_angles=[45.0], normalized_line_spacing=0.03)
        b = _features(dominant_angles=[50.0], normalized_line_spacing=0.05)
        forward = compare(a, b)
        backward = compare(b, a)
        self.assertAlmostEqual(forward.overall_similarity, backward.overall_similarity)


class MissingEvidenceTests(unittest.TestCase):
    def test_missing_spacing_excludes_it_and_renormalizes_over_the_rest(self):
        reference = _features(normalized_line_spacing=None)
        candidate = _features(normalized_line_spacing=0.035)
        result = compare(reference, candidate)
        self.assertTrue(result.comparable)
        self.assertFalse(result.components["spacing"].available)
        # Every other component matched exactly -- overall should still
        # be near-perfect despite the missing spacing evidence, proving
        # the denominator was renormalized rather than penalizing the gap
        # as if it were a real mismatch.
        self.assertGreater(result.overall_similarity, 0.99)

    def test_missing_line_width_and_periodicity_still_produces_a_valid_score(self):
        reference = _features(normalized_line_width=None, periodicity=None)
        candidate = _features(normalized_line_width=None, periodicity=None)
        result = compare(reference, candidate)
        self.assertTrue(result.comparable)
        self.assertFalse(result.components["line_width"].available)
        self.assertFalse(result.components["periodicity"].available)
        self.assertGreater(result.overall_similarity, 0.99)

    def test_cross_hatch_undetermined_on_both_sides_excludes_it(self):
        reference = _features(is_cross_hatch=None, dominant_angles=[])
        candidate = _features(is_cross_hatch=None, dominant_angles=[])
        result = compare(reference, candidate)
        self.assertTrue(result.comparable)
        self.assertFalse(result.components["cross_hatch"].available)
        self.assertFalse(result.components["angle"].available)
        # density and color are always available -- a valid score must
        # still come out even with both angle and cross_hatch missing.
        self.assertIsNotNone(result.overall_similarity)


class CrossHatchCannotZeroTheTotalTests(unittest.TestCase):
    def test_single_disagreeing_boolean_does_not_force_overall_to_zero(self):
        """R5 section 15's explicit requirement: a cross-hatch mismatch
        must be meaningful but must not, by itself, be capable of forcing
        the whole similarity to zero when everything else matches."""
        reference = _features(is_cross_hatch=False)
        candidate = _features(is_cross_hatch=True)
        result = compare(reference, candidate)
        self.assertTrue(result.comparable)
        self.assertAlmostEqual(result.components["cross_hatch"].score, 0.0)
        # Everything else is identical -- the overall score must reflect
        # a real but partial penalty, not a wipeout.
        self.assertGreater(result.overall_similarity, 0.85)


class EvidenceCoverageTests(unittest.TestCase):
    """Quality metadata, not confidence -- see similarity/models.py's
    SimilarityResult.evidence_coverage docstring and the R5 negative-
    control finding it exists to surface."""

    def test_full_evidence_comparison_has_coverage_one(self):
        result = compare(_features(), _features())
        self.assertAlmostEqual(result.evidence_coverage, 1.0)

    def test_missing_components_reduce_coverage_below_one(self):
        reference = _features(normalized_line_spacing=None, periodicity=None)
        candidate = _features(normalized_line_spacing=None, periodicity=None)
        result = compare(reference, candidate)
        self.assertLess(result.evidence_coverage, 1.0)

    def test_only_density_and_color_available_yields_low_coverage(self):
        """The exact degenerate case the R5 ranking benchmark's negative
        control surfaced: no angle, spacing, periodicity, or cross-hatch
        evidence on either side leaves only density+color, a small
        fraction of the full weight budget."""
        reference = _features(
            dominant_angles=[], is_cross_hatch=None, normalized_line_spacing=None,
            normalized_line_width=None, periodicity=None,
        )
        candidate = _features(
            dominant_angles=[], is_cross_hatch=None, normalized_line_spacing=None,
            normalized_line_width=None, periodicity=None,
        )
        result = compare(reference, candidate)
        self.assertLess(result.evidence_coverage, 0.3)


class ScoreInvariantTests(unittest.TestCase):
    """R5 section 43 -- mandatory."""

    def test_bounded_across_a_range_of_inputs(self):
        cases = [
            (_features(), _features()),
            (_features(dominant_angles=[0.0]), _features(dominant_angles=[90.0])),
            (_features(line_density=0.0), _features(line_density=1.0)),
            (_features(periodicity=0.0), _features(periodicity=1.0)),
            (_features(is_cross_hatch=True), _features(is_cross_hatch=False)),
            (_features(color_mean_l=0.0, color_mean_a=0.0, color_mean_b=0.0), _features(color_mean_l=255.0, color_mean_a=255.0, color_mean_b=255.0)),
        ]
        for reference, candidate in cases:
            result = compare(reference, candidate)
            self.assertTrue(result.comparable)
            self.assertGreaterEqual(result.overall_similarity, 0.0)
            self.assertLessEqual(result.overall_similarity, 1.0)
            self.assertFalse(math.isnan(result.overall_similarity))
            self.assertFalse(math.isinf(result.overall_similarity))
            for component in result.components.values():
                if component.available:
                    self.assertGreaterEqual(component.score, 0.0)
                    self.assertLessEqual(component.score, 1.0)
                    self.assertFalse(math.isnan(component.score))


if __name__ == "__main__":
    unittest.main()
