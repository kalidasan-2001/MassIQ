from __future__ import annotations

from dataclasses import dataclass

import fitz

from app.models.plan import PdfType

# Classification thresholds -- named and documented here rather than in
# Settings, because they are specific to this one classification algorithm
# (not deployment configuration that varies per environment). Empirically
# grounded against BOTH synthetic fixtures AND one real scanned construction
# floor plan (see docs/releases/R2_CORE_FOUNDATION_CHECKLIST.md's
# classification evidence): a full-bleed synthetic scanned page's embedded
# image covers ~100% of the page area with zero vector drawing commands, but
# a real scanned sheet with ordinary print margins/title-block whitespace
# only covered ~58% -- an 0.8 threshold (the original value) misclassified
# that real page as UNKNOWN. RASTER_IMAGE_COVERAGE_THRESHOLD was lowered to
# 0.5 specifically because of that real-PDF finding: a page with zero vector
# drawings and one image covering the visual majority of the page is a scan,
# margins and all. The two thresholds below are deliberately not 0%/100% so
# a page with a small logo image alongside vector geometry still counts as
# VECTOR (not MIXED), and a scanned page with a tiny stray vector annotation
# still counts as RASTER (not MIXED) only if it also lacks any drawings at
# all -- see _classify_page's exact rule ordering.
RASTER_IMAGE_COVERAGE_THRESHOLD = 0.5
MIXED_IMAGE_COVERAGE_THRESHOLD = 0.2


class InvalidPdfError(ValueError):
    """Raised when uploaded bytes cannot be treated as a valid, readable
    PDF. Callers (PlanService/routes) must map this to a 4xx response --
    it must never surface as an unhandled 500 with a raw traceback."""


@dataclass(frozen=True)
class PageInspection:
    page_number: int  # 1-based -- see PlanPage's docstring for the convention
    width: float
    height: float
    rotation: int
    has_vector_drawings: bool
    has_raster_images: bool
    image_coverage_ratio: float
    text_length: int
    page_type: PdfType


def open_and_validate(content: bytes) -> fitz.Document:
    """Proves the uploaded bytes are a real, readable PDF -- not just
    validation by file extension. Raises InvalidPdfError (never lets a raw
    PyMuPDF exception escape) for: empty content, content that doesn't even
    start with a PDF header, content PyMuPDF cannot parse at all, a
    zero-page document, or a document whose first page cannot be loaded.
    """
    if not content:
        raise InvalidPdfError("Uploaded file is empty")
    if not content.lstrip()[:5].startswith(b"%PDF-"):
        raise InvalidPdfError("File does not start with a PDF header (%PDF-)")
    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises its own exception hierarchy for malformed streams
        raise InvalidPdfError(f"File could not be opened as a PDF: {exc}") from exc
    if doc.page_count == 0:
        doc.close()
        raise InvalidPdfError("PDF has no pages")
    try:
        doc.load_page(0)
    except Exception as exc:
        doc.close()
        raise InvalidPdfError(f"PDF's first page could not be read: {exc}") from exc
    return doc


def _page_image_coverage(page: fitz.Page) -> float:
    page_area = page.rect.width * page.rect.height
    if page_area <= 0:
        return 0.0
    try:
        image_infos = page.get_image_info()
    except Exception:
        return 0.0
    covered = 0.0
    for info in image_infos:
        bbox = info.get("bbox")
        if not bbox:
            continue
        x0, y0, x1, y1 = bbox
        covered += max(0.0, x1 - x0) * max(0.0, y1 - y0)
    return min(1.0, covered / page_area)


def _classify_page(has_vector: bool, image_coverage: float) -> PdfType:
    """Explicit, structural per-page classification -- deliberately NOT
    'text exists => VECTOR' (PDF text alone proves nothing about whether the
    construction geometry itself is vector) and NOT 'image exists => RASTER'
    (a page can have both real vector geometry and a raster background/
    photo, which is MIXED, not RASTER).

    - RASTER: no vector drawing commands, and raster images cover most of
      the page (a typical scanned page).
    - MIXED: has vector drawing commands AND non-trivial raster image
      coverage (drawn/annotated geometry over or alongside a raster image).
    - VECTOR: has vector drawing commands and no significant raster
      coverage.
    - UNKNOWN: neither vector drawings nor significant raster coverage is
      present (e.g. a blank page, or a page whose only content is text).
    """
    if has_vector and image_coverage >= MIXED_IMAGE_COVERAGE_THRESHOLD:
        return PdfType.MIXED
    if has_vector:
        return PdfType.VECTOR
    if image_coverage >= RASTER_IMAGE_COVERAGE_THRESHOLD:
        return PdfType.RASTER
    return PdfType.UNKNOWN


def inspect_document(doc: fitz.Document) -> list[PageInspection]:
    """Inspects every page (not just page 0, unlike the old MVP's renderer)."""
    inspections: list[PageInspection] = []
    for index in range(doc.page_count):
        page = doc.load_page(index)
        drawings = page.get_drawings()
        has_vector = len(drawings) > 0
        image_coverage = _page_image_coverage(page)
        has_images = image_coverage > 0.0
        text_length = len(page.get_text("text").strip())
        page_type = _classify_page(has_vector, image_coverage)
        rect = page.rect  # rotation-adjusted logical page rect
        inspections.append(
            PageInspection(
                page_number=index + 1,
                width=rect.width,
                height=rect.height,
                rotation=page.rotation,
                has_vector_drawings=has_vector,
                has_raster_images=has_images,
                image_coverage_ratio=round(image_coverage, 4),
                text_length=text_length,
                page_type=page_type,
            )
        )
    return inspections


def classify_document(page_inspections: list[PageInspection]) -> PdfType:
    """Aggregates per-page classifications into one document-level PdfType:

    - no pages, or every page UNKNOWN -> UNKNOWN
    - any MIXED page, or both VECTOR and RASTER pages present -> MIXED
    - otherwise, the single remaining classification shared by all
      non-UNKNOWN pages (all VECTOR -> VECTOR, all RASTER -> RASTER).
    """
    known = [p.page_type for p in page_inspections if p.page_type != PdfType.UNKNOWN]
    if not known:
        return PdfType.UNKNOWN
    distinct = set(known)
    if PdfType.MIXED in distinct or (PdfType.VECTOR in distinct and PdfType.RASTER in distinct):
        return PdfType.MIXED
    return next(iter(distinct))
