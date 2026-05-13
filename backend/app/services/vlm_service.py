from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path


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
