from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.preprocessing import InvalidHatchImageError, preprocess, validate_image
from tests import hatch_fixtures as hfx


class ValidateImageTests(unittest.TestCase):
    def test_none_raises(self):
        with self.assertRaises(InvalidHatchImageError):
            validate_image(None)

    def test_empty_array_raises(self):
        with self.assertRaises(InvalidHatchImageError):
            validate_image(np.empty((0, 0, 3), dtype=np.uint8))

    def test_too_small_raises(self):
        with self.assertRaises(InvalidHatchImageError):
            validate_image(np.zeros((4, 4, 3), dtype=np.uint8))

    def test_1d_array_raises(self):
        with self.assertRaises(InvalidHatchImageError):
            validate_image(np.zeros(10, dtype=np.uint8))

    def test_valid_minimum_size_passes(self):
        validate_image(np.zeros((8, 8, 3), dtype=np.uint8))  # must not raise


class PreprocessTests(unittest.TestCase):
    def test_produces_expected_shapes_and_dtypes(self):
        image = hfx.family_a_parallel_45()
        pre = preprocess(image)
        self.assertEqual(pre.width, image.shape[1])
        self.assertEqual(pre.height, image.shape[0])
        self.assertEqual(pre.gray.shape, (pre.height, pre.width))
        self.assertEqual(pre.binary.shape, (pre.height, pre.width))
        self.assertEqual(pre.edges.shape, (pre.height, pre.width))
        self.assertEqual(pre.original_bgr.shape, (pre.height, pre.width, 3))

    def test_binary_image_is_two_valued(self):
        pre = preprocess(hfx.family_d_cross_hatch_45_135())
        unique_values = set(np.unique(pre.binary).tolist())
        self.assertTrue(unique_values.issubset({0, 255}))

    def test_diagonal_matches_pythagorean_length(self):
        pre = preprocess(hfx.family_a_parallel_45(size=100))
        self.assertAlmostEqual(pre.diagonal_px, float(np.hypot(100, 100)))

    def test_accepts_grayscale_input(self):
        gray = np.zeros((50, 50), dtype=np.uint8)
        gray[:, ::5] = 255
        pre = preprocess(gray)
        self.assertEqual(pre.original_bgr.shape, (50, 50, 3))

    def test_all_white_image_does_not_raise_and_has_no_foreground(self):
        blank = np.full((60, 60, 3), 255, dtype=np.uint8)
        pre = preprocess(blank)
        # A uniform image has no real bimodal structure for Otsu to split
        # meaningfully -- must not crash, whatever it decides.
        self.assertEqual(pre.binary.shape, (60, 60))

    def test_all_black_image_does_not_raise(self):
        black = np.zeros((60, 60, 3), dtype=np.uint8)
        preprocess(black)  # must not raise


if __name__ == "__main__":
    unittest.main()
