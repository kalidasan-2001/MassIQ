from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.detection.merging import group_candidate_tiles
from app.detection.models import Tile, TileEvaluation


def _tile(row, col):
    return Tile(row=row, col=col, x_px=col * 100, y_px=row * 100, width_px=100, height_px=100, x=col * 0.1, y=row * 0.1, width=0.1, height=0.1)


def _evaluation(row, col, is_candidate=True, similarity=0.8):
    return TileEvaluation(tile=_tile(row, col), scored=True, similarity=similarity, evidence_coverage=1.0, is_candidate=is_candidate)


class GroupCandidateTilesTests(unittest.TestCase):
    def test_no_candidates_returns_no_groups(self):
        evaluations = [_evaluation(0, 0, is_candidate=False)]
        self.assertEqual(group_candidate_tiles(evaluations), [])

    def test_single_isolated_candidate_is_its_own_group(self):
        evaluations = [_evaluation(0, 0), _evaluation(5, 5)]
        groups = group_candidate_tiles(evaluations)
        self.assertEqual(len(groups), 2)
        self.assertEqual({len(g) for g in groups}, {1})

    def test_adjacent_candidates_merge_into_one_group(self):
        evaluations = [_evaluation(0, 0), _evaluation(0, 1), _evaluation(1, 0), _evaluation(1, 1)]
        groups = group_candidate_tiles(evaluations)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]), 4)

    def test_diagonal_only_adjacency_still_merges_with_8_connectivity(self):
        """The documented choice (MERGE_CONNECTIVITY=8): two candidate
        tiles touching only at a corner must still merge into one region."""
        evaluations = [_evaluation(0, 0), _evaluation(1, 1)]
        groups = group_candidate_tiles(evaluations)
        self.assertEqual(len(groups), 1)

    def test_non_candidate_tiles_never_appear_in_a_group(self):
        evaluations = [_evaluation(0, 0), _evaluation(0, 1, is_candidate=False), _evaluation(0, 2)]
        groups = group_candidate_tiles(evaluations)
        # (0,0) and (0,2) are not adjacent (the gap at (0,1) is a real,
        # non-candidate tile) -- must NOT be merged into one region just
        # because they're in the same row.
        self.assertEqual(len(groups), 2)

    def test_two_separate_clusters_stay_separate(self):
        cluster_a = [_evaluation(0, 0), _evaluation(0, 1)]
        cluster_b = [_evaluation(10, 10), _evaluation(10, 11)]
        groups = group_candidate_tiles(cluster_a + cluster_b)
        self.assertEqual(len(groups), 2)
        sizes = sorted(len(g) for g in groups)
        self.assertEqual(sizes, [2, 2])

    def test_deterministic_across_repeated_calls(self):
        evaluations = [_evaluation(0, 0), _evaluation(0, 1), _evaluation(3, 3)]
        first = group_candidate_tiles(evaluations)
        second = group_candidate_tiles(evaluations)
        first_sizes = sorted(len(g) for g in first)
        second_sizes = sorted(len(g) for g in second)
        self.assertEqual(first_sizes, second_sizes)


if __name__ == "__main__":
    unittest.main()
