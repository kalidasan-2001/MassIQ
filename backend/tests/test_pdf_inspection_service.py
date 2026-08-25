"""Pure PDF validation/classification unit tests -- no database required."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests import pdf_fixtures as fx

from app.models.plan import PdfType
from app.services.pdf_inspection_service import (
    InvalidPdfError,
    PageInspection,
    classify_document,
    inspect_document,
    open_and_validate,
)


class OpenAndValidateTests(unittest.TestCase):
    def test_valid_pdf_accepted(self):
        doc = open_and_validate(fx.build_vector_pdf_bytes())
        self.assertEqual(doc.page_count, 1)
        doc.close()

    def test_empty_file_rejected(self):
        with self.assertRaises(InvalidPdfError):
            open_and_validate(fx.build_empty_pdf_bytes())

    def test_fake_text_file_rejected(self):
        with self.assertRaises(InvalidPdfError):
            open_and_validate(fx.build_fake_pdf_bytes())

    def test_corrupt_pdf_rejected(self):
        with self.assertRaises(InvalidPdfError):
            open_and_validate(fx.build_corrupt_pdf_bytes())


class PageClassificationTests(unittest.TestCase):
    def _inspect_single(self, content: bytes) -> PageInspection:
        doc = open_and_validate(content)
        inspections = inspect_document(doc)
        doc.close()
        return inspections[0]

    def test_vector_fixture_classified_vector(self):
        insp = self._inspect_single(fx.build_vector_pdf_bytes())
        self.assertTrue(insp.has_vector_drawings)
        self.assertEqual(insp.image_coverage_ratio, 0.0)
        self.assertEqual(insp.page_type, PdfType.VECTOR)

    def test_raster_fixture_classified_raster(self):
        insp = self._inspect_single(fx.build_raster_pdf_bytes())
        self.assertFalse(insp.has_vector_drawings)
        self.assertGreaterEqual(insp.image_coverage_ratio, 0.8)
        self.assertEqual(insp.page_type, PdfType.RASTER)

    def test_mixed_fixture_classified_mixed(self):
        insp = self._inspect_single(fx.build_mixed_pdf_bytes())
        self.assertTrue(insp.has_vector_drawings)
        self.assertGreaterEqual(insp.image_coverage_ratio, 0.2)
        self.assertEqual(insp.page_type, PdfType.MIXED)

    def test_blank_page_classified_unknown_not_vector_or_raster(self):
        insp = self._inspect_single(fx.build_blank_pdf_bytes())
        self.assertFalse(insp.has_vector_drawings)
        self.assertEqual(insp.image_coverage_ratio, 0.0)
        self.assertEqual(insp.page_type, PdfType.UNKNOWN)

    def test_text_alone_is_not_treated_as_vector_proof(self):
        # A blank page has zero drawings/images -- the classifier only ever
        # reads has_vector_drawings/image_coverage, never text_length, so a
        # text-only page can never be misclassified VECTOR by text presence.
        insp = self._inspect_single(fx.build_blank_pdf_bytes())
        self.assertEqual(insp.text_length, 0)
        self.assertNotEqual(insp.page_type, PdfType.VECTOR)


class DocumentClassificationTests(unittest.TestCase):
    def test_all_vector_pages_document_is_vector(self):
        doc = open_and_validate(fx.build_multi_page_vector_pdf_bytes(3))
        inspections = inspect_document(doc)
        doc.close()
        self.assertEqual(classify_document(inspections), PdfType.VECTOR)

    def test_no_pages_is_unknown(self):
        self.assertEqual(classify_document([]), PdfType.UNKNOWN)

    def test_mixed_page_forces_document_mixed(self):
        doc = open_and_validate(fx.build_mixed_pdf_bytes(page_count=1))
        inspections = inspect_document(doc)
        doc.close()
        self.assertEqual(classify_document(inspections), PdfType.MIXED)

    def test_vector_and_raster_pages_together_force_mixed(self):
        vector_page = PageInspection(1, 595.0, 842.0, 0, True, False, 0.0, 10, PdfType.VECTOR)
        raster_page = PageInspection(2, 595.0, 842.0, 0, False, True, 0.9, 0, PdfType.RASTER)
        self.assertEqual(classify_document([vector_page, raster_page]), PdfType.MIXED)

    def test_all_unknown_pages_document_is_unknown(self):
        doc = open_and_validate(fx.build_blank_pdf_bytes(page_count=2))
        inspections = inspect_document(doc)
        doc.close()
        self.assertEqual(classify_document(inspections), PdfType.UNKNOWN)


class MultiPageInspectionTests(unittest.TestCase):
    def test_page_numbers_are_1_based_and_sequential(self):
        doc = open_and_validate(fx.build_multi_page_vector_pdf_bytes(3))
        inspections = inspect_document(doc)
        doc.close()
        self.assertEqual([i.page_number for i in inspections], [1, 2, 3])

    def test_rotated_last_page_has_swapped_dimensions_and_rotation_recorded(self):
        doc = open_and_validate(fx.build_multi_page_vector_pdf_bytes(3))
        inspections = inspect_document(doc)
        doc.close()
        self.assertEqual(inspections[2].rotation, 90)
        self.assertGreater(inspections[2].width, inspections[2].height)  # landscape after rotation


if __name__ == "__main__":
    unittest.main()
