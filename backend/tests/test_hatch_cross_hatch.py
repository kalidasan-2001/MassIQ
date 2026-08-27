from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.cross_hatch import classify_cross_hatch, dominant_angles_list
from app.hatch.models import AngleEvidence


class ClassifyCrossHatchTests(unittest.TestCase):
    def test_no_primary_angle_is_undetermined(self):
        evidence = AngleEvidence(None, 0.0, None, 0.0, 0)
        self.assertIsNone(classify_cross_hatch(evidence))

    def test_no_secondary_angle_is_single_direction(self):
        evidence = AngleEvidence(45.0, 1000.0, None, 0.0, 20)
        self.assertFalse(classify_cross_hatch(evidence))

    def test_weak_secondary_peak_is_still_single_direction(self):
        # Below the CROSS_HATCH_SECOND_PEAK_MIN_RATIO threshold (0.35).
        evidence = AngleEvidence(45.0, 1000.0, 135.0, 100.0, 20)
        self.assertFalse(classify_cross_hatch(evidence))

    def test_strong_secondary_peak_is_cross_hatch(self):
        evidence = AngleEvidence(45.0, 1000.0, 135.0, 900.0, 40)
        self.assertTrue(classify_cross_hatch(evidence))

    def test_ratio_boundary_is_inclusive(self):
        evidence = AngleEvidence(45.0, 1000.0, 135.0, 350.0, 40)  # exactly 0.35
        self.assertTrue(classify_cross_hatch(evidence))


class DominantAnglesListTests(unittest.TestCase):
    def test_no_primary_angle_yields_empty_list(self):
        evidence = AngleEvidence(None, 0.0, None, 0.0, 0)
        self.assertEqual(dominant_angles_list(evidence, None), [])

    def test_single_direction_yields_one_angle(self):
        evidence = AngleEvidence(45.0, 1000.0, None, 0.0, 20)
        self.assertEqual(dominant_angles_list(evidence, False), [45.0])

    def test_cross_hatch_yields_both_angles(self):
        evidence = AngleEvidence(45.0, 1000.0, 135.0, 900.0, 40)
        self.assertEqual(dominant_angles_list(evidence, True), [45.0, 135.0])

    def test_never_forces_two_angles_when_not_cross_hatch(self):
        """Even if a (weak) secondary angle exists, a non-cross-hatch
        classification must report only the primary -- no fabricated
        second orientation."""
        evidence = AngleEvidence(45.0, 1000.0, 135.0, 100.0, 20)
        self.assertEqual(dominant_angles_list(evidence, False), [45.0])


if __name__ == "__main__":
    unittest.main()
