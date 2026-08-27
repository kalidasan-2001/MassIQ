"""Color features (R4 section 17): descriptive only, never a primary
classifier on their own.

Uses CIELAB rather than raw BGR/RGB averages -- LAB separates lightness
(L) from the two color-opponent channels (a: green-red, b: blue-yellow),
which is far less sensitive to simple brightness/exposure differences
between two renders of the same crop than averaging raw color channels
directly would be (a darker scan of the same colored fill shifts B/G/R
means substantially; it shifts LAB's a/b much less).

Computed over the *original* color crop, before grayscale/binarization --
color.py never sees the thresholded structure-only image, since
binarizing would destroy the color signal entirely.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class ColorFeatures:
    mean_l: float
    mean_a: float
    mean_b: float
    std_l: float
    std_a: float
    std_b: float


def compute_color_features(original_bgr: np.ndarray) -> ColorFeatures:
    lab = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2LAB).astype(np.float64)
    l_channel, a_channel, b_channel = lab[:, :, 0], lab[:, :, 1], lab[:, :, 2]
    return ColorFeatures(
        mean_l=float(l_channel.mean()),
        mean_a=float(a_channel.mean()),
        mean_b=float(b_channel.mean()),
        std_l=float(l_channel.std()),
        std_a=float(a_channel.std()),
        std_b=float(b_channel.std()),
    )
