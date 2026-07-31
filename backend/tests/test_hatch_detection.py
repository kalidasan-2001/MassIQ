from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.hatch_detection import DEFAULT_SCALE_STEPS, _passes_size_quality_filter, detect_hatch_regions

# Fixed seed => deterministic matchTemplate confidences across runs.
_RNG = np.random.default_rng(42)
_SAMPLE = _RNG.integers(0, 255, size=(20, 20), dtype=np.uint8)
_MIN_REGION_SIZE = 350  # raw template area is 400px; sits between the strong/weak effective areas below


def _build_fixture_images(tmp_dir: Path) -> tuple[Path, Path]:
    """Builds a page with two candidate matches sharing one 20x20 sample:

    - an exact copy at (10, 10) -> confidence ~1.0 (strong)
    - a heavily noised copy at (70, 70) -> confidence ~0.81, still clears the
      default 0.7 threshold but is a much weaker match (weak)
    """
    page = np.full((120, 120), 180, dtype=np.uint8)
    page[10:30, 10:30] = _SAMPLE

    noisy = _SAMPLE.astype(np.int32) + _RNG.integers(-90, 90, size=_SAMPLE.shape)
    noisy = np.clip(noisy, 0, 255).astype(np.uint8)
    page[70:90, 70:90] = noisy

    page_path = tmp_dir / "page.png"
    sample_path = tmp_dir / "sample.png"
    cv2.imwrite(str(page_path), page)
    cv2.imwrite(str(sample_path), _SAMPLE)
    return page_path, sample_path


class PassesSizeQualityFilterTests(unittest.TestCase):
    def test_weak_confidence_is_dropped_even_with_sufficient_raw_area(self):
        # raw area 20*20=400 >= min_region_size, but confidence is weak.
        self.assertFalse(_passes_size_quality_filter(20, 20, 0.81, _MIN_REGION_SIZE))

    def test_strong_confidence_of_same_size_is_kept(self):
        # Same template size as above, but a near-perfect match.
        self.assertTrue(_passes_size_quality_filter(20, 20, 1.0, _MIN_REGION_SIZE))

    def test_result_varies_per_candidate_for_identical_raw_area(self):
        # This is the core bug: same width/height, different confidence, must
        # not collapse to the same outcome.
        weak = _passes_size_quality_filter(20, 20, 0.5, _MIN_REGION_SIZE)
        strong = _passes_size_quality_filter(20, 20, 0.95, _MIN_REGION_SIZE)
        self.assertNotEqual(weak, strong)

    def test_filter_never_triggers_when_raw_area_dominates(self):
        # Realistic frontend samples (e.g. 40x40=1600px) against the default
        # min_region_size=225 should behave exactly as before: always kept.
        self.assertTrue(_passes_size_quality_filter(40, 40, 0.7, 225))
        self.assertTrue(_passes_size_quality_filter(40, 40, 1.0, 225))


class DetectHatchRegionsFilterIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.page_path, self.sample_path = _build_fixture_images(self.tmp_dir)

    def tearDown(self):
        self._tmp.cleanup()

    def test_weak_detection_dropped_strong_detection_kept(self):
        detections = detect_hatch_regions(
            self.page_path,
            self.sample_path,
            threshold=0.7,
            min_region_size=_MIN_REGION_SIZE,
            merge_nearby_detections=True,
            remove_small_noise=True,
        )
        self.assertEqual(len(detections), 1)
        self.assertEqual((detections[0]["x"], detections[0]["y"]), (10, 10))
        self.assertGreaterEqual(detections[0]["confidence"], 0.99)

    def test_noise_filter_disabled_keeps_both_detections(self):
        detections = detect_hatch_regions(
            self.page_path,
            self.sample_path,
            threshold=0.7,
            min_region_size=_MIN_REGION_SIZE,
            merge_nearby_detections=True,
            remove_small_noise=False,
        )
        positions = sorted((det["x"], det["y"]) for det in detections)
        self.assertEqual(positions, [(10, 10), (70, 70)])


def _build_multi_scale_fixture_images(tmp_dir: Path) -> tuple[Path, Path]:
    """Builds a page with the sample present at three different scales:

    - native (1.0x) at (10, 10) -- 20x20, the sample's own size
    - upscaled (2.0x) at (60, 60) -- 40x40
    - downscaled (0.7x) at (20, 110) -- 14x14

    0.7x is chosen because it's one of DEFAULT_SCALE_STEPS: raw pixel-correlation
    matching on a high-frequency random-noise texture (empirically verified) has
    very little tolerance for scale mismatches that fall *between* configured
    steps -- score dropped from 1.0 to ~0.3-0.45 for just a 5-8% gap in a quick
    check, well under the 0.7 default threshold. This fixture proves detection
    works at the configured scale grid, which is what the feature promises; it
    does not prove continuous-scale tolerance, which real (periodic, more
    self-similar) hatch fills would likely handle better than random noise does,
    but that's untested here.

    A single-scale matcher (scale_steps=(1.0,)) can only ever find the first.
    """
    page = np.full((150, 150), 180, dtype=np.uint8)
    page[10:30, 10:30] = _SAMPLE
    upscaled = cv2.resize(_SAMPLE, (40, 40), interpolation=cv2.INTER_LINEAR)
    page[60:100, 60:100] = upscaled
    downscaled = cv2.resize(_SAMPLE, (14, 14), interpolation=cv2.INTER_AREA)
    page[110:124, 20:34] = downscaled

    page_path = tmp_dir / "multi_scale_page.png"
    sample_path = tmp_dir / "multi_scale_sample.png"
    cv2.imwrite(str(page_path), page)
    cv2.imwrite(str(sample_path), _SAMPLE)
    return page_path, sample_path


class MultiScaleDetectionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.page_path, self.sample_path = _build_multi_scale_fixture_images(self.tmp_dir)

    def tearDown(self):
        self._tmp.cleanup()

    def _detect(self, **overrides):
        params = {
            "threshold": 0.7,
            "min_region_size": 50,
            "merge_nearby_detections": True,
            "remove_small_noise": True,
        }
        params.update(overrides)
        return detect_hatch_regions(self.page_path, self.sample_path, **params)

    def test_native_scale_still_detected_by_default(self):
        # Same-scale detection must keep working -- this is the "current behavior
        # remains a subset" requirement.
        detections = self._detect()
        positions = [(d["x"], d["y"]) for d in detections]
        self.assertIn((10, 10), positions)

    def test_upscaled_and_downscaled_instances_now_detected(self):
        detections = self._detect()
        found = {(d["x"], d["y"]): d for d in detections}
        self.assertIn((10, 10), found)
        self.assertIn((60, 60), found)
        self.assertIn((20, 110), found)
        # The reported box size should reflect the winning scale, not the
        # original 20x20 sample size forced onto every detection.
        self.assertEqual((found[(60, 60)]["w"], found[(60, 60)]["h"]), (40, 40))
        self.assertEqual((found[(20, 110)]["w"], found[(20, 110)]["h"]), (14, 14))
        self.assertEqual((found[(10, 10)]["w"], found[(10, 10)]["h"]), (20, 20))

    def test_single_scale_only_finds_the_native_instance(self):
        # Proves the multi-scale sweep is what closes the gap, not just that the
        # new code path happens to find more things for some unrelated reason.
        detections = self._detect(scale_steps=(1.0,))
        positions = [(d["x"], d["y"]) for d in detections]
        self.assertIn((10, 10), positions)
        self.assertNotIn((60, 60), positions)
        self.assertNotIn((20, 110), positions)

    def test_default_scale_steps_always_include_native_scale(self):
        self.assertIn(1.0, DEFAULT_SCALE_STEPS)

    def test_undersized_noise_still_filtered_within_multi_scale_pipeline(self):
        # Re-verifies the already-fixed per-detection size filter survives the
        # multi-scale refactor, using a min_region_size that only the upscaled
        # (40x40) and native (20x20) instances can clear, not the smaller 14x14 one
        # (196px area vs the 350 threshold).
        detections = self._detect(min_region_size=350)
        positions = [(d["x"], d["y"]) for d in detections]
        self.assertIn((60, 60), positions)
        self.assertNotIn((20, 110), positions)


if __name__ == "__main__":
    unittest.main()
