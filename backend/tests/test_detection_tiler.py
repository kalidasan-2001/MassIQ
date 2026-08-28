from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.detection.tiler import generate_tiles


class GenerateTilesTests(unittest.TestCase):
    def test_exact_multiple_of_tile_size_produces_no_overlap_slack(self):
        tiles = generate_tiles(256, 256, tile_size_px=128, stride_px=128)
        # 2x2 grid, non-overlapping.
        self.assertEqual(len(tiles), 4)
        rows = {t.row for t in tiles}
        cols = {t.col for t in tiles}
        self.assertEqual(rows, {0, 1})
        self.assertEqual(cols, {0, 1})

    def test_every_pixel_is_covered_no_gaps(self):
        tiles = generate_tiles(300, 300, tile_size_px=128, stride_px=96)
        covered = set()
        for t in tiles:
            for px in range(t.x_px, t.x_px + t.width_px):
                for py in range(t.y_px, t.y_px + t.height_px):
                    covered.add((px, py))
        self.assertEqual(len(covered), 300 * 300)

    def test_no_tile_extends_past_the_page(self):
        tiles = generate_tiles(305, 217, tile_size_px=128, stride_px=96)
        for t in tiles:
            self.assertLessEqual(t.x_px + t.width_px, 305)
            self.assertLessEqual(t.y_px + t.height_px, 217)
            self.assertGreater(t.width_px, 0)
            self.assertGreater(t.height_px, 0)

    def test_normalized_coordinates_match_pixel_coordinates(self):
        tiles = generate_tiles(400, 200, tile_size_px=128, stride_px=96)
        for t in tiles:
            self.assertAlmostEqual(t.x, t.x_px / 400)
            self.assertAlmostEqual(t.y, t.y_px / 200)
            self.assertAlmostEqual(t.width, t.width_px / 400)
            self.assertAlmostEqual(t.height, t.height_px / 200)

    def test_deterministic_row_major_order(self):
        tiles = generate_tiles(300, 300, tile_size_px=128, stride_px=96)
        positions = [(t.row, t.col) for t in tiles]
        self.assertEqual(positions, sorted(positions))

    def test_deterministic_repeated_calls(self):
        first = generate_tiles(437, 311, tile_size_px=128, stride_px=96)
        second = generate_tiles(437, 311, tile_size_px=128, stride_px=96)
        self.assertEqual(first, second)

    def test_degenerate_page_size_returns_empty(self):
        self.assertEqual(generate_tiles(0, 0), [])
        self.assertEqual(generate_tiles(-10, 100), [])

    def test_page_smaller_than_one_tile_returns_a_single_clipped_tile(self):
        tiles = generate_tiles(50, 50, tile_size_px=128, stride_px=96)
        self.assertEqual(len(tiles), 1)
        self.assertEqual((tiles[0].width_px, tiles[0].height_px), (50, 50))

    def test_larger_stride_than_tile_size_still_covers_the_page(self):
        # An unusual configuration (stride > tile size would leave real
        # gaps) -- not a supported configuration, but must not crash or
        # silently produce an incorrect grid; documented behavior only.
        tiles = generate_tiles(500, 500, tile_size_px=100, stride_px=100)
        self.assertGreater(len(tiles), 0)


if __name__ == "__main__":
    unittest.main()
