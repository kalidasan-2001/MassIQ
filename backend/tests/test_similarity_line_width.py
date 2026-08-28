from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.similarity.line_width_similarity import line_width_similarity


class LineWidthSimilarityTests(unittest.TestCase):
    def test_identical_width_is_perfect(self):
        result = line_width_similarity(0.02, 0.02)
        self.assertTrue(result.available)
        self.assertAlmostEqual(result.score, 1.0)

    def test_missing_on_either_side_excludes_never_substitutes_zero(self):
        # The literal R5 section 18 requirement.
        self.assertFalse(line_width_similarity(None, 0.02).available)
        self.assertFalse(line_width_similarity(0.02, None).available)
        self.assertFalse(line_width_similarity(None, None).available)

    def test_score_is_bounded(self):
        for a, b in [(0.01, 0.05), (0.05, 0.01)]:
            result = line_width_similarity(a, b)
            self.assertGreaterEqual(result.score, 0.0)
            self.assertLessEqual(result.score, 1.0)


if __name__ == "__main__":
    unittest.main()
