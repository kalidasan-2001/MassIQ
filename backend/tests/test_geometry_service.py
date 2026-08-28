"""R7 section 30/31 -- release-critical union/subtraction geometry tests.
Pure, no DB needed. Every expected value below is computed by hand in the
test itself (independent of app.geometry.service), not by calling the
function under test twice.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.geometry.service import NormalizedRect, compute_final_area_m2

# Non-square page on purpose -- a square page cannot catch an x/y axis
# mixup bug (both axes would silently produce the same wrong answer).
PAGE_W = 200.0  # points
PAGE_H = 100.0  # points
SCALE = 1.0  # real_meters_per_plan_point -- 1 point == 1 real meter here,
# chosen purely so hand-computed expected areas stay simple; the
# multiplication itself is exercised identically regardless of its value.


def area(rects_pos, rects_neg=()):
    return compute_final_area_m2(list(rects_pos), list(rects_neg), PAGE_W, PAGE_H, SCALE)


class GoldenGeometryTests(unittest.TestCase):
    def test_case_a_single_accepted_region_no_overlap(self):
        # width 0.1 * 200 = 20m, height 0.05 * 100 = 5m -> 100 m^2
        result = area([NormalizedRect(0, 0, 0.1, 0.05)])
        self.assertAlmostEqual(result, 100.0, places=6)

    def test_case_b_addition_no_overlap_sums(self):
        # Region A: 20m x 5m = 100 m^2 at x in [0, 0.1]
        # Addition: 10m x 5m = 50 m^2 at x in [0.1, 0.15] (adjacent, no overlap)
        result = area([NormalizedRect(0, 0, 0.1, 0.05), NormalizedRect(0.1, 0, 0.05, 0.05)])
        self.assertAlmostEqual(result, 150.0, places=6)

    def test_case_c_subtraction_fully_inside_positive(self):
        # Region A: 100 m^2. Subtract a 4m x 5m = 20 m^2 slice fully inside it.
        result = area([NormalizedRect(0, 0, 0.1, 0.05)], [NormalizedRect(0, 0, 0.02, 0.05)])
        self.assertAlmostEqual(result, 80.0, places=6)

    def test_case_d_overlapping_additions_not_double_counted(self):
        # A: x in [0, 0.1], 20m x 5m = 100 m^2.
        # Add: x in [0.05, 0.15], 20m x 5m = 100 m^2.
        # Overlap: x in [0.05, 0.1] -> 10m x 5m = 50 m^2.
        # Union = 100 + 100 - 50 = 150, NOT 200 (naive sum).
        result = area([NormalizedRect(0, 0, 0.1, 0.05), NormalizedRect(0.05, 0, 0.1, 0.05)])
        self.assertAlmostEqual(result, 150.0, places=6)
        naive_sum = 100.0 + 100.0
        self.assertNotAlmostEqual(result, naive_sum, places=6)

    def test_case_e_subtraction_extends_beyond_positive_region(self):
        # A: x in [0, 0.1], 100 m^2.
        # Subtract: x in [0.05, 0.55] (huge, mostly off the positive region).
        #   Overlap with A: x in [0.05, 0.1] -> 10m x 5m = 50 m^2 removed.
        # Only the intersecting part is removed -- final = 50 m^2, not
        # 100 - (huge subtraction area) and not negative.
        result = area([NormalizedRect(0, 0, 0.1, 0.05)], [NormalizedRect(0.05, 0, 0.5, 0.05)])
        self.assertAlmostEqual(result, 50.0, places=6)
        self.assertGreaterEqual(result, 0.0)

    def test_subtraction_entirely_covering_positive_yields_zero(self):
        result = area([NormalizedRect(0, 0, 0.1, 0.05)], [NormalizedRect(0, 0, 1.0, 1.0)])
        self.assertEqual(result, 0.0)

    def test_subtraction_disjoint_from_positive_leaves_area_unchanged(self):
        result = area([NormalizedRect(0, 0, 0.1, 0.05)], [NormalizedRect(0.5, 0.5, 0.1, 0.05)])
        self.assertAlmostEqual(result, 100.0, places=6)

    def test_overlapping_subtractions_not_double_subtracted(self):
        # Positive: whole page = 200 * 100 = 20000 m^2.
        # Subtract1: x[0,0.5] -> 100m x 100m = 10000 m^2.
        # Subtract2: x[0.25,0.75] -> 100m x 100m = 10000 m^2.
        # Overlap between subtracts: x[0.25,0.5] -> 50m x 100m = 5000 m^2.
        # Union of subtracts = 10000+10000-5000 = 15000.
        # Final = 20000 - 15000 = 5000 (NOT 20000 - 20000 = 0).
        result = area(
            [NormalizedRect(0, 0, 1.0, 1.0)],
            [NormalizedRect(0, 0, 0.5, 1.0), NormalizedRect(0.25, 0, 0.5, 1.0)],
        )
        self.assertAlmostEqual(result, 5000.0, places=6)

    def test_no_positive_geometry_is_zero(self):
        self.assertEqual(area([]), 0.0)
        self.assertEqual(area([], [NormalizedRect(0, 0, 0.5, 0.5)]), 0.0)

    def test_never_negative_never_nan_never_infinite(self):
        for result in (
            area([NormalizedRect(0, 0, 0.01, 0.01)], [NormalizedRect(0, 0, 1.0, 1.0)]),
            area([]),
            area([NormalizedRect(0, 0, 1.0, 1.0)], [NormalizedRect(0, 0, 1.0, 1.0)]),
        ):
            self.assertGreaterEqual(result, 0.0)
            self.assertEqual(result, result)  # NaN check: NaN != NaN
            self.assertNotEqual(result, float("inf"))

    def test_duplicate_identical_positive_rects_counted_once(self):
        rect = NormalizedRect(0, 0, 0.1, 0.05)
        result = area([rect, rect, rect])
        self.assertAlmostEqual(result, 100.0, places=6)


if __name__ == "__main__":
    unittest.main()
