"""R6 section 17/31 -- compares the legacy multi-scale `matchTemplate`
detector (backend/app/services/hatch_detection.py, untouched by R6)
against Detection V2 on the SAME synthetic fixtures. Legacy is not
deleted, not rewritten, and not automatically combined with V2 (R6
sections 16-17) -- this file only measures both independently and reports
the comparison honestly (see docs/testing/R6_DETECTION_BENCHMARK.md for
the full narrative, including any case where legacy performs
comparably or better).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import cv2

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.detection.detector import run_detection
from app.hatch.feature_extractor import HatchFeatureExtractor
from app.hatch.similarity.models import ComparableFeatures
from app.services.hatch_detection import detect_hatch_regions
from tests import detection_fixtures as df
from tests import hatch_fixtures as hfx
from tests.test_detection_synthetic_benchmark import evaluate


def _legacy_boxes_to_normalized(detections: list[dict], page_width: int, page_height: int):
    class _Box:
        def __init__(self, x, y, w, h):
            self.x, self.y, self.width, self.height = x, y, w, h

    return [
        _Box(d["x"] / page_width, d["y"] / page_height, d["w"] / page_width, d["h"] / page_height)
        for d in detections
    ]


class LegacyVsV2ComparisonTests(unittest.TestCase):
    """Runs both detectors on the same fixture and reports metrics for
    each independently -- never combines them, per R6 section 17."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.reference_features = ComparableFeatures.from_features(
            HatchFeatureExtractor().extract(hfx.family_a_parallel_45())
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _run_both(self, page_image, sample_image):
        tmp_dir = Path(self._tmp.name)
        page_path = tmp_dir / "page.png"
        sample_path = tmp_dir / "sample.png"
        cv2.imwrite(str(page_path), page_image)
        cv2.imwrite(str(sample_path), sample_image)

        legacy_raw = detect_hatch_regions(page_path, sample_path)
        page_h, page_w = page_image.shape[:2]
        legacy_boxes = _legacy_boxes_to_normalized(legacy_raw, page_w, page_h)

        v2_result = run_detection(page_image, self.reference_features)
        return legacy_boxes, v2_result.candidate_regions

    def test_single_target_comparison(self):
        page_image, ground_truth = df.build_single_target_page()
        sample_image = hfx.family_a_parallel_45(size=40)
        legacy_boxes, v2_regions = self._run_both(page_image, sample_image)

        legacy_metrics = evaluate(legacy_boxes, ground_truth)
        v2_metrics = evaluate(v2_regions, ground_truth)
        print(f"\n[single target] legacy={legacy_metrics} v2={v2_metrics}")
        # Both must at least run cleanly and return a real (possibly
        # empty) result -- no strict "V2 must win" assertion here, per R6
        # section 31's explicit "do not claim V2 is better unless measured."
        self.assertIsInstance(legacy_metrics["candidate_count"], int)
        self.assertIsInstance(v2_metrics["candidate_count"], int)

    def test_distractor_comparison(self):
        page_image, ground_truth = df.build_target_with_distractors_page()
        sample_image = hfx.family_a_parallel_45(size=40)
        legacy_boxes, v2_regions = self._run_both(page_image, sample_image)

        legacy_metrics = evaluate(legacy_boxes, ground_truth)
        v2_metrics = evaluate(v2_regions, ground_truth)
        print(f"\n[distractor] legacy={legacy_metrics} v2={v2_metrics}")
        self.assertIsInstance(legacy_metrics["candidate_count"], int)
        self.assertIsInstance(v2_metrics["candidate_count"], int)

    def test_rotated_scaled_comparison(self):
        """The case legacy is expected to struggle with most -- a
        rotated, differently-scaled target -- matchTemplate has no
        rotation invariance at all (only its own fixed multi-scale
        steps), while V2's R4 features are explicitly angle/scale-aware.
        Measured, not assumed."""
        page_image, ground_truth = df.build_rotated_scaled_target_page()
        sample_image = hfx.family_a_parallel_45(size=40)
        legacy_boxes, v2_regions = self._run_both(page_image, sample_image)

        legacy_metrics = evaluate(legacy_boxes, ground_truth)
        v2_metrics = evaluate(v2_regions, ground_truth)
        print(f"\n[rotated/scaled] legacy={legacy_metrics} v2={v2_metrics}")
        self.assertIsInstance(legacy_metrics["candidate_count"], int)
        self.assertIsInstance(v2_metrics["candidate_count"], int)


if __name__ == "__main__":
    unittest.main()
