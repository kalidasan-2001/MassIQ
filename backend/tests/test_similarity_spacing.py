from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.similarity.spacing_similarity import spacing_similarity


class SpacingSimilarityTests(unittest.TestCase):
    def test_identical_spacing_is_perfect(self):
        result = spacing_similarity(0.035, 0.035)
        self.assertTrue(result.available)
        self.assertAlmostEqual(result.score, 1.0)

    def test_missing_on_either_side_is_unavailable(self):
        self.assertFalse(spacing_similarity(None, 0.035).available)
        self.assertFalse(spacing_similarity(0.035, None).available)
        self.assertFalse(spacing_similarity(None, None).available)

    def test_r4_documented_15_percent_scale_deviation_scores_highly_similar(self):
        """R4's own measured worst-case same-pattern deviation (~15% at
        2.0x scale, see docs/testing/R4_HATCH_FEATURE_BENCHMARK.md) must
        still be recognized as a strong match, not penalized as if it
        were a genuinely different pattern."""
        reference = 0.035355339059327376  # family A at 1.0x (measured)
        candidate = 0.030052038200428267  # family A at 2.0x (measured)
        result = spacing_similarity(reference, candidate)
        self.assertTrue(result.available)
        self.assertGreater(result.score, 0.8)

    def test_clearly_different_spacing_scores_low(self):
        # A ~3x spacing difference (e.g. family A vs a hypothetical much
        # wider hatch) should not be mistaken for a close match.
        result = spacing_similarity(0.035, 0.105)
        self.assertLess(result.score, 0.5)

    def test_both_zero_is_identical_not_a_crash(self):
        result = spacing_similarity(0.0, 0.0)
        self.assertTrue(result.available)
        self.assertAlmostEqual(result.score, 1.0)

    def test_score_is_bounded(self):
        for a, b in [(0.01, 0.5), (0.5, 0.01), (0.0, 0.2)]:
            result = spacing_similarity(a, b)
            self.assertGreaterEqual(result.score, 0.0)
            self.assertLessEqual(result.score, 1.0)

    def test_symmetric(self):
        a = spacing_similarity(0.04, 0.06)
        b = spacing_similarity(0.06, 0.04)
        self.assertAlmostEqual(a.score, b.score)


if __name__ == "__main__":
    unittest.main()
