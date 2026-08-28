from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.similarity.color_similarity import color_similarity


class ColorSimilarityTests(unittest.TestCase):
    def test_identical_color_is_perfect(self):
        result = color_similarity((200.0, 128.0, 128.0), (200.0, 128.0, 128.0))
        self.assertAlmostEqual(result.score, 1.0)

    def test_always_available(self):
        # color_mean_l/a/b are never None -- no missing-evidence branch.
        result = color_similarity((0.0, 0.0, 0.0), (255.0, 255.0, 255.0))
        self.assertTrue(result.available)

    def test_same_pattern_brightness_variation_scores_highly_similar(self):
        """Realistic R4-measured same-pattern variation (brightness/blur/
        noise perturbations measured 0.5-8.5 LAB units apart -- see
        similarity/config.py's calibration note) must not be treated as a
        meaningfully different color."""
        result = color_similarity((204.83, 128.0, 128.0), (213.34, 128.0, 128.0))
        self.assertGreater(result.score, 0.9)

    def test_score_is_bounded_even_for_extreme_distance(self):
        result = color_similarity((0.0, 0.0, 0.0), (255.0, 255.0, 255.0))
        self.assertGreaterEqual(result.score, 0.0)
        self.assertLessEqual(result.score, 1.0)


if __name__ == "__main__":
    unittest.main()
