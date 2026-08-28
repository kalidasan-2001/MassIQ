from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.similarity.density_similarity import density_similarity


class DensitySimilarityTests(unittest.TestCase):
    def test_identical_density_is_perfect(self):
        result = density_similarity(0.3, 0.3)
        self.assertTrue(result.available)
        self.assertAlmostEqual(result.score, 1.0)

    def test_always_available_never_nullable(self):
        # R4's line_density is never None -- density_similarity has no
        # missing-evidence branch at all, unlike the nullable features.
        result = density_similarity(0.0, 1.0)
        self.assertTrue(result.available)

    def test_maximally_different_density_scores_zero(self):
        result = density_similarity(0.0, 1.0)
        self.assertAlmostEqual(result.score, 0.0)

    def test_score_is_bounded(self):
        for a, b in [(0.1, 0.9), (0.5, 0.5), (0.0, 0.0)]:
            result = density_similarity(a, b)
            self.assertGreaterEqual(result.score, 0.0)
            self.assertLessEqual(result.score, 1.0)


if __name__ == "__main__":
    unittest.main()
