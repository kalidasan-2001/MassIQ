"""Synthetic, reproducible PDF fixtures for R2 tests -- built programmatically
with PyMuPDF (and PIL for raster content) so tests never depend on private
customer construction plans. Not a test module itself (name doesn't match
the `test_*.py` discovery pattern).

Each builder's structural properties were empirically verified against
`app.services.pdf_inspection_service` before being relied on in tests (see
docs/releases/R2_CORE_FOUNDATION_CHECKLIST.md's classification evidence):
- vector: get_drawings() > 0, image coverage 0.0
- raster: get_drawings() == 0, image coverage ~1.0 (full-bleed image)
- mixed: get_drawings() > 0 AND image coverage ~1.0
- blank/unknown: get_drawings() == 0, image coverage 0.0
"""

from __future__ import annotations

import io

import fitz
from PIL import Image, ImageDraw

PAGE_WIDTH = 595.0
PAGE_HEIGHT = 842.0


def _striped_image_bytes() -> bytes:
    img = Image.new("RGB", (800, 1131), color=(200, 200, 200))
    draw = ImageDraw.Draw(img)
    for x in range(0, 800, 20):
        draw.line([(x, 0), (x, 1131)], fill=(150, 150, 150))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def build_vector_pdf_bytes(page_count: int = 1) -> bytes:
    """Every page has real vector drawing commands (rect + line) and no
    raster images -- get_drawings() > 0, image coverage 0.0 per page."""
    doc = fitz.open()
    for i in range(page_count):
        page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        page.draw_rect(fitz.Rect(50, 50, 500 - i, 500 - i), color=(0, 0, 0), width=2)
        page.draw_line(fitz.Point(50, 50), fitz.Point(500, 500), color=(0, 0, 0), width=2)
        page.insert_text((60, 780), f"Vector construction plan - page {i + 1}", fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


def build_raster_pdf_bytes(page_count: int = 1) -> bytes:
    """Every page is a full-bleed raster image with no vector drawing
    commands -- get_drawings() == 0, image coverage ~1.0 per page."""
    image_bytes = _striped_image_bytes()
    doc = fitz.open()
    for _ in range(page_count):
        page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        page.insert_image(fitz.Rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT), stream=image_bytes)
    data = doc.tobytes()
    doc.close()
    return data


def build_mixed_pdf_bytes(page_count: int = 1) -> bytes:
    """Every page has both a full-bleed raster background AND vector
    drawing commands on top -- get_drawings() > 0 AND image coverage ~1.0."""
    image_bytes = _striped_image_bytes()
    doc = fitz.open()
    for _ in range(page_count):
        page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        page.insert_image(fitz.Rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT), stream=image_bytes)
        page.draw_rect(fitz.Rect(50, 50, 500, 500), color=(0, 0, 0), width=3)
        page.draw_line(fitz.Point(60, 60), fitz.Point(490, 490), color=(1, 0, 0), width=2)
    data = doc.tobytes()
    doc.close()
    return data


def build_multi_page_vector_pdf_bytes(page_count: int = 3) -> bytes:
    """Distinct per-page geometry (varying rotation) so page-level metadata
    can be told apart in assertions."""
    doc = fitz.open()
    for i in range(page_count):
        page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        page.draw_rect(fitz.Rect(50 + i * 5, 50, 500, 500), color=(0, 0, 0), width=2)
        page.insert_text((60, 780), f"Page {i + 1} of {page_count}", fontsize=12)
        if i == page_count - 1:
            page.set_rotation(90)
    data = doc.tobytes()
    doc.close()
    return data


def build_blank_pdf_bytes(page_count: int = 1) -> bytes:
    """No vector drawings, no images, no text -- classifies as UNKNOWN."""
    doc = fitz.open()
    for _ in range(page_count):
        doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    data = doc.tobytes()
    doc.close()
    return data


def build_corrupt_pdf_bytes() -> bytes:
    """Starts with a valid PDF header but the body is deliberately
    truncated/malformed -- PyMuPDF's fitz.open() must fail on this."""
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\ntrailer\n<< garbage, not valid xref"


def build_fake_pdf_bytes() -> bytes:
    """Plain text with no PDF header at all, renamed .pdf by the client."""
    return b"This is just a plain text file pretending to be a PDF. It is not PDF content at all."


def build_empty_pdf_bytes() -> bytes:
    return b""
