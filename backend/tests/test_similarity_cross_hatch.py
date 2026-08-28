from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.similarity.cross_hatch_similarity import cross_hatch_similarity


class CrossHatchSimilarityTests(unittest.TestCase):
    def test_both_single_direction_agrees(self):
        result = cross_hatch_similarity(False, False)
        self.assertTrue(result.available)
        self.assertAlmostEqual(result.score, 1.0)

    def test_both_cross_hatch_agrees(self):
        result = cross_hatch_similarity(True, True)
        self.assertTrue(result.available)
        self.assertAlmostEqual(result.score, 1.0)

    def test_disagreement_is_a_real_penalty(self):
        result = cross_hatch_similarity(False, True)
        self.assertTrue(result.available)
        self.assertAlmostEqual(result.score, 0.0)

    def test_either_side_undetermined_is_unavailable(self):
        self.assertFalse(cross_hatch_similarity(None, True).available)
        self.assertFalse(cross_hatch_similarity(True, None).available)
        self.assertFalse(cross_hatch_similarity(None, None).available)


if __name__ == "__main__":
    unittest.main()
