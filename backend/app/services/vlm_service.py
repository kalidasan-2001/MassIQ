from __future__ import annotations

import base64
import io
import json
import mimetypes
import os
from pathlib import Path

LEGEND_CROP_RIGHT_RATIO = 0.32  # crop the rightmost ~32% of the page (within the 30-35% band)
MAX_HATCH_CANDIDATES = 5


class VLMServiceError(RuntimeError):
    pass


def _image_to_data_url(image_path: str | Path) -> str:
    image_path = Path(image_path)
    if not image_path.exists():
        raise VLMServiceError(f"Image not found: {image_path}")
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _fallback_floor_plan() -> dict:
    return {
        "legend_area": {"x": 0, "y": 0, "width": 0, "height": 0},
        "component_candidates": [],
        "scale_candidates": [],
        "notes": "VLM unavailable. Continue with heuristic/manual workflow.",
    }


def _fallback_section() -> dict:
    return {
        "height_suggestions": [],
        "thickness_suggestions": [],
        "notes": "VLM unavailable. Continue with manual confirmation.",
    }


def analyze_floor_plan_with_vlm(image_path: str) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _fallback_floor_plan()
    try:
        from openai import OpenAI
    except Exception as exc:
        raise VLMServiceError(f"OpenAI SDK unavailable: {exc}") from exc

    prompt = (
        "Analyze this construction floor plan. Suggest only legend area, component candidates, "
        "and possible scale text. Never calculate final quantity, final area, or volume. "
        "Return strict JSON."
    )
    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=os.getenv("OPENAI_VLM_MODEL", "gpt-4.1-mini"),
        temperature=0,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": _image_to_data_url(image_path)},
                ],
            }
        ],
    )
    text = getattr(response, "output_text", "") or "{}"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise VLMServiceError("VLM returned invalid JSON")


def _crop_legend_region(image) -> tuple:
    width, height = image.size
    crop_x = round(width * (1 - LEGEND_CROP_RIGHT_RATIO))
    crop = image.crop((crop_x, 0, width, height))
    bbox = {"x": crop_x, "y": 0, "width": width - crop_x, "height": height}
    return crop, bbox


def _image_to_data_url_from_image(image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _empty_legend_suggestion(component_query: str, reason: str, legend_crop: dict | None = None) -> dict:
    return {
        "available": False,
        "reason": reason,
        "component_query": component_query,
        "legend_crop": legend_crop,
        "hatch_candidates": [],
        "rejected_candidates": [],
    }


def _normalize_candidate(raw: dict, crop_bbox: dict, crop_size: tuple) -> dict | None:
    """Converts a VLM candidate (bbox relative to the crop) into full-page pixel coordinates."""
    if not isinstance(raw, dict):
        return None
    raw_bbox = raw.get("bbox")
    if not isinstance(raw_bbox, dict):
        return None
    try:
        x = float(raw_bbox.get("x", 0))
        y = float(raw_bbox.get("y", 0))
        w = float(raw_bbox.get("width", 0))
        h = float(raw_bbox.get("height", 0))
    except (TypeError, ValueError):
        return None

    crop_w, crop_h = crop_size
    if w <= 0 or h <= 0 or crop_w <= 0 or crop_h <= 0:
        return None

    # Clamp to the crop bounds before translating into full-page coordinates.
    x = max(0.0, min(float(crop_w), x))
    y = max(0.0, min(float(crop_h), y))
    w = max(0.0, min(float(crop_w) - x, w))
    h = max(0.0, min(float(crop_h) - y, h))
    if w <= 0 or h <= 0:
        return None

    try:
        confidence = float(raw.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return {
        "matched_text": str(raw.get("matched_text") or "").strip(),
        "bbox": {
            "x": int(round(x + crop_bbox["x"])),
            "y": int(round(y + crop_bbox["y"])),
            "width": int(round(w)),
            "height": int(round(h)),
        },
        "confidence": round(confidence, 4),
        "reason": str(raw.get("reason") or "").strip(),
    }


def suggest_legend_hatch_candidates(image_path: str | Path, component_query: str) -> dict:
    """Crops the legend-likely region of a rendered plan and asks the VLM to locate hatch
    pattern samples for component_query. Never raises -- any failure (missing API key,
    missing image, SDK/network error, malformed response) degrades to the same valid
    empty shape so the caller can always render a friendly fallback.
    """
    component_query = str(component_query or "").strip()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _empty_legend_suggestion(
            component_query, "OPENAI_API_KEY not configured; AI suggestion unavailable."
        )

    image_path = Path(image_path)
    if not image_path.exists():
        return _empty_legend_suggestion(component_query, "Rendered plan image not found.")

    try:
        from openai import OpenAI
        from PIL import Image
    except Exception as exc:
        return _empty_legend_suggestion(component_query, f"AI suggestion unavailable: {exc}")

    try:
        with Image.open(image_path) as full_image:
            crop, crop_bbox = _crop_legend_region(full_image.convert("RGB"))
            crop_size = crop.size
            crop_data_url = _image_to_data_url_from_image(crop)
    except Exception as exc:
        return _empty_legend_suggestion(component_query, f"Could not read the rendered plan: {exc}")

    prompt = (
        "This image is a crop of the right side of a construction floor plan, likely containing "
        "the legend or title block. Find hatch pattern samples and the component labels next to them. "
        f'The component being searched for is: "{component_query}". '
        "For each hatch pattern you can identify, report its bounding box in PIXELS relative to THIS "
        f"cropped image, which is {crop_size[0]}x{crop_size[1]} pixels (top-left origin). "
        "Return strict JSON with this exact shape: "
        '{"hatch_candidates": [{"matched_text": string, "bbox": {"x": number, "y": number, '
        '"width": number, "height": number}, "confidence": number between 0 and 1, "reason": string}], '
        '"rejected_candidates": [ ...same shape... ]}. '
        "Put hatch patterns that clearly match the requested component in hatch_candidates, ranked by "
        f"confidence, highest first, at most {MAX_HATCH_CANDIDATES} entries. Put hatch patterns for other "
        "components you noticed but that do not match the requested component in rejected_candidates. "
        "Never mention or transcribe scale text (e.g. 1:100). Never calculate area, volume, or quantity. "
        "If you cannot find any matching hatch pattern, return empty arrays for both fields."
    )

    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=os.getenv("OPENAI_VLM_MODEL", "gpt-4.1-mini"),
            temperature=0,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": crop_data_url},
                    ],
                }
            ],
        )
        text = getattr(response, "output_text", "") or "{}"
        parsed = json.loads(text)
    except Exception as exc:
        return _empty_legend_suggestion(component_query, f"AI request failed: {exc}", legend_crop=crop_bbox)

    if not isinstance(parsed, dict):
        return _empty_legend_suggestion(
            component_query, "AI returned an unexpected response shape.", legend_crop=crop_bbox
        )

    raw_candidates = parsed.get("hatch_candidates")
    raw_rejected = parsed.get("rejected_candidates")
    raw_candidates = raw_candidates if isinstance(raw_candidates, list) else []
    raw_rejected = raw_rejected if isinstance(raw_rejected, list) else []

    hatch_candidates = [
        candidate
        for raw in raw_candidates[:MAX_HATCH_CANDIDATES]
        if (candidate := _normalize_candidate(raw, crop_bbox, crop_size))
    ]
    rejected_candidates = [
        candidate
        for raw in raw_rejected[:MAX_HATCH_CANDIDATES]
        if (candidate := _normalize_candidate(raw, crop_bbox, crop_size))
    ]
    hatch_candidates.sort(key=lambda item: item["confidence"], reverse=True)

    if not hatch_candidates:
        return {
            "available": True,
            "reason": f'No hatch pattern candidates found for "{component_query}" in the legend crop.',
            "component_query": component_query,
            "legend_crop": crop_bbox,
            "hatch_candidates": [],
            "rejected_candidates": rejected_candidates,
        }

    return {
        "available": True,
        "reason": "",
        "component_query": component_query,
        "legend_crop": crop_bbox,
        "hatch_candidates": hatch_candidates,
        "rejected_candidates": rejected_candidates,
    }


def analyze_section_with_vlm(image_path: str, component_name: str) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _fallback_section()
    try:
        from openai import OpenAI
    except Exception as exc:
        raise VLMServiceError(f"OpenAI SDK unavailable: {exc}") from exc

    prompt = (
        f"Analyze this section drawing for component {component_name}. "
        "Suggest possible height or thickness values only. Return strict JSON."
    )
    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=os.getenv("OPENAI_VLM_MODEL", "gpt-4.1-mini"),
        temperature=0,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": _image_to_data_url(image_path)},
                ],
            }
        ],
    )
    text = getattr(response, "output_text", "") or "{}"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise VLMServiceError("VLM returned invalid JSON")
