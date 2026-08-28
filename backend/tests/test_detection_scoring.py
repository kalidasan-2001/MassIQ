from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.detection.models import Tile, TileEvaluation
from app.detection.scoring import score_region


def _tile(row, col):
    return Tile(row=row, col=col, x_px=col * 100, y_px=row * 100, width_px=100, height_px=100, x=col * 0.1, y=row * 0.1, width=0.1, height=0.1)


def _evaluation(row, col, similarity, coverage=1.0):
    return TileEvaluation(tile=_tile(row, col), scored=True, similarity=similarity, evidence_coverage=coverage, is_candidate=True)


class ScoreRegionTests(unittest.TestCase):
    def test_median_not_mean_for_similarity(self):
        """R6 section 15's explicit requirement: one high outlier tile
        must not make a mostly-weak region look confidently scored."""
        group = [_evaluation(0, 0, 0.66), _evaluation(0, 1, 0.67), _evaluation(0, 2, 0.99)]
        region = score_region(group)
        self.assertAlmostEqual(region.similarity, 0.67)  # median, not (0.66+0.67+0.99)/3=0.773 or max=0.99
        self.assertNotAlmostEqual(region.similarity, max(e.similarity for e in group))

    def test_mean_for_evidence_coverage(self):
        group = [_evaluation(0, 0, 0.8, coverage=0.5), _evaluation(0, 1, 0.8, coverage=1.0)]
        region = score_region(group)
        self.assertAlmostEqual(region.evidence_coverage, 0.75)

    def test_bounding_box_is_the_union_of_member_tiles(self):
        group = [_evaluation(0, 0, 0.8), _evaluation(1, 1, 0.8)]
        region = score_region(group)
        self.assertAlmostEqual(region.x, 0.0)
        self.assertAlmostEqual(region.y, 0.0)
        self.assertAlmostEqual(region.width, 0.2)  # spans col 0 and col 1 (each 0.1 wide)
        self.assertAlmostEqual(region.height, 0.2)

    def test_tile_count_recorded(self):
        group = [_evaluation(0, 0, 0.8), _evaluation(0, 1, 0.8), _evaluation(1, 0, 0.8)]
        region = score_region(group)
        self.assertEqual(region.tile_count, 3)

    def test_single_tile_region_score_equals_that_tiles_score(self):
        group = [_evaluation(4, 4, 0.91, coverage=0.7)]
        region = score_region(group)
        self.assertAlmostEqual(region.similarity, 0.91)
        self.assertAlmostEqual(region.evidence_coverage, 0.7)


if __name__ == "__main__":
    unittest.main()
