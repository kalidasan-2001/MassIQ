"""Neighbor merging (R6 section 13-14).

Groups adjacent candidate tiles (tiles that both passed quality gating and
cleared the similarity/evidence-coverage threshold -- see
detector.py) into connected regions, so one physical hatch area produces
one candidate region instead of dozens of independent, overlapping boxes.

Uses `cv2.connectedComponents` over a boolean tile-grid mask -- the
simplest defensible method (R6 section 13): tiles already sit on a regular
(row, col) grid from the tiler, so this is exactly the well-tested,
already-a-dependency connected-components primitive R4/the legacy
detector's own OpenCV usage already relies on, rather than a hand-rolled
graph/flood-fill or a new dependency.

Region geometry is a plain bounding box (the union of its member tiles'
normalized rects) -- not a polygon. R6 section 14 is explicit: do not
overbuild polygon segmentation when the existing correction/quantity UI
already works with rectangles (see frontend/src/utils/quantityEngine.js
and RegionEditor.jsx, both rectangle-based).
"""

from __future__ import annotations

import cv2
import numpy as np

from .config import MERGE_CONNECTIVITY
from .models import TileEvaluation


def group_candidate_tiles(evaluations: list[TileEvaluation]) -> list[list[TileEvaluation]]:
    """Returns a list of groups, each group being the TileEvaluations of
    one connected region of candidate tiles. Non-candidate tiles are not
    included in any group."""
    candidates = [e for e in evaluations if e.is_candidate]
    if not candidates:
        return []

    max_row = max(e.tile.row for e in candidates)
    max_col = max(e.tile.col for e in candidates)
    mask = np.zeros((max_row + 1, max_col + 1), dtype=np.uint8)
    by_position: dict[tuple[int, int], TileEvaluation] = {}
    for evaluation in candidates:
        mask[evaluation.tile.row, evaluation.tile.col] = 1
        by_position[(evaluation.tile.row, evaluation.tile.col)] = evaluation

    connectivity = 8 if MERGE_CONNECTIVITY == 8 else 4
    num_labels, labels = cv2.connectedComponents(mask, connectivity=connectivity)

    groups: list[list[TileEvaluation]] = [[] for _ in range(num_labels)]
    for (row, col), evaluation in by_position.items():
        label = labels[row, col]
        groups[label].append(evaluation)

    # Label 0 is cv2's background (non-candidate cells in the mask) --
    # never a real group, since only candidate positions were written into
    # by_position at all.
    return [group for label, group in enumerate(groups) if label != 0 and group]
