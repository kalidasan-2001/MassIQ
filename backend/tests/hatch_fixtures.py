"""Synthetic, reproducible hatch-pattern image fixtures for R4 tests --
same spirit as pdf_fixtures.py: built programmatically so tests never
depend on private customer crops, and so the exact geometry (angle,
spacing) generated is always known ground truth to compare extracted
features against.

Family builders (R4 section 24's required minimum set):
  A. parallel 45-degree lines
  B. parallel 90-degree (vertical) lines
  C. parallel lines, different spacing
  D. cross hatch 45/135
  E. dense cross hatch
  F. sparse cross hatch
  G. dotted/noisy non-hatch control
  H. irregular line control

Variant generators (R4 section 25): scale, rotation, blur, noise,
brightness, line interruption, an overlay crossing line, and crop-offset.

All functions are deterministic given their arguments (noise/dot
generators take an explicit `seed`) and return BGR uint8 numpy arrays,
matching what cv2.imread/imdecode would produce for a real crop file.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

CANVAS_SIZE = 200
LINE_COLOR = (0, 0, 0)
BG_COLOR = (255, 255, 255)


def _pil_to_bgr(image: Image.Image) -> np.ndarray:
    return np.array(image.convert("RGB"))[:, :, ::-1].copy()


def _draw_parallel_lines(
    size: int, angle_deg: float, spacing: float, line_width: int = 2, color=LINE_COLOR, bg=BG_COLOR
) -> Image.Image:
    """Draws vertical lines at `spacing` px apart on an oversized canvas,
    then rotates and center-crops back to `size` -- exact angle and
    spacing by construction, regardless of trigonometry rounding, since
    PIL's rotation is doing the geometric work.

    `angle_deg` is defined to directly match app.hatch's own orientation
    convention (angle from horizontal, via atan2(dy, dx) on an image with
    y increasing downward -- see normalization.py): passing angle_deg=45
    here produces lines the extractor itself reports as ~45 degrees.
    Since this function starts from *vertical* (90-degree) lines, that
    means rotating by (90 - angle_deg), not angle_deg directly -- PIL's
    rotate() is counter-clockwise for positive angles in a coordinate
    system that otherwise matches this project's y-down image convention.
    This offset was verified empirically against app.hatch.feature_extractor
    during R4 implementation, not assumed from theory alone.
    """
    oversized = int(size * 1.8) + 20
    canvas = Image.new("RGB", (oversized, oversized), color=bg)
    draw = ImageDraw.Draw(canvas)
    x = 0.0
    while x < oversized:
        draw.line([(x, 0), (x, oversized)], fill=color, width=line_width)
        x += spacing
    rotated = canvas.rotate(90 - angle_deg, resample=Image.BICUBIC, fillcolor=bg)
    left = (oversized - size) // 2
    return rotated.crop((left, left, left + size, left + size))


def _combine_min(a: Image.Image, b: Image.Image) -> Image.Image:
    """Combines two line images by keeping the darkest pixel at each
    position -- correct for "ink on white paper" compositing where 0=ink,
    255=background: min() keeps whichever image drew ink at that pixel."""
    arr_a = np.array(a.convert("RGB")).astype(np.int16)
    arr_b = np.array(b.convert("RGB")).astype(np.int16)
    combined = np.minimum(arr_a, arr_b).astype(np.uint8)
    return Image.fromarray(combined, mode="RGB")


# -- Family builders -----------------------------------------------------


def family_a_parallel_45(size: int = CANVAS_SIZE) -> np.ndarray:
    return _pil_to_bgr(_draw_parallel_lines(size, angle_deg=45, spacing=10))


def family_b_parallel_90(size: int = CANVAS_SIZE) -> np.ndarray:
    return _pil_to_bgr(_draw_parallel_lines(size, angle_deg=90, spacing=10))


def family_c_parallel_wide_spacing(size: int = CANVAS_SIZE) -> np.ndarray:
    return _pil_to_bgr(_draw_parallel_lines(size, angle_deg=45, spacing=20))


def family_d_cross_hatch_45_135(size: int = CANVAS_SIZE) -> np.ndarray:
    a = _draw_parallel_lines(size, angle_deg=45, spacing=14)
    b = _draw_parallel_lines(size, angle_deg=135, spacing=14)
    return _pil_to_bgr(_combine_min(a, b))


def family_e_dense_cross_hatch(size: int = CANVAS_SIZE) -> np.ndarray:
    a = _draw_parallel_lines(size, angle_deg=45, spacing=6, line_width=2)
    b = _draw_parallel_lines(size, angle_deg=135, spacing=6, line_width=2)
    return _pil_to_bgr(_combine_min(a, b))


def family_f_sparse_cross_hatch(size: int = CANVAS_SIZE) -> np.ndarray:
    a = _draw_parallel_lines(size, angle_deg=45, spacing=30, line_width=1)
    b = _draw_parallel_lines(size, angle_deg=135, spacing=30, line_width=1)
    return _pil_to_bgr(_combine_min(a, b))


def family_g_dotted_noise(size: int = CANVAS_SIZE, seed: int = 0) -> np.ndarray:
    """Random dots, not lines at all -- a non-hatch control. Should
    produce little to no reliable angle evidence."""
    rng = np.random.default_rng(seed)
    canvas = Image.new("RGB", (size, size), color=BG_COLOR)
    draw = ImageDraw.Draw(canvas)
    for _ in range(250):
        x, y = rng.integers(0, size, size=2)
        r = rng.integers(1, 3)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=LINE_COLOR)
    return _pil_to_bgr(canvas)


def family_h_irregular_lines(size: int = CANVAS_SIZE, seed: int = 0) -> np.ndarray:
    """Lines at random, uncorrelated angles and positions -- a control for
    "not a real periodic hatch" that still contains real line segments
    (unlike the dotted control), so it should still exercise Hough
    detection but fail the periodicity/cross-hatch dominance criteria."""
    rng = np.random.default_rng(seed)
    canvas = Image.new("RGB", (size, size), color=BG_COLOR)
    draw = ImageDraw.Draw(canvas)
    for _ in range(12):
        x1, y1, x2, y2 = rng.integers(0, size, size=4)
        draw.line([(x1, y1), (x2, y2)], fill=LINE_COLOR, width=2)
    return _pil_to_bgr(canvas)


# -- Variant generators (R4 section 25) ------------------------------------


def variant_scale(image: np.ndarray, factor: float) -> np.ndarray:
    import cv2

    height, width = image.shape[:2]
    new_size = (max(1, int(width * factor)), max(1, int(height * factor)))
    return cv2.resize(image, new_size, interpolation=cv2.INTER_LINEAR)


def variant_rotate(image: np.ndarray, degrees: float) -> np.ndarray:
    import cv2

    height, width = image.shape[:2]
    center = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(center, degrees, 1.0)
    return cv2.warpAffine(image, matrix, (width, height), borderValue=BG_COLOR, flags=cv2.INTER_LINEAR)


def variant_blur(image: np.ndarray, ksize: int = 3) -> np.ndarray:
    import cv2

    ksize = ksize if ksize % 2 == 1 else ksize + 1
    return cv2.GaussianBlur(image, (ksize, ksize), 0)


def variant_noise(image: np.ndarray, sigma: float = 10.0, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, sigma, image.shape)
    noisy = image.astype(np.float64) + noise
    return np.clip(noisy, 0, 255).astype(np.uint8)


def variant_brightness(image: np.ndarray, delta: int = 30) -> np.ndarray:
    shifted = image.astype(np.int16) + delta
    return np.clip(shifted, 0, 255).astype(np.uint8)


def variant_line_interruption(image: np.ndarray, seed: int = 0, patch_count: int = 6, patch_size: int = 6) -> np.ndarray:
    """Erases several small random patches back to background -- simulates
    a scan/render gap interrupting individual hatch lines."""
    rng = np.random.default_rng(seed)
    result = image.copy()
    height, width = image.shape[:2]
    for _ in range(patch_count):
        x = rng.integers(0, max(1, width - patch_size))
        y = rng.integers(0, max(1, height - patch_size))
        result[y : y + patch_size, x : x + patch_size] = BG_COLOR[::-1]  # BGR
    return result


def variant_overlay_crossing_line(image: np.ndarray) -> np.ndarray:
    import cv2

    result = image.copy()
    height, width = image.shape[:2]
    cv2.line(result, (0, 0), (width - 1, height - 1), (0, 0, 255), thickness=3)
    return result


def variant_crop_offset(image: np.ndarray, dx: int = 5, dy: int = 5) -> np.ndarray:
    height, width = image.shape[:2]
    canvas = np.full_like(image, 255)
    src_x0, src_y0 = max(0, -dx), max(0, -dy)
    dst_x0, dst_y0 = max(0, dx), max(0, dy)
    copy_w = width - abs(dx)
    copy_h = height - abs(dy)
    if copy_w <= 0 or copy_h <= 0:
        return canvas
    canvas[dst_y0 : dst_y0 + copy_h, dst_x0 : dst_x0 + copy_w] = image[
        src_y0 : src_y0 + copy_h, src_x0 : src_x0 + copy_w
    ]
    return canvas
