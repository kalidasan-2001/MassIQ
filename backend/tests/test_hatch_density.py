from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.density import compute_density


class ComputeDensityTests(unittest.TestCase):
    def test_blank_image_has_zero_density(self):
        self.assertEqual(compute_density(np.zeros((50, 50), dtype=np.uint8)), 0.0)

    def test_fully_filled_image_has_density_one(self):
        self.assertEqual(compute_density(np.full((50, 50), 255, dtype=np.uint8)), 1.0)

    def test_half_filled_region_has_density_near_half(self):
        # Checkerboard: every row and every column (including the first and
        # last) has at least one foreground pixel, so the bounding box is
        # exactly the full 10x10 grid and exactly half of it is foreground.
        binary = np.zeros((10, 10), dtype=np.uint8)
        rows, cols = np.indices(binary.shape)
        binary[(rows + cols) % 2 == 0] = 255
        self.assertAlmostEqual(compute_density(binary), 0.5)

    def test_density_ignores_blank_margin_around_a_tight_pattern(self):
        """A large blank margin around a small, dense filled region must
        not dilute the reported density -- density is computed over the
        foreground's own bounding box, not the whole crop."""
        binary = np.zeros((100, 100), dtype=np.uint8)
        binary[40:50, 40:50] = 255  # fully filled 10x10 region, tightly bounded
        self.assertAlmostEqual(compute_density(binary), 1.0)

    def test_result_is_bounded_zero_to_one(self):
        rng = np.random.default_rng(0)
        binary = (rng.random((60, 60)) > 0.5).astype(np.uint8) * 255
        density = compute_density(binary)
        self.assertGreaterEqual(density, 0.0)
        self.assertLessEqual(density, 1.0)


if __name__ == "__main__":
    unittest.main()
