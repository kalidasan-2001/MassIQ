"""Shared "rotate so hatch lines align, then project perpendicular to
them" signal -- both spacing.py (line spacing) and periodicity.py
(regularity) are computed from the exact same 1D projection, so it's
computed once here rather than twice (which would double the CV cost and
risk the two features disagreeing about what they measured).

R4 section 11's preferred strategy, directly:
1. Rotate the binary image by -angle so the hatch lines become horizontal.
2. Sum foreground pixels along each row -> a 1D signal where each hatch
   line produces one peak, at the row where it crosses.
"""

from __future__ import annotations

import cv2
import numpy as np


def rotate_to_align(binary: np.ndarray, angle_deg: float) -> np.ndarray:
    """Rotates `binary` so a line at `angle_deg` (in [0, 180), the
    hatch-orientation convention -- see normalization.py) becomes
    horizontal. Background-fills with 0 (matches the binary image's own
    background value after preprocessing's THRESH_BINARY_INV)."""
    height, width = binary.shape[:2]
    center = (width / 2.0, height / 2.0)
    rotation_matrix = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    # Expand the output canvas so corners rotated into view aren't clipped
    # -- a clipped line would bias the projection signal near the edges.
    cos = abs(rotation_matrix[0, 0])
    sin = abs(rotation_matrix[0, 1])
    new_width = int(height * sin + width * cos)
    new_height = int(height * cos + width * sin)
    rotation_matrix[0, 2] += (new_width - width) / 2.0
    rotation_matrix[1, 2] += (new_height - height) / 2.0
    return cv2.warpAffine(binary, rotation_matrix, (new_width, new_height), flags=cv2.INTER_NEAREST, borderValue=0)


def row_projection(rotated_binary: np.ndarray) -> np.ndarray:
    """Sums foreground pixels per row -- a 1D signal with one peak per
    hatch line once the image has been rotated so lines run horizontally."""
    return rotated_binary.astype(np.float64).sum(axis=1)
