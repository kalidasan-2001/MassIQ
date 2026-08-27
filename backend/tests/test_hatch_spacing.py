from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.projection import rotate_to_align, row_projection
from app.hatch.spacing import estimate_spacing_px, find_peaks_1d, normalize_spacing
from app.hatch.preprocessing import preprocess
from tests import hatch_fixtures as hfx


class FindPeaks1dTests(unittest.TestCase):
    def test_finds_evenly_spaced_peaks(self):
        signal = np.zeros(50)
        for center in (5, 15, 25, 35, 45):
            signal[center] = 10
        peaks = find_peaks_1d(signal, min_distance=5, min_prominence=1)
        self.assertEqual(peaks, [5, 15, 25, 35, 45])

    def test_short_signal_returns_no_peaks(self):
        self.assertEqual(find_peaks_1d(np.array([1.0, 2.0]), min_distance=1, min_prominence=0.1), [])

    def test_min_distance_suppresses_close_duplicate_peaks(self):
        signal = np.zeros(30)
        signal[10] = 10
        signal[12] = 9  # close shoulder of the same peak
        signal[20] = 10
        peaks = find_peaks_1d(signal, min_distance=5, min_prominence=1)
        self.assertEqual(len(peaks), 2)

    def test_low_prominence_bumps_are_rejected(self):
        signal = np.ones(30)
        signal[15] = 1.05  # negligible bump
        peaks = find_peaks_1d(signal, min_distance=2, min_prominence=1.0)
        self.assertEqual(peaks, [])


class EstimateSpacingPxTests(unittest.TestCase):
    def test_flat_signal_returns_none(self):
        spacing, count = estimate_spacing_px(np.ones(50), reference_dimension_px=100.0)
        self.assertIsNone(spacing)
        self.assertEqual(count, 0)

    def test_single_peak_returns_none_spacing(self):
        signal = np.zeros(50)
        signal[25] = 10
        spacing, count = estimate_spacing_px(signal, reference_dimension_px=100.0)
        self.assertIsNone(spacing)

    def test_known_synthetic_spacing_recovered(self):
        signal = np.zeros(100)
        for center in (10, 20, 30, 40, 50, 60, 70, 80, 90):
            signal[center] = 10
        spacing, count = estimate_spacing_px(signal, reference_dimension_px=200.0)
        self.assertAlmostEqual(spacing, 10.0)
        self.assertEqual(count, 9)


class NormalizeSpacingTests(unittest.TestCase):
    def test_divides_by_diagonal(self):
        self.assertAlmostEqual(normalize_spacing(10.0, 100.0), 0.1)

    def test_zero_diagonal_returns_none(self):
        self.assertIsNone(normalize_spacing(10.0, 0.0))


class ScaleInvarianceTests(unittest.TestCase):
    """R4's critical success criterion (section 12): normalized spacing
    for the same physical pattern rendered at different resolutions must
    stay comparable. Tested at every scale R4 section 12 lists."""

    def _normalized_spacing_at_scale(self, scale: float) -> float:
        image = hfx.variant_scale(hfx.family_a_parallel_45(), scale)
        pre = preprocess(image)
        from app.hatch.angles import detect_line_segments, extract_dominant_angles

        segments = detect_line_segments(pre)
        evidence = extract_dominant_angles(segments)
        self.assertIsNotNone(evidence.primary_angle_deg)
        rotated = rotate_to_align(pre.binary, evidence.primary_angle_deg)
        projection = row_projection(rotated)
        spacing_px, _count = estimate_spacing_px(projection, pre.diagonal_px)
        self.assertIsNotNone(spacing_px)
        return normalize_spacing(spacing_px, pre.diagonal_px)

    def test_normalized_spacing_stable_across_scales(self):
        baseline = self._normalized_spacing_at_scale(1.0)
        for scale in (0.5, 0.75, 1.5, 2.0):
            with self.subTest(scale=scale):
                value = self._normalized_spacing_at_scale(scale)
                relative_error = abs(value - baseline) / baseline
                # 20% margin: measured worst case during R4 calibration was
                # ~15% at 2.0x (see docs/testing/R4_HATCH_FEATURE_BENCHMARK.md)
                # -- documented as a known limitation, not engineered away
                # by silently loosening this test past what was measured.
                self.assertLess(relative_error, 0.20, f"scale={scale} relative_error={relative_error:.3f}")


if __name__ == "__main__":
    unittest.main()
