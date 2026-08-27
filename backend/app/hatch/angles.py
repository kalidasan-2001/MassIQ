"""Dominant hatch-line orientation extraction.

Method (R4 section 9's suggested approach, implemented directly):
1. Detect line segments in the preprocessed edge image with the
   probabilistic Hough transform (`cv2.HoughLinesP`).
2. Convert each segment to an orientation angle in [0, 180) (a line has no
   direction, so 179 degrees and 1 degree are the same family -- see
   normalization.py) and weight it by the segment's own length: a long,
   confidently-detected line should outvote several short noise segments.
3. Accumulate weighted evidence into a circular histogram over [0, 180),
   smooth it with a small circular moving average (absorbs bin-edge
   jitter), and find peaks.
4. The strongest peak is the primary orientation. A second peak only
   counts as a genuine second hatch direction if it is both angularly
   separated from the first (not its shoulder) AND carries a meaningful
   fraction of the first peak's evidence (config.CROSS_HATCH_SECOND_PEAK_MIN_RATIO)
   -- see cross_hatch.py, which makes the actual single/cross decision
   from this evidence.
5. If total evidence falls below config.MIN_ANGLE_EVIDENCE_PX, no angle is
   reported at all (None) -- a controlled "insufficient evidence" result,
   never a fabricated angle.
"""

from __future__ import annotations

import cv2
import numpy as np

from .config import (
    ANGLE_BIN_COUNT,
    ANGLE_BIN_WIDTH_DEG,
    ANGLE_SMOOTHING_WINDOW_BINS,
    HOUGH_MAX_LINE_GAP_RATIO,
    HOUGH_MIN_LINE_LENGTH_RATIO,
    HOUGH_RHO_RESOLUTION_PX,
    HOUGH_THETA_RESOLUTION_RAD_DIVISOR,
    HOUGH_VOTE_THRESHOLD,
    MIN_ANGLE_EVIDENCE_PX,
    MIN_PEAK_SEPARATION_DEG,
)
from .models import AngleEvidence
from .normalization import circular_angle_distance, normalize_angle
from .preprocessing import PreprocessedImage


def detect_line_segments(pre: PreprocessedImage) -> np.ndarray:
    """Returns an (N, 4) array of [x1, y1, x2, y2] segments, possibly empty."""
    min_length = max(4, int(min(pre.width, pre.height) * HOUGH_MIN_LINE_LENGTH_RATIO))
    max_gap = max(1, int(min(pre.width, pre.height) * HOUGH_MAX_LINE_GAP_RATIO))
    segments = cv2.HoughLinesP(
        pre.edges,
        HOUGH_RHO_RESOLUTION_PX,
        np.pi / HOUGH_THETA_RESOLUTION_RAD_DIVISOR,
        HOUGH_VOTE_THRESHOLD,
        minLineLength=min_length,
        maxLineGap=max_gap,
    )
    if segments is None:
        return np.empty((0, 4), dtype=np.float64)
    return segments.reshape(-1, 4).astype(np.float64)


def _segment_angle_and_length(segment: np.ndarray) -> tuple[float, float]:
    x1, y1, x2, y2 = segment
    length = float(np.hypot(x2 - x1, y2 - y1))
    angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
    return normalize_angle(angle), length


def _weighted_angle_histogram(segments: np.ndarray) -> np.ndarray:
    histogram = np.zeros(ANGLE_BIN_COUNT, dtype=np.float64)
    for segment in segments:
        angle, length = _segment_angle_and_length(segment)
        bin_index = int(angle // ANGLE_BIN_WIDTH_DEG) % ANGLE_BIN_COUNT
        histogram[bin_index] += length
    return histogram


def _smooth_circular(histogram: np.ndarray, window_bins: int) -> np.ndarray:
    if window_bins <= 1:
        return histogram
    kernel = np.ones(window_bins) / window_bins
    # Circular convolution: pad by wrapping both ends around, matching the
    # angle histogram's own periodicity, then trim back to the original size.
    pad = window_bins // 2
    padded = np.concatenate([histogram[-pad:], histogram, histogram[:pad]]) if pad else histogram
    smoothed = np.convolve(padded, kernel, mode="same" if pad == 0 else "valid")
    return smoothed[: len(histogram)] if len(smoothed) >= len(histogram) else histogram


def _find_circular_peaks(histogram: np.ndarray) -> list[tuple[int, float]]:
    """Returns (bin_index, weight) for every bin that is a local maximum
    (>= both circular neighbors), sorted by weight descending."""
    n = len(histogram)
    peaks = []
    for i in range(n):
        left = histogram[i - 1]
        right = histogram[(i + 1) % n]
        if histogram[i] >= left and histogram[i] >= right and histogram[i] > 0:
            peaks.append((i, histogram[i]))
    peaks.sort(key=lambda item: item[1], reverse=True)
    return peaks


def extract_dominant_angles(segments: np.ndarray) -> AngleEvidence:
    """Takes already-detected Hough segments (see detect_line_segments) --
    the caller (feature_extractor.py) detects segments exactly once and
    reuses them here and for line-width estimation, rather than running
    the Hough transform twice."""
    if len(segments) == 0:
        return AngleEvidence(None, 0.0, None, 0.0, 0)

    raw_histogram = _weighted_angle_histogram(segments)
    histogram = _smooth_circular(raw_histogram, ANGLE_SMOOTHING_WINDOW_BINS)
    peaks = _find_circular_peaks(histogram)
    if not peaks:
        return AngleEvidence(None, 0.0, None, 0.0, len(segments))

    def bin_to_angle(bin_index: int) -> float:
        return (bin_index + 0.5) * ANGLE_BIN_WIDTH_DEG

    primary_bin, primary_weight = peaks[0]
    # The threshold is against the WINNING peak's own evidence, not the
    # histogram's total sum across every direction -- a crop full of
    # short, randomly-oriented segments (e.g. edges of scattered dots)
    # can easily accumulate a large *total* across all bins combined while
    # no single orientation is actually well-supported; checking the total
    # would let that case through as "reliable," which it isn't.
    if primary_weight < MIN_ANGLE_EVIDENCE_PX:
        return AngleEvidence(None, 0.0, None, 0.0, len(segments))
    primary_angle = bin_to_angle(primary_bin)

    secondary_angle: float | None = None
    secondary_weight = 0.0
    for bin_index, weight in peaks[1:]:
        candidate_angle = bin_to_angle(bin_index)
        if circular_angle_distance(candidate_angle, primary_angle) >= MIN_PEAK_SEPARATION_DEG:
            secondary_angle = candidate_angle
            secondary_weight = weight
            break

    return AngleEvidence(
        primary_angle_deg=primary_angle,
        primary_evidence_px=float(primary_weight),
        secondary_angle_deg=secondary_angle,
        secondary_evidence_px=float(secondary_weight),
        line_count=len(segments),
    )
