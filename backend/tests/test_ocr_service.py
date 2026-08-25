"""R3: OcrService tests. Fast, deterministic cases use a fake provider;
one test exercises the real RapidOcrProvider end-to-end (mirrors
test_pdf_inspection_service.py's mix of synthetic + one grounded-in-reality
check) -- proving OCR actually works in this environment, not just that
the module imports.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.ocr_service import OcrResult, OcrService, RapidOcrProvider


class _FakeSuccessProvider:
    name = "fake-success"

    def extract_text(self, image_path):
        return OcrResult(text="Stahlbeton C25/30", provider=self.name, confidence=0.95)


class _FakeEmptyProvider:
    name = "fake-empty"

    def extract_text(self, image_path):
        return OcrResult(text="", provider=self.name, confidence=None)


class _FakeExplodingProvider:
    name = "fake-exploding"

    def extract_text(self, image_path):
        raise RuntimeError("model weights corrupted")


class OcrServiceFakeProviderTests(unittest.TestCase):
    def test_success_returns_text_and_confidence(self):
        service = OcrService(provider=_FakeSuccessProvider())
        result = service.extract_text(Path("irrelevant.png"))
        self.assertEqual(result.text, "Stahlbeton C25/30")
        self.assertEqual(result.provider, "fake-success")
        self.assertEqual(result.confidence, 0.95)
        self.assertIsNone(result.error)

    def test_empty_result_is_not_an_error(self):
        """No text found is a normal, valid result -- not a failure."""
        service = OcrService(provider=_FakeEmptyProvider())
        result = service.extract_text(Path("irrelevant.png"))
        self.assertEqual(result.text, "")
        self.assertIsNone(result.error)

    def test_provider_exception_never_propagates(self):
        """OCR is assistance, not truth: a provider crash must come back as
        a valid OcrResult with error set, never raise to the caller."""
        service = OcrService(provider=_FakeExplodingProvider())
        result = service.extract_text(Path("irrelevant.png"))
        self.assertEqual(result.text, "")
        self.assertIsNone(result.confidence)
        self.assertIn("model weights corrupted", result.error)
        self.assertEqual(result.provider, "fake-exploding")


class RealRapidOcrProviderTests(unittest.TestCase):
    """One real, non-mocked check that OCR actually works in this
    environment -- confirmed manually during R3 planning (real inference on
    a generated text image returned the exact expected string at confidence
    ~0.97, fully offline). This test reproduces that as an automated,
    permanent regression check."""

    def test_real_ocr_reads_generated_text_image(self):
        from PIL import Image, ImageDraw

        tmp_path = BACKEND_DIR / "tests" / "_tmp_ocr_test_image.png"
        try:
            image = Image.new("RGB", (500, 100), color=(255, 255, 255))
            draw = ImageDraw.Draw(image)
            draw.text((10, 30), "Stahlbeton C25/30", fill=(0, 0, 0))
            image.save(tmp_path)

            service = OcrService(provider=RapidOcrProvider())
            result = service.extract_text(tmp_path)

            self.assertIsNone(result.error)
            self.assertEqual(result.provider, "rapidocr")
            self.assertIn("Stahlbeton", result.text)
            self.assertIsNotNone(result.confidence)
            self.assertGreater(result.confidence, 0.5)
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
