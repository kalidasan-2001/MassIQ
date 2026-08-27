from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.angles import detect_line_segments, extract_dominant_angles
from app.hatch.normalization import circular_angle_distance
from app.hatch.preprocessing import preprocess
from tests import hatch_fixtures as hfx

# How close an extracted angle must land to the fixture's known ground
# truth to count as "correct" -- generous enough to absorb rasterization/
# rotation-interpolation noise, tight enough to catch a real regression.
ANGLE_TOLERANCE_DEG = 5.0


def _evidence_for(image: np.ndarray):
    pre = preprocess(image)
    segments = detect_line_segments(pre)
    return extract_dominant_angles(segments), segments


class DominantAngleRobustnessTests(unittest.TestCase):
    """R4 section 10's required robustness set: horizontal, vertical, 45,
    135, and small rotation perturbations."""

    def test_45_degree_family(self):
        evidence, _ = _evidence_for(hfx.family_a_parallel_45())
        self.assertIsNotNone(evidence.primary_angle_deg)
        self.assertLess(circular_angle_distance(evidence.primary_angle_deg, 45), ANGLE_TOLERANCE_DEG)

    def test_90_degree_vertical_family(self):
        evidence, _ = _evidence_for(hfx.family_b_parallel_90())
        self.assertIsNotNone(evidence.primary_angle_deg)
        self.assertLess(circular_angle_distance(evidence.primary_angle_deg, 90), ANGLE_TOLERANCE_DEG)

    def test_0_degree_horizontal(self):
        image = hfx._pil_to_bgr(hfx._draw_parallel_lines(hfx.CANVAS_SIZE, angle_deg=0, spacing=10))
        evidence, _ = _evidence_for(image)
        self.assertIsNotNone(evidence.primary_angle_deg)
        self.assertLess(circular_angle_distance(evidence.primary_angle_deg, 0), ANGLE_TOLERANCE_DEG)

    def test_135_degree_family(self):
        image = hfx._pil_to_bgr(hfx._draw_parallel_lines(hfx.CANVAS_SIZE, angle_deg=135, spacing=10))
        evidence, _ = _evidence_for(image)
        self.assertIsNotNone(evidence.primary_angle_deg)
        self.assertLess(circular_angle_distance(evidence.primary_angle_deg, 135), ANGLE_TOLERANCE_DEG)

    def test_small_rotation_perturbations_track_the_perturbed_angle(self):
        for delta in (-3, -1, 1, 3):
            with self.subTest(delta=delta):
                nominal = 45 + delta
                image = hfx._pil_to_bgr(hfx._draw_parallel_lines(hfx.CANVAS_SIZE, angle_deg=nominal, spacing=10))
                evidence, _ = _evidence_for(image)
                self.assertIsNotNone(evidence.primary_angle_deg)
                self.assertLess(circular_angle_distance(evidence.primary_angle_deg, nominal), ANGLE_TOLERANCE_DEG)


class CrossHatchAngleEvidenceTests(unittest.TestCase):
    def test_cross_hatch_reports_two_well_separated_angles(self):
        evidence, _ = _evidence_for(hfx.family_d_cross_hatch_45_135())
        self.assertIsNotNone(evidence.primary_angle_deg)
        self.assertIsNotNone(evidence.secondary_angle_deg)
        self.assertGreaterEqual(circular_angle_distance(evidence.primary_angle_deg, evidence.secondary_angle_deg), 20.0)

    def test_dense_cross_hatch_still_detects_both_directions(self):
        """Regression test for the dense cross-hatch false negative found
        during R4 calibration (see hatch/config.py's HOUGH_MIN_LINE_LENGTH_RATIO
        comment): tight-spacing cross-hatch must not under-detect one
        direction due to segment fragmentation at crossings."""
        evidence, _ = _evidence_for(hfx.family_e_dense_cross_hatch())
        self.assertIsNotNone(evidence.secondary_angle_deg)
        ratio = evidence.secondary_evidence_px / evidence.primary_evidence_px
        self.assertGreaterEqual(ratio, 0.35)


class NoEvidenceControlTests(unittest.TestCase):
    def test_dotted_noise_reports_no_reliable_angle(self):
        """The non-hatch dotted control must not fabricate an angle --
        regression test for the wrong-aggregate evidence-threshold bug
        found during R4 calibration."""
        evidence, _ = _evidence_for(hfx.family_g_dotted_noise())
        self.assertIsNone(evidence.primary_angle_deg)

    def test_empty_segments_returns_no_evidence(self):
        from app.hatch.models import AngleEvidence

        evidence = extract_dominant_angles(np.empty((0, 4), dtype=np.float64))
        self.assertEqual(evidence, AngleEvidence(None, 0.0, None, 0.0, 0))


if __name__ == "__main__":
    unittest.main()
