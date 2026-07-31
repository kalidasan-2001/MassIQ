from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

# Denser near 1.0 (where most real-world scale drift will land), sparser at the
# extremes, to bound how many extra matchTemplate passes a request costs.
DEFAULT_SCALE_STEPS: tuple[float, ...] = (0.5, 0.7, 0.85, 1.0, 1.15, 1.35, 1.6, 2.0)
MAX_RAW_CANDIDATES_PER_SCALE = 200
MAX_TOTAL_DETECTIONS = 200


def _passes_size_quality_filter(width: int, height: int, confidence: float, min_region_size: int) -> bool:
    """Per-candidate noise gate.

    Every match from matchTemplate at a given scale shares that scale's template
    width/height, so a plain width*height comparison would be constant across
    candidates from the same scale. Weighting the area by that candidate's own
    confidence makes weak matches count as effectively smaller than strong
    matches of the same size, so the filter varies per detection regardless of
    which scale produced it.
    """
    effective_area = width * height * max(0.0, confidence)
    return effective_area >= int(min_region_size)


def _normalize_scale_steps(scale_steps) -> tuple[float, ...]:
    steps = set(float(s) for s in (scale_steps or DEFAULT_SCALE_STEPS) if s and s > 0)
    steps.add(1.0)
    return tuple(sorted(steps))


def _match_at_scale(page: np.ndarray, sample: np.ndarray, scale: float, threshold: float) -> list[dict]:
    """Runs matchTemplate at one scale, returning raw (unmerged, unfiltered) candidates."""
    sample_h, sample_w = sample.shape[:2]
    if scale == 1.0:
        scaled_sample = sample
    else:
        new_w = max(1, round(sample_w * scale))
        new_h = max(1, round(sample_h * scale))
        if new_w < 4 or new_h < 4:
            return []
        if new_h >= page.shape[0] or new_w >= page.shape[1]:
            return []
        interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
        scaled_sample = cv2.resize(sample, (new_w, new_h), interpolation=interpolation)

    result = cv2.matchTemplate(page, scaled_sample, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(result >= float(threshold))
    scaled_h, scaled_w = scaled_sample.shape[:2]

    candidates = []
    for x, y in zip(xs.tolist(), ys.tolist()):
        candidates.append(
            {
                "x": int(x),
                "y": int(y),
                "w": int(scaled_w),
                "h": int(scaled_h),
                "confidence": float(result[y, x]),
            }
        )
        if len(candidates) >= MAX_RAW_CANDIDATES_PER_SCALE:
            break
    return candidates


def _merge_detections(detections: list[dict]) -> list[dict]:
    """Merges nearby candidates, keeping the highest-confidence one per region.

    Compares center points (not top-left corners) since candidates can now carry
    different sizes across scales; the proximity threshold uses the smaller of
    the two candidates' own sizes. For same-sized boxes (the single-scale case)
    this is mathematically identical to the previous top-left/fixed-size
    comparison, so native-scale behavior is unchanged.
    """
    merged: list[dict] = []
    for det in detections:
        det_cx = det["x"] + det["w"] / 2
        det_cy = det["y"] + det["h"] / 2
        overlap = None
        for candidate in merged:
            cand_cx = candidate["x"] + candidate["w"] / 2
            cand_cy = candidate["y"] + candidate["h"] / 2
            proximity_w = min(candidate["w"], det["w"]) // 2
            proximity_h = min(candidate["h"], det["h"]) // 2
            if abs(cand_cx - det_cx) < proximity_w and abs(cand_cy - det_cy) < proximity_h:
                overlap = candidate
                break
        if overlap is None:
            merged.append(det)
        elif det["confidence"] > overlap["confidence"]:
            overlap.update(det)
    return merged


def detect_hatch_regions(
    page_image_path: str | Path,
    hatch_sample_path: str | Path,
    threshold: float = 0.7,
    min_region_size: int = 225,
    merge_nearby_detections: bool = True,
    remove_small_noise: bool = True,
    scale_steps: tuple[float, ...] | None = None,
) -> list[dict]:
    page = cv2.imread(str(page_image_path), cv2.IMREAD_GRAYSCALE)
    sample = cv2.imread(str(hatch_sample_path), cv2.IMREAD_GRAYSCALE)
    if page is None:
        raise ValueError("Page image not found")
    if sample is None:
        raise ValueError("Hatch sample image not found")
    if sample.shape[0] < 4 or sample.shape[1] < 4:
        raise ValueError("Hatch sample too small")

    scales = _normalize_scale_steps(scale_steps)

    raw_candidates: list[dict] = []
    for scale in scales:
        raw_candidates.extend(_match_at_scale(page, sample, scale, threshold))

    filtered = []
    for candidate in raw_candidates:
        if remove_small_noise and not _passes_size_quality_filter(
            candidate["w"], candidate["h"], candidate["confidence"], min_region_size
        ):
            continue
        filtered.append(candidate)

    merged = _merge_detections(filtered) if merge_nearby_detections else filtered

    merged.sort(key=lambda det: det["confidence"], reverse=True)
    merged = merged[:MAX_TOTAL_DETECTIONS]

    detections = [
        {
            "id": f"det_{index}",
            "x": det["x"],
            "y": det["y"],
            "w": det["w"],
            "h": det["h"],
            "confidence": round(det["confidence"], 4),
            "selected": True,
            "status": "accepted",
        }
        for index, det in enumerate(merged, start=1)
    ]
    return detections
