from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.similarity.angle_similarity import angle_similarity


class AngleSimilarityTests(unittest.TestCase):
    def test_identical_single_angle_is_perfect(self):
        result = angle_similarity([45.0], [45.0])
        self.assertTrue(result.available)
        self.assertAlmostEqual(result.score, 1.0)

    def test_wraparound_179_vs_1_is_close(self):
        """The whole point of R4's circular distance: 179 and 1 are 2
        degrees apart, not 178 -- must score highly similar."""
        result = angle_similarity([179.0], [1.0])
        self.assertTrue(result.available)
        self.assertGreater(result.score, 0.95)

    def test_45_vs_135_are_not_automatically_equivalent(self):
        """45 and 135 are 90 degrees apart -- the maximum possible
        circular distance -- and must score as maximally dissimilar on
        their own (cross-hatch evidence, not angle_similarity itself, is
        what would make two DIFFERENT single directions from two
        DIFFERENT crops seem related; this component must not silently
        treat them as equivalent)."""
        result = angle_similarity([45.0], [135.0])
        self.assertTrue(result.available)
        self.assertAlmostEqual(result.score, 0.0, places=5)

    def test_missing_evidence_on_either_side_is_unavailable(self):
        self.assertFalse(angle_similarity([], [45.0]).available)
        self.assertFalse(angle_similarity([45.0], []).available)
        self.assertFalse(angle_similarity([], []).available)

    def test_two_angle_sets_use_best_pairing_not_positional(self):
        """[45, 135] vs [135, 45] (same two orientations, reversed order)
        must score as a perfect match -- proves matching is not blindly
        positional (index 0 to index 0)."""
        result = angle_similarity([45.0, 135.0], [135.0, 45.0])
        self.assertTrue(result.available)
        self.assertAlmostEqual(result.score, 1.0, places=5)

    def test_count_mismatch_matches_the_single_angle_to_its_closest_counterpart(self):
        """A single-direction pattern at 45 vs a cross-hatch pattern at
        [45, 135] should match the single 45 to its closest counterpart
        (45, distance 0) rather than being penalized for the count
        mismatch itself -- that penalty belongs to cross_hatch_similarity."""
        result = angle_similarity([45.0], [45.0, 135.0])
        self.assertTrue(result.available)
        self.assertAlmostEqual(result.score, 1.0, places=5)

    def test_score_is_bounded(self):
        for ref, cand in [([0.0], [90.0]), ([10.0, 170.0], [50.0, 130.0])]:
            result = angle_similarity(ref, cand)
            self.assertGreaterEqual(result.score, 0.0)
            self.assertLessEqual(result.score, 1.0)

    def test_symmetric(self):
        a = angle_similarity([30.0, 120.0], [45.0, 135.0])
        b = angle_similarity([45.0, 135.0], [30.0, 120.0])
        self.assertAlmostEqual(a.score, b.score)


if __name__ == "__main__":
    unittest.main()
