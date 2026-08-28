"""Synthetic, reproducible "plan-like" page fixtures for R6's Detection
Engine V2 benchmark -- same spirit as hatch_fixtures.py (R4) and its own
reuse in R5: built programmatically so tests never depend on private
customer plans, and so ground-truth target-region boxes are always known
exactly, never estimated.

Each builder returns `(page_image_bgr, ground_truth_boxes)`, where
`ground_truth_boxes` is a list of normalized (x, y, width, height) rects
-- the same coordinate contract every other overlay in this app uses
(see docs/releases/R3_LEGEND_WORKFLOW_CHECKLIST.md's coordinate section).

Deliberately reuses hatch_fixtures.py's own line-drawing primitives
(`_draw_parallel_lines`, `_combine_min`) rather than reimplementing hatch
rendering a second time with a possibly-different angle convention.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from tests import hatch_fixtures as hfx

PAGE_SIZE = (900, 700)  # (width, height) px -- a plausible plan-page-preview size
BG_COLOR = (255, 255, 255)
LINE_COLOR = (0, 0, 0)


def _blank_page(size: tuple[int, int] = PAGE_SIZE) -> Image.Image:
    return Image.new("RGB", size, color=BG_COLOR)


def _paste_pattern(page: Image.Image, pattern: Image.Image, x: int, y: int) -> None:
    page.paste(pattern, (x, y))


def _to_normalized_box(x: int, y: int, w: int, h: int, page_size: tuple[int, int]) -> tuple[float, float, float, float]:
    pw, ph = page_size
    return (x / pw, y / ph, w / pw, h / ph)


def _draw_dimension_line(draw: ImageDraw.ImageDraw, x1: int, y1: int, x2: int, y2: int) -> None:
    """A thin straight line with small perpendicular tick marks at each
    end -- visually close to an architectural dimension line, and
    deliberately NOT a repeating hatch pattern (a single line, no
    periodicity), so it should never itself pass R4's angle-evidence gate
    strongly enough to be mistaken for a hatch tile."""
    draw.line([(x1, y1), (x2, y2)], fill=LINE_COLOR, width=1)
    tick = 6
    for x, y in ((x1, y1), (x2, y2)):
        draw.line([(x - tick, y - tick), (x + tick, y + tick)], fill=LINE_COLOR, width=1)


def _draw_text_block(draw: ImageDraw.ImageDraw, x: int, y: int, text: str) -> None:
    draw.multiline_text((x, y), text, fill=LINE_COLOR)


def _draw_crossing_structural_lines(draw: ImageDraw.ImageDraw, x: int, y: int, size: int) -> None:
    """Thick crossing lines simulating a wall corner/structural outline --
    real lines, but not a periodic hatch (only 2 lines, far below R4's
    MIN_ANGLE_EVIDENCE_PX in a tile-sized region), a distinct distractor
    from the dedicated hatch distractor regions below."""
    draw.line([(x, y), (x + size, y)], fill=LINE_COLOR, width=4)
    draw.line([(x, y), (x, y + size)], fill=LINE_COLOR, width=4)


def build_single_target_page() -> tuple[np.ndarray, list[tuple[float, float, float, float]]]:
    """One clean target hatch region (family A, 45deg, 10px spacing --
    the same pattern used as the "reference" in benchmark tests), fully
    surrounded by blank page. The simplest possible ground-truth case."""
    page = _blank_page()
    target = hfx._pil_to_bgr(hfx._draw_parallel_lines(200, angle_deg=45, spacing=10))
    target_img = Image.fromarray(target[:, :, ::-1])  # back to RGB for pasting
    x, y = 350, 250
    _paste_pattern(page, target_img, x, y)
    boxes = [_to_normalized_box(x, y, 200, 200, PAGE_SIZE)]
    return hfx._pil_to_bgr(page), boxes


def build_multi_target_page() -> tuple[np.ndarray, list[tuple[float, float, float, float]]]:
    """Three separated instances of the same target pattern -- tests that
    detection finds ALL of them, not just the first."""
    page = _blank_page()
    boxes = []
    for x, y in ((80, 80), (500, 120), (250, 450)):
        target = hfx._pil_to_bgr(hfx._draw_parallel_lines(150, angle_deg=45, spacing=10))
        target_img = Image.fromarray(target[:, :, ::-1])
        _paste_pattern(page, target_img, x, y)
        boxes.append(_to_normalized_box(x, y, 150, 150, PAGE_SIZE))
    return hfx._pil_to_bgr(page), boxes


def build_partial_boundary_page() -> tuple[np.ndarray, list[tuple[float, float, float, float]]]:
    """A target region straddling the page edge, half cut off -- a
    realistic case (a wall that continues past the visible plan
    boundary), and a genuinely harder detection case than a fully-visible
    target."""
    page = _blank_page()
    target = hfx._pil_to_bgr(hfx._draw_parallel_lines(200, angle_deg=45, spacing=10))
    target_img = Image.fromarray(target[:, :, ::-1])
    x, y = PAGE_SIZE[0] - 100, 300  # only the left half of the 200px pattern is on-page
    _paste_pattern(page, target_img, x, y)
    visible_width = PAGE_SIZE[0] - x
    boxes = [_to_normalized_box(x, y, visible_width, 200, PAGE_SIZE)]
    return hfx._pil_to_bgr(page), boxes


def build_target_with_distractors_page() -> tuple[np.ndarray, list[tuple[float, float, float, float]]]:
    """One target region plus multiple distractor hatch regions (a
    different family -- dense cross-hatch, and a different angle family)
    that must NOT be reported as candidates."""
    page = _blank_page()
    target = hfx._pil_to_bgr(hfx._draw_parallel_lines(180, angle_deg=45, spacing=10))
    target_img = Image.fromarray(target[:, :, ::-1])
    tx, ty = 350, 250
    _paste_pattern(page, target_img, tx, ty)
    boxes = [_to_normalized_box(tx, ty, 180, 180, PAGE_SIZE)]

    distractor_e = hfx.family_e_dense_cross_hatch(size=160)
    distractor_e_img = Image.fromarray(distractor_e[:, :, ::-1])
    _paste_pattern(page, distractor_e_img, 60, 60)

    distractor_b = hfx._pil_to_bgr(hfx._draw_parallel_lines(160, angle_deg=90, spacing=10))
    distractor_b_img = Image.fromarray(distractor_b[:, :, ::-1])
    _paste_pattern(page, distractor_b_img, 650, 480)

    return hfx._pil_to_bgr(page), boxes


def build_full_scene_page(seed: int = 0) -> tuple[np.ndarray, list[tuple[float, float, float, float]]]:
    """The "everything at once" fixture (R6 section 18's full required
    list): target regions, a distractor hatch, dimension-like lines, text
    overlays, blank areas, crossing structural lines -- exercises the
    whole gating/thresholding/merging pipeline together, not just one
    concern at a time."""
    page = _blank_page()
    draw = ImageDraw.Draw(page)
    boxes = []

    for x, y in ((60, 60), (600, 400)):
        target = hfx._pil_to_bgr(hfx._draw_parallel_lines(160, angle_deg=45, spacing=10))
        target_img = Image.fromarray(target[:, :, ::-1])
        _paste_pattern(page, target_img, x, y)
        boxes.append(_to_normalized_box(x, y, 160, 160, PAGE_SIZE))

    distractor = hfx.family_f_sparse_cross_hatch(size=150)
    distractor_img = Image.fromarray(distractor[:, :, ::-1])
    _paste_pattern(page, distractor_img, 400, 40)

    _draw_dimension_line(draw, 40, 620, 860, 620)
    _draw_dimension_line(draw, 850, 40, 850, 600)
    _draw_text_block(draw, 50, 20, "GRUNDRISS ERDGESCHOSS\nM 1:50")
    _draw_crossing_structural_lines(draw, 300, 500, 80)

    return hfx._pil_to_bgr(page), boxes


def build_blank_page() -> tuple[np.ndarray, list[tuple[float, float, float, float]]]:
    """Pure negative control -- no target, no distractor, nothing but
    background. Zero candidate regions is the only correct result."""
    page = _blank_page()
    return hfx._pil_to_bgr(page), []


def build_rotated_scaled_target_page() -> tuple[np.ndarray, list[tuple[float, float, float, float]]]:
    """The target pattern rendered at a different angle and scale than the
    reference crop -- exercises R4's own documented angle/scale
    robustness (see R4_HATCH_FEATURE_BENCHMARK.md) at detection scale, not
    just isolated-crop scale."""
    page = _blank_page()
    target = hfx._pil_to_bgr(hfx._draw_parallel_lines(220, angle_deg=50, spacing=13))
    target_img = Image.fromarray(target[:, :, ::-1]).resize((260, 260))
    x, y = 300, 200
    _paste_pattern(page, target_img, x, y)
    boxes = [_to_normalized_box(x, y, 260, 260, PAGE_SIZE)]
    return hfx._pil_to_bgr(page), boxes
