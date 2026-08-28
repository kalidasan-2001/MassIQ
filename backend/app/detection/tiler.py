"""Deterministic page tiling (R6 section 6-7).

Divides a page image (given only its pixel dimensions -- this module never
touches an actual image, only geometry) into a grid of overlapping tiles
of a fixed size and stride. Pure and deterministic: the same
(page_width_px, page_height_px) always produces the identical tile grid,
in the identical row-major order -- this is what makes a DetectionRun's
tile indices reproducible across runs of the same detector_version.

Tiles that would run past the page's right/bottom edge are clipped to fit
within the page rather than dropped or padded -- every pixel of the page
is covered by at least one tile, and no tile ever requests pixels outside
the source image.
"""

from __future__ import annotations

from .config import TILE_SIZE_PX, TILE_STRIDE_PX
from .models import Tile


def generate_tiles(
    page_width_px: int,
    page_height_px: int,
    tile_size_px: int = TILE_SIZE_PX,
    stride_px: int = TILE_STRIDE_PX,
) -> list[Tile]:
    if page_width_px <= 0 or page_height_px <= 0:
        return []

    tiles: list[Tile] = []
    row = 0
    y = 0
    while y < page_height_px:
        col = 0
        x = 0
        height = min(tile_size_px, page_height_px - y)
        while x < page_width_px:
            width = min(tile_size_px, page_width_px - x)
            tiles.append(
                Tile(
                    row=row,
                    col=col,
                    x_px=x,
                    y_px=y,
                    width_px=width,
                    height_px=height,
                    x=x / page_width_px,
                    y=y / page_height_px,
                    width=width / page_width_px,
                    height=height / page_height_px,
                )
            )
            col += 1
            if x + tile_size_px >= page_width_px:
                break
            x += stride_px
        row += 1
        if y + tile_size_px >= page_height_px:
            break
        y += stride_px

    return tiles
