"""Deterministic preprocessing pipeline: raw crop -> the derived images
every other `hatch/` module works from.

Stages and why each exists (R4 section 8 requires this be documented, not
just chained blindly):

1. **Validate** -- reject an empty/zero-size/too-tiny image early with a
   controlled domain error, before any OpenCV call that would otherwise
   raise its own opaque exception.
2. **Grayscale** -- angle/spacing/density/line-width all reason about line
   *structure*, not color; color is analyzed separately, from the
   original BGR image (see color.py), specifically so binarizing for
   structure never destroys the color signal.
3. **Light denoise** (small Gaussian blur) -- absorbs single-pixel
   scan/compression noise before edge detection. Deliberately small (see
   config.DENOISE_KERNEL_SIZE) -- hatch lines are themselves only a few
   pixels wide, so anything more aggressive would blur separate lines
   together and corrupt spacing/line-width estimation downstream.
4. **Contrast normalization** -- stretches the grayscale range to [0,255]
   before thresholding, so a crop rendered slightly lighter/darker (a
   different render pass, a different screen capture) doesn't shift
   Otsu's threshold point unpredictably.
5. **Binarization** (Otsu global threshold) -- hatch pattern crops are
   overwhelmingly bimodal (ink vs. paper/background), which is exactly
   the case Otsu's method is designed for, and it is fully deterministic
   (no tunable threshold to drift). Adaptive thresholding was considered
   and deliberately not used: it adds a block-size parameter with no
   evidence it is needed for these crops, and risks fragmenting long
   hatch lines under locally-varying illumination that vector-rendered
   PDF previews don't actually exhibit.
6. **Morphology -- deliberately skipped.** Closing small gaps was
   considered (R4 section 8 lists it as optional), but for the hatch
   spacings this engine targets, a closing operation large enough to
   bridge real scan gaps would also risk merging adjacent parallel lines
   at tight spacing, corrupting the exact measurement (spacing) morphology
   would be introduced to help. Revisit only with real evidence a specific
   crop family needs it.
7. **Edge extraction** (Canny) -- the input Hough line detection (angles.py)
   actually operates on.

All threshold values used here are named constants in `hatch/config.py`,
never inline literals.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .config import CANNY_HIGH_THRESHOLD, CANNY_LOW_THRESHOLD, DENOISE_KERNEL_SIZE, MIN_IMAGE_DIMENSION_PX


class InvalidHatchImageError(ValueError):
    """Raised for input that cannot be treated as a hatch pattern crop at
    all (empty, zero-size, undecodable, below the minimum usable
    dimension). Distinct from "valid but low-evidence" images, which
    still produce a HatchFeatures result -- just with missing/None fields
    -- rather than raising."""


@dataclass(frozen=True)
class PreprocessedImage:
    original_bgr: np.ndarray
    gray: np.ndarray
    binary: np.ndarray
    edges: np.ndarray
    width: int
    height: int

    @property
    def diagonal_px(self) -> float:
        """The ORIGINAL (pre-rotation) crop's diagonal length -- the
        resolution-independent reference length every normalized spatial
        feature (spacing, line width) is divided by. Using the diagonal
        rather than width or height alone keeps the normalization stable
        regardless of the crop's aspect ratio or which way a hatch happens
        to run."""
        return float(np.hypot(self.width, self.height))


def validate_image(image: np.ndarray | None) -> None:
    if image is None:
        raise InvalidHatchImageError("Image could not be decoded")
    if not isinstance(image, np.ndarray) or image.size == 0:
        raise InvalidHatchImageError("Image is empty")
    if image.ndim < 2:
        raise InvalidHatchImageError("Image has no spatial dimensions")
    height, width = image.shape[:2]
    if width < MIN_IMAGE_DIMENSION_PX or height < MIN_IMAGE_DIMENSION_PX:
        raise InvalidHatchImageError(
            f"Image is too small to analyze ({width}x{height}px, minimum {MIN_IMAGE_DIMENSION_PX}px per side)"
        )


def preprocess(image: np.ndarray) -> PreprocessedImage:
    """Runs the full deterministic pipeline described in this module's
    docstring. Raises InvalidHatchImageError only for genuinely unusable
    input -- a valid but blank/all-white/all-black image passes through
    fine and simply yields low-evidence features downstream."""
    validate_image(image)

    if image.ndim == 3 and image.shape[2] >= 3:
        original_bgr = image[:, :, :3].copy()
        gray = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2GRAY)
    else:
        gray = image if image.ndim == 2 else image[:, :, 0]
        original_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    height, width = gray.shape[:2]

    denoised = cv2.GaussianBlur(gray, (DENOISE_KERNEL_SIZE, DENOISE_KERNEL_SIZE), 0)
    normalized = cv2.normalize(denoised, None, 0, 255, cv2.NORM_MINMAX)
    _, binary = cv2.threshold(normalized, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    edges = cv2.Canny(normalized, CANNY_LOW_THRESHOLD, CANNY_HIGH_THRESHOLD)

    return PreprocessedImage(
        original_bgr=original_bgr,
        gray=normalized,
        binary=binary,
        edges=edges,
        width=width,
        height=height,
    )
