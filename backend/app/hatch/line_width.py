"""Line-width estimation (R4 section 14).

For each detected Hough line segment (from angles.py's detection pass),
samples several interior points along the segment and measures the
perpendicular run-length of foreground pixels in the binary image at each
sample -- i.e. "how thick is the ink right here, measured across the
line, not along it." The median across all samples from all contributing
lines is the estimate; individual samples that miss the line entirely
(anti-aliasing gaps, a sample landing exactly on a background pixel) are
simply excluded rather than corrupting the result with a zero.

Deliberately conservative about precision: `normalized_line_width` is None
unless config.MIN_LINE_WIDTH_SAMPLES independent samples actually
succeeded (R4 section 14: "do not fabricate precision"). Sample points
near a segment's own endpoints are skipped -- Hough segment endpoints are
themselves the least reliable part of a detected line (most likely to be
right at a line's real termination or a gap), so only the interior 60% of
each segment is sampled.
"""

from __future__ import annotations

import numpy as np

from .config import LINE_WIDTH_SAMPLES_PER_LINE, MIN_LINE_WIDTH_SAMPLES

_SAMPLE_T_RANGE = (0.2, 0.8)  # interior of the segment only -- see module docstring
_MAX_WALK_PX = 30  # safety cap; real hatch line widths are always far below this


def _thickness_at(binary: np.ndarray, x: float, y: float, perp_dx: float, perp_dy: float) -> int | None:
    height, width = binary.shape[:2]
    px, py = int(round(x)), int(round(y))
    if not (0 <= px < width and 0 <= py < height) or binary[py, px] == 0:
        return None

    thickness = 1
    for direction in (1, -1):
        step = 1
        while step <= _MAX_WALK_PX:
            sx = int(round(x + perp_dx * direction * step))
            sy = int(round(y + perp_dy * direction * step))
            if not (0 <= sx < width and 0 <= sy < height) or binary[sy, sx] == 0:
                break
            thickness += 1
            step += 1
    return thickness


def estimate_line_width_px(binary: np.ndarray, segments: np.ndarray) -> tuple[float | None, int]:
    samples: list[int] = []
    for segment in segments:
        x1, y1, x2, y2 = segment
        length = float(np.hypot(x2 - x1, y2 - y1))
        if length <= 0:
            continue
        dx, dy = (x2 - x1) / length, (y2 - y1) / length
        perp_dx, perp_dy = -dy, dx
        for t in np.linspace(_SAMPLE_T_RANGE[0], _SAMPLE_T_RANGE[1], LINE_WIDTH_SAMPLES_PER_LINE):
            sample_x = x1 + dx * length * t
            sample_y = y1 + dy * length * t
            thickness = _thickness_at(binary, sample_x, sample_y, perp_dx, perp_dy)
            if thickness is not None:
                samples.append(thickness)

    if len(samples) < MIN_LINE_WIDTH_SAMPLES:
        return None, len(samples)
    return float(np.median(samples)), len(samples)


def normalize_line_width(width_px: float, diagonal_px: float) -> float | None:
    if diagonal_px <= 0:
        return None
    return width_px / diagonal_px
