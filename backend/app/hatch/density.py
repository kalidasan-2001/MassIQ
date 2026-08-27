"""Line density (R4 section 13): the fraction of foreground (ink) pixels
within the detected pattern region.

Computed over the bounding box of the binary image's own foreground
pixels, not the full crop -- a crop with legitimate blank margin around a
tight hatch pattern (very common: a user's drag selection is rarely
pixel-perfect around the pattern) would otherwise report an artificially
low density purely because of how tightly the user happened to draw the
selection box, which has nothing to do with the pattern itself. If no
foreground pixels exist at all (a blank crop), density is 0.0 -- bounded,
deterministic, and doesn't divide by a zero-area bounding box.
"""

from __future__ import annotations

import numpy as np


def compute_density(binary: np.ndarray) -> float:
    nonzero_rows, nonzero_cols = np.nonzero(binary)
    if nonzero_rows.size == 0:
        return 0.0

    top, bottom = nonzero_rows.min(), nonzero_rows.max()
    left, right = nonzero_cols.min(), nonzero_cols.max()
    region = binary[top : bottom + 1, left : right + 1]
    region_area = region.size
    if region_area == 0:
        return 0.0

    foreground_count = int(np.count_nonzero(region))
    return float(foreground_count) / float(region_area)
