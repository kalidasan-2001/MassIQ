from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.color import compute_color_features


class ComputeColorFeaturesTests(unittest.TestCase):
    def test_pure_white_has_max_lightness_and_zero_chroma_std(self):
        white = np.full((20, 20, 3), 255, dtype=np.uint8)
        features = compute_color_features(white)
        self.assertGreater(features.mean_l, 250)
        self.assertEqual(features.std_l, 0.0)
        self.assertEqual(features.std_a, 0.0)
        self.assertEqual(features.std_b, 0.0)

    def test_pure_black_has_min_lightness(self):
        black = np.zeros((20, 20, 3), dtype=np.uint8)
        features = compute_color_features(black)
        self.assertLess(features.mean_l, 5)

    def test_uses_lab_not_raw_bgr_a_red_fill_shows_up_in_a_channel(self):
        # BGR red = (0, 0, 255). LAB's 'a' channel (green-red) should shift
        # noticeably positive/high relative to a neutral gray of similar
        # brightness -- this is the actual point of using LAB over BGR.
        red = np.zeros((20, 20, 3), dtype=np.uint8)
        red[:, :, 2] = 200  # BGR red channel
        features = compute_color_features(red)
        gray = np.full((20, 20, 3), 100, dtype=np.uint8)
        gray_features = compute_color_features(gray)
        self.assertGreater(features.mean_a, gray_features.mean_a)

    def test_mixed_colors_produce_nonzero_std(self):
        half_white_half_black = np.zeros((20, 20, 3), dtype=np.uint8)
        half_white_half_black[:, :10] = 255
        features = compute_color_features(half_white_half_black)
        self.assertGreater(features.std_l, 0.0)


if __name__ == "__main__":
    unittest.main()
