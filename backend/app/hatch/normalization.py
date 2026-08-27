"""Shared normalization helpers -- primarily circular angle arithmetic.

Hatch-line orientation is periodic over 180 degrees: a line has no
"direction", so a line at 179 degrees and a line at 1 degree are nearly
the same orientation (2 degrees apart), not 178 degrees apart. Every
place in `backend/app/hatch/` that compares or averages angles must go
through these functions rather than plain subtraction.
"""

from __future__ import annotations

from .config import ANGLE_PERIOD_DEG


def normalize_angle(angle_deg: float, period: float = ANGLE_PERIOD_DEG) -> float:
    """Wraps an angle into [0, period)."""
    return angle_deg % period


def circular_angle_distance(a_deg: float, b_deg: float, period: float = ANGLE_PERIOD_DEG) -> float:
    """Shortest distance between two angles on a circle of the given period.

    Example (period=180, the hatch-orientation case): distance(179, 1) == 2,
    not 178 -- wrapping through 0/180 is shorter than going the long way
    around.
    """
    diff = abs(normalize_angle(a_deg, period) - normalize_angle(b_deg, period)) % period
    return min(diff, period - diff)
