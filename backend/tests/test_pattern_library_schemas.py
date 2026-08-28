from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.similarity.config import MIN_COVERAGE_FOR_HIGH_BAND
from app.schemas.pattern_library import similarity_band


class SimilarityBandTests(unittest.TestCase):
    def test_high_score_with_full_coverage_bands_high(self):
        self.assertEqual(similarity_band(0.9, evidence_coverage=1.0), "high")

    def test_medium_score_bands_medium(self):
        self.assertEqual(similarity_band(0.6, evidence_coverage=1.0), "medium")

    def test_low_score_bands_low(self):
        self.assertEqual(similarity_band(0.3, evidence_coverage=1.0), "low")

    def test_high_score_with_low_coverage_is_capped_at_medium(self):
        """The R5 negative-control finding, made permanent as a unit
        test: a numerically high score is not trustworthy on its own if
        almost none of the intended feature comparison actually had
        evidence on both sides."""
        low_coverage = MIN_COVERAGE_FOR_HIGH_BAND - 0.01
        self.assertEqual(similarity_band(0.9, evidence_coverage=low_coverage), "medium")

    def test_high_score_at_the_coverage_threshold_still_bands_high(self):
        self.assertEqual(similarity_band(0.9, evidence_coverage=MIN_COVERAGE_FOR_HIGH_BAND), "high")

    def test_default_coverage_argument_does_not_downgrade(self):
        # Callers that don't pass evidence_coverage (e.g. legacy code)
        # must not be silently downgraded -- defaults to full coverage.
        self.assertEqual(similarity_band(0.9), "high")


if __name__ == "__main__":
    unittest.main()
