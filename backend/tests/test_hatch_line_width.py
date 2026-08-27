from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.angles import detect_line_segments
from app.hatch.line_width import estimate_line_width_px, normalize_line_width
from app.hatch.preprocessing import preprocess
from tests import hatch_fixtures as hfx


class EstimateLineWidthPxTests(unittest.TestCase):
    def test_no_segments_returns_none(self):
        binary = np.zeros((50, 50), dtype=np.uint8)
        width, count = estimate_line_width_px(binary, np.empty((0, 4)))
        self.assertIsNone(width)
        self.assertEqual(count, 0)

    def test_recovers_a_plausible_width_for_a_real_hatch_pattern(self):
        image = hfx.family_a_parallel_45()
        pre = preprocess(image)
        segments = detect_line_segments(pre)
        width, count = estimate_line_width_px(pre.binary, segments)
        self.assertIsNotNone(width)
        self.assertGreaterEqual(count, 5)
        # Fixture lines are drawn 2px wide; some inflation from diagonal
        # rasterization/anti-aliasing thresholding is expected, but a wildly
        # implausible value (e.g. 20px) would indicate a real bug.
        self.assertGreater(width, 0)
        self.assertLess(width, 10)

    def test_never_fabricates_precision_below_minimum_sample_count(self):
        """Only one of the segment's interior sample points actually lands
        on foreground -- must return None rather than a value derived from
        too little evidence (R4 section 14), even though a segment was
        detected at all."""
        binary = np.zeros((50, 50), dtype=np.uint8)
        binary[25, 10] = 255  # a single lit pixel, far from most sample points
        segments = np.array([[0.0, 25.0, 20.0, 25.0]])  # samples land at x=4,7,10,13,16
        width, count = estimate_line_width_px(binary, segments)
        self.assertIsNone(width)
        self.assertLess(count, 5)


class NormalizeLineWidthTests(unittest.TestCase):
    def test_divides_by_diagonal(self):
        self.assertAlmostEqual(normalize_line_width(2.0, 100.0), 0.02)

    def test_zero_diagonal_returns_none(self):
        self.assertIsNone(normalize_line_width(2.0, 0.0))


if __name__ == "__main__":
    unittest.main()
