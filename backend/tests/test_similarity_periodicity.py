from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.similarity.periodicity_similarity import periodicity_similarity


class PeriodicitySimilarityTests(unittest.TestCase):
    def test_identical_periodicity_is_perfect(self):
        result = periodicity_similarity(0.9, 0.9)
        self.assertTrue(result.available)
        self.assertAlmostEqual(result.score, 1.0)

    def test_missing_on_either_side_is_unavailable(self):
        self.assertFalse(periodicity_similarity(None, 0.9).available)
        self.assertFalse(periodicity_similarity(0.9, None).available)

    def test_regular_hatch_vs_irregular_control_loses_similarity(self):
        """R5 section 16's mandatory test: a regular hatch's measured
        periodicity (~0.84-0.97 per the R4 benchmark) against the
        irregular-line control's measured periodicity (~0.29) must score
        a real, meaningful similarity loss -- this is precisely the
        signal that should catch a structural false-positive from other
        components (see R4's documented irregular-line limitation)."""
        result = periodicity_similarity(0.9, 0.29)
        self.assertTrue(result.available)
        self.assertLess(result.score, 0.5)

    def test_score_is_bounded(self):
        for a, b in [(0.0, 1.0), (1.0, 0.0), (0.5, 0.5)]:
            result = periodicity_similarity(a, b)
            self.assertGreaterEqual(result.score, 0.0)
            self.assertLessEqual(result.score, 1.0)


if __name__ == "__main__":
    unittest.main()
