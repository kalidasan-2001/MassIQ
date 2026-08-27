"""Line-spacing estimation (R4 section 11).

Uses projection.py's rotated row-projection signal: each hatch line
produces one peak in that 1D signal, so the median distance between
consecutive peaks is the line spacing, in pixels, *after* rotation.

That raw pixel spacing is then normalized by the crop's own (pre-rotation)
diagonal length, so the same physical-looking hatch rendered at a
different resolution/scale produces a comparable value -- see R4 section
12's scale-invariance requirement and
docs/testing/R4_HATCH_FEATURE_BENCHMARK.md for the measured evidence.

Deliberately does not use `scipy.signal.find_peaks` -- a small, local,
numpy-only peak finder (`find_peaks_1d`) is simple enough to implement
directly and avoids adding a new backend dependency for one function.
"""

from __future__ import annotations

import numpy as np

from .config import (
    MIN_PEAKS_FOR_SPACING,
    PROJECTION_PEAK_MIN_DISTANCE_FLOOR_PX,
    PROJECTION_PEAK_MIN_DISTANCE_RATIO,
    PROJECTION_PEAK_MIN_PROMINENCE_RATIO,
)


def find_peaks_1d(signal: np.ndarray, min_distance: int, min_prominence: float) -> list[int]:
    """Local maxima at least `min_distance` apart, each required to stand
    out from its immediate surroundings by at least `min_prominence`
    (absolute units of the signal itself). Simple and deterministic:
    scans for candidates, then greedily keeps the strongest ones subject
    to the distance constraint (a plain non-max-suppression pass) --
    intentionally not scipy's more elaborate prominence algorithm, which
    would be overkill for the clean, single-scale peaks this projection
    signal produces."""
    n = len(signal)
    if n < 3:
        return []

    candidates = []
    for i in range(1, n - 1):
        if signal[i] >= signal[i - 1] and signal[i] >= signal[i + 1] and signal[i] > 0:
            local_min = min(
                signal[max(0, i - min_distance) : i].min() if i > 0 else signal[i],
                signal[i + 1 : i + 1 + min_distance].min() if i + 1 < n else signal[i],
            )
            prominence = signal[i] - local_min
            if prominence >= min_prominence:
                candidates.append((i, signal[i]))

    candidates.sort(key=lambda item: item[1], reverse=True)
    kept: list[int] = []
    for index, _value in candidates:
        if all(abs(index - other) >= min_distance for other in kept):
            kept.append(index)
    return sorted(kept)


def estimate_spacing_px(projection: np.ndarray, reference_dimension_px: float) -> tuple[float | None, int]:
    """Returns (median_spacing_px, peak_count). median_spacing_px is None
    when fewer than config.MIN_PEAKS_FOR_SPACING peaks were found -- a
    single peak has no spacing to measure between, and reporting a
    fabricated value would be worse than reporting none.

    `reference_dimension_px` (the crop's own diagonal -- the same
    resolution-independent reference used to normalize the final spacing
    value) scales the minimum peak-separation distance so it behaves
    consistently across crop sizes; see config.PROJECTION_PEAK_MIN_DISTANCE_RATIO.
    """
    signal_range = float(projection.max() - projection.min()) if projection.size else 0.0
    if signal_range <= 0:
        return None, 0

    min_distance = max(
        PROJECTION_PEAK_MIN_DISTANCE_FLOOR_PX, int(reference_dimension_px * PROJECTION_PEAK_MIN_DISTANCE_RATIO)
    )
    min_prominence = signal_range * PROJECTION_PEAK_MIN_PROMINENCE_RATIO
    peaks = find_peaks_1d(projection, min_distance, min_prominence)
    if len(peaks) < MIN_PEAKS_FOR_SPACING:
        return None, len(peaks)

    spacings = np.diff(peaks).astype(np.float64)
    return float(np.median(spacings)), len(peaks)


def normalize_spacing(spacing_px: float, diagonal_px: float) -> float | None:
    if diagonal_px <= 0:
        return None
    return spacing_px / diagonal_px
