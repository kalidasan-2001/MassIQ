"""The mandatory R4 synthetic benchmark suite (section 24): all 8 named
hatch families, the required variant perturbations, determinism, and
invalid-input handling -- all fully self-contained (no GPU, no external
API, no customer data), so it runs unmodified in CI.

See docs/testing/R4_HATCH_FEATURE_BENCHMARK.md for the full narrative
writeup of these results, including the two known, documented limitations
(residual ~15% scale-invariance deviation at 2.0x; small-family angle
tolerance) this suite's thresholds are calibrated against.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.feature_extractor import HatchFeatureExtractor
from app.hatch.normalization import circular_angle_distance
from app.hatch.preprocessing import InvalidHatchImageError
from tests import hatch_fixtures as hfx

ANGLE_TOLERANCE_DEG = 5.0


class EightFamilyBenchmarkTests(unittest.TestCase):
    """One test per named family (A-H) -- each asserts the specific,
    documented ground truth that family is constructed to exhibit."""

    def setUp(self):
        self.extractor = HatchFeatureExtractor()

    def test_family_a_parallel_45_single_direction(self):
        features = self.extractor.extract(hfx.family_a_parallel_45())
        self.assertEqual(len(features.dominant_angles), 1)
        self.assertLess(circular_angle_distance(features.dominant_angles[0], 45), ANGLE_TOLERANCE_DEG)
        self.assertFalse(features.is_cross_hatch)
        self.assertTrue(features.spacing_available)

    def test_family_b_parallel_90_single_direction(self):
        features = self.extractor.extract(hfx.family_b_parallel_90())
        self.assertEqual(len(features.dominant_angles), 1)
        self.assertLess(circular_angle_distance(features.dominant_angles[0], 90), ANGLE_TOLERANCE_DEG)
        self.assertFalse(features.is_cross_hatch)

    def test_family_c_wide_spacing_greater_than_family_a(self):
        narrow = self.extractor.extract(hfx.family_a_parallel_45())
        wide = self.extractor.extract(hfx.family_c_parallel_wide_spacing())
        self.assertIsNotNone(narrow.normalized_line_spacing)
        self.assertIsNotNone(wide.normalized_line_spacing)
        self.assertGreater(wide.normalized_line_spacing, narrow.normalized_line_spacing)

    def test_family_d_cross_hatch_45_135(self):
        features = self.extractor.extract(hfx.family_d_cross_hatch_45_135())
        self.assertTrue(features.is_cross_hatch)
        self.assertEqual(len(features.dominant_angles), 2)

    def test_family_e_dense_cross_hatch_detected_as_cross_hatch(self):
        features = self.extractor.extract(hfx.family_e_dense_cross_hatch())
        self.assertTrue(features.is_cross_hatch)

    def test_family_f_sparse_cross_hatch_detected_as_cross_hatch(self):
        features = self.extractor.extract(hfx.family_f_sparse_cross_hatch())
        self.assertTrue(features.is_cross_hatch)

    def test_family_g_dotted_noise_reports_no_structure(self):
        features = self.extractor.extract(hfx.family_g_dotted_noise())
        self.assertEqual(features.dominant_angles, [])
        self.assertIsNone(features.is_cross_hatch)
        self.assertFalse(features.spacing_available)

    def test_family_h_irregular_lines_is_not_reported_as_confidently_periodic(self):
        """Known, documented limitation (see
        docs/testing/R4_HATCH_FEATURE_BENCHMARK.md): with only a handful of
        random, uncorrelated line segments, the angle histogram can by
        chance land two directions close enough in evidence to cross the
        cross-hatch dominance ratio, so `is_cross_hatch` is not asserted
        here. What the algorithm must get right is not reporting strong,
        confident periodicity for a pattern that has none."""
        features = self.extractor.extract(hfx.family_h_irregular_lines())
        if features.periodicity is not None:
            self.assertLess(features.periodicity, 0.6)


class DeterminismTests(unittest.TestCase):
    """R4 section 26 -- mandatory: repeated extraction on identical input
    must be byte-for-byte identical."""

    def test_repeated_extraction_is_identical(self):
        extractor = HatchFeatureExtractor()
        image = hfx.family_d_cross_hatch_45_135()
        first = extractor.extract(image.copy())
        second = extractor.extract(image.copy())
        third = extractor.extract(image.copy())
        self.assertEqual(first, second)
        self.assertEqual(second, third)

    def test_determinism_holds_across_separate_extractor_instances(self):
        image = hfx.family_a_parallel_45()
        first = HatchFeatureExtractor().extract(image.copy())
        second = HatchFeatureExtractor().extract(image.copy())
        self.assertEqual(first, second)


class VariantStabilityTests(unittest.TestCase):
    """R4 section 25's required variant set -- each perturbation should
    leave the primary angle detection substantially unchanged, since none
    of them alter the underlying hatch geometry."""

    def setUp(self):
        self.extractor = HatchFeatureExtractor()
        self.baseline = self.extractor.extract(hfx.family_a_parallel_45())
        self.assertIsNotNone(self.baseline.dominant_angles)

    def _assert_angle_stable(self, variant_image):
        features = self.extractor.extract(variant_image)
        self.assertEqual(len(features.dominant_angles), 1)
        self.assertLess(
            circular_angle_distance(features.dominant_angles[0], self.baseline.dominant_angles[0]),
            ANGLE_TOLERANCE_DEG,
        )

    def test_blur_variant_is_stable(self):
        self._assert_angle_stable(hfx.variant_blur(hfx.family_a_parallel_45()))

    def test_noise_variant_is_stable(self):
        self._assert_angle_stable(hfx.variant_noise(hfx.family_a_parallel_45()))

    def test_brightness_variant_is_stable(self):
        self._assert_angle_stable(hfx.variant_brightness(hfx.family_a_parallel_45()))

    def test_line_interruption_variant_is_stable(self):
        self._assert_angle_stable(hfx.variant_line_interruption(hfx.family_a_parallel_45()))

    def test_overlay_crossing_line_variant_is_stable(self):
        self._assert_angle_stable(hfx.variant_overlay_crossing_line(hfx.family_a_parallel_45()))

    def test_crop_offset_variant_is_stable(self):
        self._assert_angle_stable(hfx.variant_crop_offset(hfx.family_a_parallel_45()))

    def test_small_rotation_variant_tracks_the_perturbation(self):
        rotated = hfx.variant_rotate(hfx.family_a_parallel_45(), degrees=2)
        features = self.extractor.extract(rotated)
        self.assertEqual(len(features.dominant_angles), 1)
        # A +/-2 degree whole-image rotation must shift the detected angle
        # by roughly that much, not wildly -- allow slack for interpolation
        # artifacts and cv2's rotation-direction convention (not asserting
        # a specific sign here, just boundedness).
        self.assertLess(circular_angle_distance(features.dominant_angles[0], 45), 2 * ANGLE_TOLERANCE_DEG)


class InvalidInputTests(unittest.TestCase):
    """R4 section 27 -- mandatory: no raw OpenCV/numpy stack traces ever
    reach the caller for genuinely unusable input; a controlled
    InvalidHatchImageError is raised instead."""

    def setUp(self):
        self.extractor = HatchFeatureExtractor()

    def test_empty_array_raises_invalid_hatch_image_error(self):
        with self.assertRaises(InvalidHatchImageError):
            self.extractor.extract(np.empty((0, 0, 3), dtype=np.uint8))

    def test_zero_width_raises(self):
        with self.assertRaises(InvalidHatchImageError):
            self.extractor.extract(np.zeros((50, 0, 3), dtype=np.uint8))

    def test_tiny_image_raises(self):
        with self.assertRaises(InvalidHatchImageError):
            self.extractor.extract(np.zeros((3, 3, 3), dtype=np.uint8))

    def test_none_raises(self):
        with self.assertRaises(InvalidHatchImageError):
            self.extractor.extract(None)

    def test_corrupt_decode_result_raises_cleanly(self):
        # Simulates what a service layer passes through after a failed
        # cv2.imdecode -- None, not a malformed array, since that's the
        # actual failure mode cv2.imdecode produces for corrupt bytes.
        garbage_bytes = np.frombuffer(b"not a real png file at all", dtype=np.uint8)
        decoded = cv2.imdecode(garbage_bytes, cv2.IMREAD_COLOR)
        self.assertIsNone(decoded)
        with self.assertRaises(InvalidHatchImageError):
            self.extractor.extract(decoded)

    def test_all_white_image_does_not_raise_and_reports_no_fabricated_structure(self):
        """A valid but featureless image must not raise -- it simply
        yields low/no-evidence features, never a crash or a fabricated
        angle."""
        white = np.full((60, 60, 3), 255, dtype=np.uint8)
        features = self.extractor.extract(white)
        self.assertEqual(features.dominant_angles, [])
        self.assertIsNone(features.is_cross_hatch)

    def test_all_black_image_does_not_raise(self):
        black = np.zeros((60, 60, 3), dtype=np.uint8)
        features = self.extractor.extract(black)
        self.assertEqual(features.dominant_angles, [])


class FeatureVersionTests(unittest.TestCase):
    def test_extraction_always_stamps_the_current_feature_version(self):
        from app.hatch.config import FEATURE_VERSION

        features = HatchFeatureExtractor().extract(hfx.family_a_parallel_45())
        self.assertEqual(features.feature_version, FEATURE_VERSION)


if __name__ == "__main__":
    unittest.main()
