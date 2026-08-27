"""Periodicity estimation (R4 section 16) via projection autocorrelation --
the simplest deterministic method that reuses the exact same rotated
projection signal spacing.py already computes, rather than reaching for an
FFT-based periodogram (R4 section 16: "do not overcomplicate with FFT
unless it provides clear value" -- autocorrelation on this already-short
1D signal is cheaper and just as informative here).

Method: mean-center the projection, compute its normalized autocorrelation
across a range of lags, and take the strongest peak at a lag greater than
zero. A perfectly periodic signal (evenly spaced identical lines) has an
autocorrelation near 1.0 at the lag equal to its period; an irregular
signal's autocorrelation decays quickly and never climbs back up.

Range: [0.0, 1.0]. 0.0 = no periodicity evidence (or negative correlation,
clipped); 1.0 = perfectly periodic. Documented explicitly since R4 section
16 allows other ranges as long as they're documented.
"""

from __future__ import annotations

import numpy as np

MIN_LAG_FRACTION = 0.02  # skip near-zero lags (always maximally self-similar, not informative)
MAX_LAG_FRACTION = 0.5  # searching past half the signal length starts wrapping onto itself


def estimate_periodicity(projection: np.ndarray) -> float | None:
    n = len(projection)
    if n < 8:
        return None

    centered = projection - projection.mean()
    energy = float(np.dot(centered, centered))
    if energy <= 0:
        return None

    min_lag = max(1, int(n * MIN_LAG_FRACTION))
    max_lag = max(min_lag + 1, int(n * MAX_LAG_FRACTION))
    if max_lag >= n:
        max_lag = n - 1
    if min_lag >= max_lag:
        return None

    best = 0.0
    for lag in range(min_lag, max_lag):
        correlation = float(np.dot(centered[:-lag], centered[lag:]))
        normalized = correlation / energy
        if normalized > best:
            best = normalized

    return float(np.clip(best, 0.0, 1.0))
