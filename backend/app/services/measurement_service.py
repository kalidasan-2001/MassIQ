from __future__ import annotations

import re
from pathlib import Path


def extract_height_suggestions(text: str) -> list[dict]:
    suggestions = []
    for index, match in enumerate(re.finditer(r"(\d+(?:[.,]\d+)?)\s*(m|cm|mm)\b", text, re.IGNORECASE), start=1):
        raw_value = match.group(1).replace(",", ".")
        unit = match.group(2).lower()
        value = float(raw_value)
        if unit == "cm":
            value = value / 100.0
        elif unit == "mm":
            value = value / 1000.0
        if value <= 0:
            continue
        suggestions.append(
            {
                "id": f"height_{index}",
                "value_m": round(value, 3),
                "source_text": match.group(0),
                "bbox": {"x": 0, "y": 0, "width": 0, "height": 0},
                "type": "likely_height",
                "confidence": 0.35,
                "reason": "Recovered from text pattern matching",
            }
        )
    return suggestions


def analyze_section_dimensions(section_image_path: str | Path) -> dict:
    section_image_path = Path(section_image_path)
    text_hint = section_image_path.stem.replace("_", " ")
    return {
        "height_suggestions": extract_height_suggestions(text_hint),
        "thickness_suggestions": [],
        "notes": "Heuristic section analysis placeholder",
    }
