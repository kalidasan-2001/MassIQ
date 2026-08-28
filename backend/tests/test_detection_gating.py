from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.detection.gating import tile_passes_quality_gate
from app.hatch.feature_extractor import HatchFeatureExtractor
from tests import hatch_fixtures as hfx


class TileQualityGateTests(unittest.TestCase):
    def setUp(self):
        self.extractor = HatchFeatureExtractor()

    def test_a_real_hatch_tile_passes(self):
        features = self.extractor.extract(hfx.family_a_parallel_45(size=128))
        self.assertTrue(tile_passes_quality_gate(features))

    def test_a_blank_white_tile_is_skipped(self):
        import numpy as np

        blank = np.full((128, 128, 3), 255, dtype=np.uint8)
        features = self.extractor.extract(blank)
        self.assertFalse(tile_passes_quality_gate(features))

    def test_a_dotted_noise_tile_is_skipped(self):
        """Same non-hatch control R4's own benchmark uses -- must not
        pass the tile gate either, for the same reason R4 gates it out of
        angle evidence at all."""
        features = self.extractor.extract(hfx.family_g_dotted_noise(size=128))
        self.assertFalse(tile_passes_quality_gate(features))


if __name__ == "__main__":
    unittest.main()
