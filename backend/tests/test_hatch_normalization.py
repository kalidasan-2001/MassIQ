from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.normalization import circular_angle_distance, normalize_angle


class NormalizeAngleTests(unittest.TestCase):
    def test_wraps_into_period(self):
        self.assertAlmostEqual(normalize_angle(190, period=180), 10)
        self.assertAlmostEqual(normalize_angle(-10, period=180), 170)
        self.assertAlmostEqual(normalize_angle(45, period=180), 45)

    def test_zero_and_period_boundary(self):
        self.assertAlmostEqual(normalize_angle(0, period=180), 0)
        self.assertAlmostEqual(normalize_angle(180, period=180), 0)


class CircularAngleDistanceTests(unittest.TestCase):
    def test_wraparound_is_shorter_than_naive_subtraction(self):
        # The whole point of R4's wraparound requirement: 179 and 1 are
        # close (2 degrees apart through 0/180), not 178 apart.
        self.assertAlmostEqual(circular_angle_distance(179, 1), 2)

    def test_identical_angles_are_zero_apart(self):
        self.assertAlmostEqual(circular_angle_distance(45, 45), 0)

    def test_orthogonal_angles_are_maximally_apart(self):
        self.assertAlmostEqual(circular_angle_distance(0, 90), 90)

    def test_symmetric(self):
        self.assertAlmostEqual(circular_angle_distance(10, 170), circular_angle_distance(170, 10))

    def test_handles_values_outside_the_base_period(self):
        self.assertAlmostEqual(circular_angle_distance(359, 1, period=180), circular_angle_distance(179, 1))


if __name__ == "__main__":
    unittest.main()
