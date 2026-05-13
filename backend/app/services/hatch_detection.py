from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def detect_hatch_regions(
    page_image_path: str | Path,
    hatch_sample_path: str | Path,
    threshold: float = 0.7,
    min_region_size: int = 225,
    merge_nearby_detections: bool = True,
    remove_small_noise: bool = True,
) -> list[dict]:
    page = cv2.imread(str(page_image_path), cv2.IMREAD_GRAYSCALE)
    sample = cv2.imread(str(hatch_sample_path), cv2.IMREAD_GRAYSCALE)
    if page is None:
        raise ValueError("Page image not found")
    if sample is None:
        raise ValueError("Hatch sample image not found")
    if sample.shape[0] < 4 or sample.shape[1] < 4:
        raise ValueError("Hatch sample too small")

    result = cv2.matchTemplate(page, sample, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(result >= float(threshold))
    detections = []
    sample_h, sample_w = sample.shape[:2]

    for index, (x, y) in enumerate(zip(xs.tolist(), ys.tolist()), start=1):
        area = sample_w * sample_h
        if remove_small_noise and area < int(min_region_size):
            continue
        detections.append(
            {
                "id": f"det_{index}",
                "x": int(x),
                "y": int(y),
                "w": int(sample_w),
                "h": int(sample_h),
                "confidence": round(float(result[y, x]), 4),
                "selected": True,
                "status": "accepted",
            }
        )
        if len(detections) >= 200:
            break

    if not merge_nearby_detections:
        return detections

    merged = []
    for det in detections:
        overlap = None
        for candidate in merged:
            if abs(candidate["x"] - det["x"]) < sample_w // 2 and abs(candidate["y"] - det["y"]) < sample_h // 2:
                overlap = candidate
                break
        if overlap is None:
            merged.append(det)
        elif det["confidence"] > overlap["confidence"]:
            overlap.update(det)
    return merged
