"""R6's mandatory synthetic detection benchmark (section 38): "plan-like"
pages with known ground truth, exercising the full tiling -> extraction ->
gating -> similarity -> thresholding -> merging pipeline together, not
just isolated units. Fully self-contained (no GPU, no external API, no
customer data) -- see tests/detection_fixtures.py.

Recall/false-positive definitions (documented, not assumed): a ground-
truth target is "found" if some candidate region's intersection with it
covers at least 50% of the target's own area (a defensible bar for a
human-review system -- the reviewer needs to see a box roughly over the
real target, not a pixel-perfect segmentation). A candidate region is a
"false positive" if it does not substantially overlap ANY ground-truth
target (less than 10% of its own area intersects any target). See
docs/testing/R6_DETECTION_BENCHMARK.md for the full measured results
these thresholds are calibrated against.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.detection.detector import run_detection
from app.hatch.feature_extractor import HatchFeatureExtractor
from app.hatch.similarity.models import ComparableFeatures
from tests import detection_fixtures as df
from tests import hatch_fixtures as hfx

_FOUND_OVERLAP_FRACTION = 0.5
_FALSE_POSITIVE_MAX_OVERLAP_FRACTION = 0.1


def _reference() -> ComparableFeatures:
    return ComparableFeatures.from_features(HatchFeatureExtractor().extract(hfx.family_a_parallel_45()))


def _intersection_area(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + aw, bx + bw)
    bottom = min(ay + ah, by + bh)
    if right <= left or bottom <= top:
        return 0.0
    return (right - left) * (bottom - top)


def _box_area(box) -> float:
    return box[2] * box[3]


def evaluate(candidate_regions, ground_truth_boxes) -> dict:
    found = 0
    for gt in ground_truth_boxes:
        gt_area = _box_area(gt)
        best_coverage = max(
            (_intersection_area((r.x, r.y, r.width, r.height), gt) / gt_area for r in candidate_regions),
            default=0.0,
        )
        if best_coverage >= _FOUND_OVERLAP_FRACTION:
            found += 1

    false_positives = 0
    for region in candidate_regions:
        region_box = (region.x, region.y, region.width, region.height)
        region_area = _box_area(region_box)
        best_overlap_fraction = max(
            (_intersection_area(region_box, gt) / region_area for gt in ground_truth_boxes),
            default=0.0,
        )
        if best_overlap_fraction < _FALSE_POSITIVE_MAX_OVERLAP_FRACTION:
            false_positives += 1

    return {
        "recall": found / len(ground_truth_boxes) if ground_truth_boxes else None,
        "found": found,
        "total_ground_truth": len(ground_truth_boxes),
        "candidate_count": len(candidate_regions),
        "false_positives": false_positives,
    }


class SyntheticBenchmarkCaseTests(unittest.TestCase):
    """One test per required case (R6 section 38)."""

    def setUp(self):
        self.reference = _reference()

    def test_one_target_region(self):
        page, gt = df.build_single_target_page()
        result = run_detection(page, self.reference)
        metrics = evaluate(result.candidate_regions, gt)
        self.assertEqual(metrics["recall"], 1.0)
        self.assertEqual(metrics["false_positives"], 0)

    def test_multiple_target_regions(self):
        page, gt = df.build_multi_target_page()
        result = run_detection(page, self.reference)
        metrics = evaluate(result.candidate_regions, gt)
        self.assertEqual(metrics["recall"], 1.0)

    def test_partial_boundary_region(self):
        page, gt = df.build_partial_boundary_page()
        result = run_detection(page, self.reference)
        metrics = evaluate(result.candidate_regions, gt)
        self.assertEqual(metrics["recall"], 1.0)

    def test_distractor_hatch(self):
        """Honest, documented finding (see benchmark doc): the dense
        cross-hatch distractor can itself score above the candidate
        threshold. Recall must still be perfect (the real target is
        found); a false positive here is expected and tracked, not hidden."""
        page, gt = df.build_target_with_distractors_page()
        result = run_detection(page, self.reference)
        metrics = evaluate(result.candidate_regions, gt)
        self.assertEqual(metrics["recall"], 1.0)

    def test_rotation_and_scale_changes(self):
        page, gt = df.build_rotated_scaled_target_page()
        result = run_detection(page, self.reference)
        metrics = evaluate(result.candidate_regions, gt)
        self.assertEqual(metrics["recall"], 1.0)

    def test_blank_page(self):
        page, gt = df.build_blank_page()
        result = run_detection(page, self.reference)
        self.assertEqual(gt, [])
        self.assertEqual(result.candidate_regions, [])

    def test_full_scene_with_dimension_lines_text_and_crossing_structural_lines(self):
        """The combined R6 section 18 fixture: dimension-like lines, text
        overlays, and crossing structural lines must not themselves
        become false-positive candidates."""
        page, gt = df.build_full_scene_page()
        result = run_detection(page, self.reference)
        metrics = evaluate(result.candidate_regions, gt)
        self.assertEqual(metrics["recall"], 1.0)
        self.assertEqual(metrics["false_positives"], 0)


class AggregateRecallTests(unittest.TestCase):
    """R6 section 20 -- candidate-region recall and false-positive count,
    measured across the whole synthetic benchmark at once, mirroring how
    R4/R5's own benchmarks report an aggregate number alongside individual
    cases."""

    def test_aggregate_recall_across_all_fixtures_meets_the_measured_floor(self):
        reference = _reference()
        total_gt = 0
        total_found = 0
        total_false_positives = 0
        for builder in (
            df.build_single_target_page,
            df.build_multi_target_page,
            df.build_partial_boundary_page,
            df.build_target_with_distractors_page,
            df.build_full_scene_page,
            df.build_rotated_scaled_target_page,
        ):
            page, gt = builder()
            result = run_detection(page, reference)
            metrics = evaluate(result.candidate_regions, gt)
            total_gt += metrics["total_ground_truth"]
            total_found += metrics["found"]
            total_false_positives += metrics["false_positives"]

        recall = total_found / total_gt
        # Measured 100% (11/11) at authoring time (see benchmark doc) --
        # asserting a floor, not the exact rate, so the test doesn't
        # become brittle against incidental future changes elsewhere in
        # the pipeline while still catching a real recall regression.
        self.assertGreaterEqual(recall, 0.9, f"recall={recall:.1%} ({total_found}/{total_gt})")
        # One known, documented false positive (the dense-cross-hatch
        # distractor) is expected -- see test_distractor_hatch above and
        # the benchmark doc. This asserts it stays small/bounded, not zero.
        self.assertLessEqual(total_false_positives, 3, f"false_positives={total_false_positives}")


if __name__ == "__main__":
    unittest.main()
