"""R2.5 hardening tests for the legacy `/upload-pdf` route.

Scope: prove `main.py::upload_pdf` now rejects invalid content with a clean
4xx (reusing `PdfInspectionService.open_and_validate` -- no second validation
implementation), leaves no orphan uploads/rendered-page file behind on a
rejected upload, and that a genuinely valid PDF upload still behaves exactly
as before (no regression on the happy path this app's own frontend depends
on). Uses the same synthetic byte builders `test_pdf_inspection_service.py`
already relies on (`tests/pdf_fixtures.py`) -- not a second fixture set.

No DB involved: `/upload-pdf` is filesystem-only, so this does not need the
`db_test_support` Postgres harness the R1/R2 route tests use.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests import pdf_fixtures as fx

from app.main import RENDERED_DIR, UPLOADS_DIR, app


def _file_counts() -> tuple[int, int]:
    return (
        len(list(UPLOADS_DIR.glob("*.pdf"))),
        len(list(RENDERED_DIR.glob("*.png"))),
    )


class LegacyUploadPdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_valid_pdf_upload_still_succeeds(self):
        """Happy-path regression: a real PDF must still upload and render
        exactly as before this hardening change (response shape unchanged)."""
        before_uploads, before_rendered = _file_counts()
        response = self.client.post(
            "/upload-pdf",
            files={"file": ("plan.pdf", fx.build_vector_pdf_bytes(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("file_id", body)
        self.assertIn("page_image_url", body)
        self.assertIn("width", body)
        self.assertIn("height", body)

        # The rendered page must actually be servable afterward -- proves
        # the happy path still writes both files, not just returns 200.
        page_response = self.client.get(body["page_image_url"])
        self.assertEqual(page_response.status_code, 200)

        after_uploads, after_rendered = _file_counts()
        self.assertEqual(after_uploads, before_uploads + 1)
        self.assertEqual(after_rendered, before_rendered + 1)

    def test_empty_file_returns_400_not_500(self):
        before = _file_counts()
        response = self.client.post(
            "/upload-pdf",
            files={"file": ("empty.pdf", fx.build_empty_pdf_bytes(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("Traceback", response.text)
        self.assertEqual(_file_counts(), before, "a rejected upload must leave no orphan files")

    def test_fake_text_file_renamed_pdf_returns_400_not_500(self):
        before = _file_counts()
        response = self.client.post(
            "/upload-pdf",
            files={"file": ("notes.pdf", fx.build_fake_pdf_bytes(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("Traceback", response.text)
        self.assertEqual(_file_counts(), before, "a rejected upload must leave no orphan files")

    def test_corrupt_pdf_returns_400_not_500(self):
        before = _file_counts()
        response = self.client.post(
            "/upload-pdf",
            files={"file": ("broken.pdf", fx.build_corrupt_pdf_bytes(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("Traceback", response.text)
        self.assertEqual(_file_counts(), before, "a rejected upload must leave no orphan files")

    def test_non_pdf_extension_still_rejected_before_touching_content(self):
        """Pre-existing filename-extension check must remain intact --
        this hardening change is additive, not a replacement."""
        before = _file_counts()
        response = self.client.post(
            "/upload-pdf",
            files={"file": ("plan.txt", fx.build_vector_pdf_bytes(), "text/plain")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(_file_counts(), before)


if __name__ == "__main__":
    unittest.main()
