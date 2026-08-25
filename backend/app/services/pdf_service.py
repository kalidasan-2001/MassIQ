from __future__ import annotations

import io
import re
from pathlib import Path

import fitz
from PIL import Image


def _resize_if_needed(image: Image.Image, max_width: int = 1800) -> Image.Image:
    if image.width <= max_width:
        return image
    ratio = max_width / float(image.width)
    return image.resize((int(image.width * ratio), int(image.height * ratio)), Image.Resampling.LANCZOS)


def convert_pdf_first_page_to_png(pdf_path: str | Path, output_path: str | Path, max_width: int = 1800) -> dict:
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    with fitz.open(pdf_path) as doc:
        if doc.page_count == 0:
            raise ValueError("PDF has no pages")
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        image = _resize_if_needed(image, max_width=max_width)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, format="PNG")
        return {"width": image.width, "height": image.height, "page_count": doc.page_count}


def render_page_to_png_bytes(doc: fitz.Document, page_index: int, dpi: int, max_width: int) -> bytes:
    """R2 multi-page renderer -- renders any single page (0-based index, as
    PyMuPDF itself indexes) of an already-open document to PNG bytes.

    Reuses `_resize_if_needed` so preview quality/sizing matches the old
    `convert_pdf_first_page_to_png` behavior, but takes `dpi`/`max_width`
    explicitly (from Settings) rather than hardcoding them, and does not
    touch `convert_pdf_first_page_to_png` itself -- that function keeps
    rendering page 0 only, unchanged, for the old /upload-pdf workflow.
    """
    page = doc.load_page(page_index)
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    image = _resize_if_needed(image, max_width=max_width)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def suggest_plan_scale(image_path: str | Path) -> dict:
    image_path = Path(image_path)
    filename_hint = image_path.stem
    match = re.search(r"1[: ](\d{2,4})", filename_hint)
    if not match:
        return {"detected": False, "scale_text": None, "pixels_per_meter": None}
    denominator = int(match.group(1))
    return {
        "detected": True,
        "scale_text": f"1:{denominator}",
        "scale_denominator": denominator,
        "pixels_per_meter": None,
    }
