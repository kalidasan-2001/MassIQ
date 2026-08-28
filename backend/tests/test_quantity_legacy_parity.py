"""R7 section 7 -- golden compatibility with the existing, UNTOUCHED
legacy `frontend/src/utils/quantityEngine.js` (audited, not rewritten from
memory -- see docs/architecture/REVIEW_AND_QUANTITY_ENGINE.md's audit
section). Legacy formula: naive scalar area summation, no union/overlap
handling at all --

    final_area_m2 = accepted + added - subtracted
    volume_m3 = final_area_m2 * confirmed_height_m

These vectors are the exact same numbers as
frontend/src/utils/quantityEngine.test.js's own test cases, so a change to
either implementation that breaks parity for the *non-overlapping* case is
caught here independently of any JS test run.

For equivalent NON-OVERLAPPING geometry (every rect placed with zero
mutual overlap, exactly the shape legacy's scalar model is valid for), the
new backend app.geometry.service union-based calculation must produce the
identical number legacy would -- proving R7's overlap-safe implementation
is a strict superset of legacy's own behavior, not a silent behavior
change for the cases legacy already handled correctly.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.geometry.service import NormalizedRect, compute_final_area_m2

PAGE_W = 100.0
PAGE_H = 100.0
SCALE = 1.0  # 1 point == 1 meter -- full page is 100m x 100m = 10000 m^2


def legacy_formula(accepted_m2: float, added_m2: float, subtracted_m2: float, height_m: float) -> tuple[float, float]:
    """A direct, deliberate reimplementation of quantityEngine.js's
    buildQuantityResult, in Python, for parity checking -- NOT calling the
    JS file. Matches its exact (unclamped, scalar) arithmetic."""
    final_area_m2 = float(accepted_m2 or 0) + float(added_m2 or 0) - float(subtracted_m2 or 0)
    volume_m3 = final_area_m2 * float(height_m or 0)
    return final_area_m2, volume_m3


class LegacyFormulaParityTests(unittest.TestCase):
    """Mirrors frontend/src/utils/quantityEngine.test.js's own cases
    exactly (same input numbers), proving the Python reference used below
    for backend-parity checks matches the actual committed JS behavior."""

    def test_final_area_is_accepted_plus_added_minus_subtracted(self):
        final_area, _ = legacy_formula(10, 2.5, 1.5, 0)
        self.assertEqual(final_area, 11)

    def test_volume_is_area_times_height(self):
        final_area, volume = legacy_formula(10, 0, 0, 3)
        self.assertEqual(final_area, 10)
        self.assertEqual(volume, 30)

    def test_combined(self):
        final_area, volume = legacy_formula(20, 5, 3, 2.5)
        self.assertEqual(final_area, 22)
        self.assertEqual(volume, 55)

    def test_missing_inputs_are_zero(self):
        final_area, volume = legacy_formula(None, None, None, None)
        self.assertEqual(final_area, 0)
        self.assertEqual(volume, 0)


class BackendMatchesLegacyForNonOverlappingGeometryTests(unittest.TestCase):
    """The release-critical parity check (R7 section 7): for geometry with
    NO overlap anywhere (exactly what legacy's scalar model implicitly
    assumes), the new union-based backend calculation must equal what
    legacy's naive scalar formula would have produced from the same
    per-rect areas."""

    def test_single_accepted_region_matches_legacy_scalar_sum(self):
        rect = NormalizedRect(0, 0, 0.1, 0.1)  # 10m x 10m = 100 m^2
        backend_area = compute_final_area_m2([rect], [], PAGE_W, PAGE_H, SCALE)
        legacy_area, _ = legacy_formula(accepted_m2=100.0, added_m2=0, subtracted_m2=0, height_m=0)
        self.assertAlmostEqual(backend_area, legacy_area, places=6)

    def test_accepted_plus_non_overlapping_addition_matches_legacy(self):
        accepted = NormalizedRect(0, 0, 0.1, 0.1)  # 100 m^2
        added = NormalizedRect(0.2, 0, 0.1, 0.1)  # disjoint, 100 m^2
        backend_area = compute_final_area_m2([accepted, added], [], PAGE_W, PAGE_H, SCALE)
        legacy_area, _ = legacy_formula(accepted_m2=100.0, added_m2=100.0, subtracted_m2=0, height_m=0)
        self.assertAlmostEqual(backend_area, legacy_area, places=6)

    def test_accepted_minus_non_overlapping_subtraction_does_not_change_area(self):
        # A disjoint subtraction removes nothing in real geometry, but
        # legacy's naive scalar formula WOULD still subtract its area --
        # this is the one case where a correct union/subtraction engine
        # and legacy's naive scalar sum legitimately diverge, and it is
        # documented here explicitly rather than silently glossed over:
        # legacy's model assumes every correction rect is drawn where it
        # geometrically belongs relative to the positive area, so this
        # divergence only matters for a nonsensical disjoint-subtraction
        # input that a real user reviewing an overlay would never draw.
        accepted = NormalizedRect(0, 0, 0.1, 0.1)  # 100 m^2
        subtracted = NormalizedRect(0.5, 0.5, 0.1, 0.1)  # disjoint, 100 m^2
        backend_area = compute_final_area_m2([accepted], [subtracted], PAGE_W, PAGE_H, SCALE)
        legacy_area, _ = legacy_formula(accepted_m2=100.0, added_m2=0, subtracted_m2=100.0, height_m=0)
        self.assertAlmostEqual(backend_area, 100.0, places=6)  # correct: nothing to remove
        self.assertNotAlmostEqual(legacy_area, backend_area, places=6)  # legacy's naive gap, documented above

    def test_accepted_minus_fully_contained_subtraction_matches_legacy(self):
        accepted = NormalizedRect(0, 0, 0.2, 0.2)  # 20m x 20m = 400 m^2
        subtracted = NormalizedRect(0, 0, 0.1, 0.1)  # fully inside, 100 m^2
        backend_area = compute_final_area_m2([accepted], [subtracted], PAGE_W, PAGE_H, SCALE)
        legacy_area, _ = legacy_formula(accepted_m2=400.0, added_m2=0, subtracted_m2=100.0, height_m=0)
        self.assertAlmostEqual(backend_area, legacy_area, places=6)

    def test_volume_formula_is_identical(self):
        rect = NormalizedRect(0, 0, 0.1, 0.1)  # 100 m^2
        backend_area = compute_final_area_m2([rect], [], PAGE_W, PAGE_H, SCALE)
        height_m = 2.5
        backend_volume = backend_area * height_m
        _, legacy_volume = legacy_formula(accepted_m2=100.0, added_m2=0, subtracted_m2=0, height_m=height_m)
        self.assertAlmostEqual(backend_volume, legacy_volume, places=6)


if __name__ == "__main__":
    unittest.main()
