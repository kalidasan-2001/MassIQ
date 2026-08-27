from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.periodicity import estimate_periodicity


class EstimatePeriodicityTests(unittest.TestCase):
    def test_too_short_signal_returns_none(self):
        self.assertIsNone(estimate_periodicity(np.array([1.0, 2.0, 3.0])))

    def test_flat_signal_returns_none(self):
        self.assertIsNone(estimate_periodicity(np.ones(50)))

    def test_perfectly_periodic_signal_scores_high(self):
        x = np.arange(200)
        signal = (np.sin(2 * np.pi * x / 10.0) > 0).astype(np.float64)  # square wave, period 10
        score = estimate_periodicity(signal)
        self.assertIsNotNone(score)
        self.assertGreater(score, 0.8)

    def test_score_is_bounded(self):
        rng = np.random.default_rng(0)
        signal = rng.normal(size=200)
        score = estimate_periodicity(signal)
        if score is not None:
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)

    def test_random_noise_scores_lower_than_perfect_periodicity(self):
        rng = np.random.default_rng(1)
        noise_score = estimate_periodicity(rng.normal(size=200)) or 0.0
        x = np.arange(200)
        periodic_score = estimate_periodicity((np.sin(2 * np.pi * x / 10.0) > 0).astype(np.float64))
        self.assertLess(noise_score, periodic_score)


if __name__ == "__main__":
    unittest.main()
