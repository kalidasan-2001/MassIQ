"""HatchFeatureExtractor: the one orchestration point that wires every
`hatch/` module together into a single deterministic
`extract(image) -> HatchFeatures` call (R4 section 19).

Deliberately a thin, near-pure orchestrator: every actual algorithm lives
in its own small module (angles, spacing, density, line_width,
cross_hatch, periodicity, color) so each stays independently unit-testable
(R4 section 3). This class holds no mutable state between calls -- safe to
share one instance across concurrent requests (R4 section 37) -- and never
touches the database, FastAPI, or the filesystem; `HatchFeatureService`
(backend/app/services/hatch_feature_service.py) is the only thing that
resolves a crop file and persists the result.
"""

from __future__ import annotations

from .angles import detect_line_segments, extract_dominant_angles
from .config import FEATURE_VERSION
from .color import compute_color_features
from .cross_hatch import classify_cross_hatch, dominant_angles_list
from .density import compute_density
from .line_width import estimate_line_width_px, normalize_line_width
from .models import HatchFeatures
from .periodicity import estimate_periodicity
from .preprocessing import preprocess
from .projection import rotate_to_align, row_projection
from .spacing import estimate_spacing_px, normalize_spacing


class HatchFeatureExtractor:
    """Stateless -- `extract()` never mutates `self` or any module-level
    state, so one instance is safely reusable across any number of calls,
    concurrently or otherwise."""

    def extract(self, image) -> HatchFeatures:  # image: np.ndarray (BGR or grayscale)
        pre = preprocess(image)  # raises InvalidHatchImageError for genuinely unusable input

        # Hough line detection runs exactly once; both angle extraction and
        # line-width estimation reuse the same segments (R4 section 36 --
        # avoid redundant CV work).
        segments = detect_line_segments(pre)
        angle_evidence = extract_dominant_angles(segments)
        is_cross_hatch = classify_cross_hatch(angle_evidence)
        angles = dominant_angles_list(angle_evidence, is_cross_hatch)

        normalized_spacing = None
        periodicity = None
        spacing_available = False
        periodicity_available = False
        if angle_evidence.primary_angle_deg is not None:
            rotated = rotate_to_align(pre.binary, angle_evidence.primary_angle_deg)
            projection = row_projection(rotated)
            spacing_px, _peak_count = estimate_spacing_px(projection, pre.diagonal_px)
            if spacing_px is not None:
                normalized_spacing = normalize_spacing(spacing_px, pre.diagonal_px)
                spacing_available = True
            periodicity = estimate_periodicity(projection)
            periodicity_available = periodicity is not None

        normalized_width = None
        if len(segments) > 0:
            width_px, _sample_count = estimate_line_width_px(pre.binary, segments)
            if width_px is not None:
                normalized_width = normalize_line_width(width_px, pre.diagonal_px)

        density = compute_density(pre.binary)
        color = compute_color_features(pre.original_bgr)

        angle_evidence_strength = angle_evidence.primary_evidence_px / pre.diagonal_px if pre.diagonal_px > 0 else 0.0

        return HatchFeatures(
            feature_version=FEATURE_VERSION,
            source_width=pre.width,
            source_height=pre.height,
            dominant_angles=angles,
            is_cross_hatch=is_cross_hatch,
            normalized_line_spacing=normalized_spacing,
            line_density=density,
            normalized_line_width=normalized_width,
            periodicity=periodicity,
            color_mean_l=color.mean_l,
            color_mean_a=color.mean_a,
            color_mean_b=color.mean_b,
            color_std_l=color.std_l,
            color_std_a=color.std_a,
            color_std_b=color.std_b,
            detected_line_count=angle_evidence.line_count,
            angle_evidence_strength=angle_evidence_strength,
            spacing_available=spacing_available,
            periodicity_available=periodicity_available,
        )
