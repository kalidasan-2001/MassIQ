from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.detection.detector import TooManyTilesError, run_detection
from app.hatch.feature_extractor import HatchFeatureExtractor
from app.hatch.similarity.models import ComparableFeatures
from tests import detection_fixtures as df
from tests import hatch_fixtures as hfx


def _reference() -> ComparableFeatures:
    return ComparableFeatures.from_features(HatchFeatureExtractor().extract(hfx.family_a_parallel_45()))


class RunDetectionTests(unittest.TestCase):
    def test_finds_a_region_overlapping_the_single_target(self):
        page, ground_truth = df.build_single_target_page()
        result = run_detection(page, _reference())
        self.assertEqual(len(result.candidate_regions), 1)
        region = result.candidate_regions[0]
        gt_x, gt_y, gt_w, gt_h = ground_truth[0]
        # The merged region (tile-grid granularity) must fully contain the
        # exact ground-truth box, not just overlap it loosely.
        self.assertLessEqual(region.x, gt_x)
        self.assertLessEqual(region.y, gt_y)
        self.assertGreaterEqual(region.x + region.width, gt_x + gt_w)
        self.assertGreaterEqual(region.y + region.height, gt_y + gt_h)

    def test_blank_page_produces_zero_regions(self):
        page, ground_truth = df.build_blank_page()
        result = run_detection(page, _reference())
        self.assertEqual(ground_truth, [])
        self.assertEqual(result.candidate_regions, [])
        self.assertEqual(result.tiles_evaluated, 0)
        self.assertGreater(result.tiles_skipped, 0)

    def test_multi_target_page_finds_all_targets(self):
        page, ground_truth = df.build_multi_target_page()
        result = run_detection(page, _reference())
        self.assertEqual(len(result.candidate_regions), len(ground_truth))

    def test_deterministic_repeated_runs(self):
        page, _ = df.build_single_target_page()
        reference = _reference()
        first = run_detection(page.copy(), reference)
        second = run_detection(page.copy(), reference)
        self.assertEqual(first.tiles_evaluated, second.tiles_evaluated)
        self.assertEqual(first.tiles_skipped, second.tiles_skipped)
        self.assertEqual(len(first.candidate_regions), len(second.candidate_regions))
        for a, b in zip(first.candidate_regions, second.candidate_regions):
            self.assertAlmostEqual(a.similarity, b.similarity)
            self.assertAlmostEqual(a.x, b.x)

    def test_all_regions_meet_the_candidate_threshold_and_coverage_floor(self):
        from app.detection.config import CANDIDATE_SIMILARITY_THRESHOLD, MIN_EVIDENCE_COVERAGE_FOR_CANDIDATE

        page, _ = df.build_target_with_distractors_page()
        result = run_detection(page, _reference())
        for region in result.candidate_regions:
            self.assertGreaterEqual(region.similarity, CANDIDATE_SIMILARITY_THRESHOLD)
            self.assertGreaterEqual(region.evidence_coverage, MIN_EVIDENCE_COVERAGE_FOR_CANDIDATE)

    def test_too_many_tiles_raises_a_controlled_error(self):
        huge_page = np.full((20000, 20000, 3), 255, dtype=np.uint8)
        with self.assertRaises(TooManyTilesError):
            run_detection(huge_page, _reference())

    def test_custom_tile_size_and_stride_are_respected(self):
        page, _ = df.build_single_target_page()
        default_result = run_detection(page, _reference())
        custom_result = run_detection(page, _reference(), tile_size_px=64, stride_px=64)
        # Different tiling produces a different total tile count -- proves
        # the override actually changed the grid, not just accepted silently.
        self.assertNotEqual(
            default_result.tiles_evaluated + default_result.tiles_skipped,
            custom_result.tiles_evaluated + custom_result.tiles_skipped,
        )


if __name__ == "__main__":
    unittest.main()
