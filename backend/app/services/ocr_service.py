from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OcrResult:
    """text is always a string (never None) so callers can persist it
    directly; confidence is only ever a real value a provider reported --
    never invented when a provider doesn't supply one. error is set only on
    a genuine technical failure (not "no text found", which is a normal,
    valid, empty result)."""

    text: str
    provider: str
    confidence: float | None
    error: str | None = None


class OcrProvider(Protocol):
    name: str

    def extract_text(self, image_path: Path) -> OcrResult: ...


class RapidOcrProvider:
    """Local, offline OCR via rapidocr-onnxruntime -- present in
    requirements.txt since before R3 but unused until now (flagged as
    technical debt in the R0 audit). Verified working in this environment:
    real inference on a generated text image returned the exact expected
    string at confidence ~0.97 in ~2s, fully offline (the ONNX models ship
    inside the pip package -- no network call at inference time).

    The engine is a process-wide lazy singleton: constructing RapidOCR()
    loads its models (~0.9s) and must not happen on every request or in
    every test that merely imports this module.
    """

    name = "rapidocr"
    _engine = None

    def _get_engine(self):
        if RapidOcrProvider._engine is None:
            from rapidocr_onnxruntime import RapidOCR  # imported lazily -- see class docstring

            RapidOcrProvider._engine = RapidOCR()
        return RapidOcrProvider._engine

    def extract_text(self, image_path: Path) -> OcrResult:
        engine = self._get_engine()
        result, _elapsed = engine(str(image_path))
        if not result:
            return OcrResult(text="", provider=self.name, confidence=None)
        lines = [str(item[1]) for item in result]
        confidences = [float(item[2]) for item in result if len(item) > 2]
        confidence = sum(confidences) / len(confidences) if confidences else None
        return OcrResult(text="\n".join(lines), provider=self.name, confidence=confidence)


class OcrService:
    """Provider-abstracted OCR. OCR is assistance, not truth (R3 product
    principle) -- extract_text() NEVER raises. A provider's technical
    failure (corrupt image, model error, anything) is caught here and
    returned as a valid OcrResult with `error` set and `text=""`, so the
    Legend workflow can always fall back to manual entry rather than
    breaking. Route/business logic depends only on this class, never
    directly on rapidocr_onnxruntime or any other specific library.
    """

    def __init__(self, provider: OcrProvider | None = None):
        self._provider = provider or RapidOcrProvider()

    def extract_text(self, image_path: Path) -> OcrResult:
        try:
            return self._provider.extract_text(image_path)
        except Exception as exc:  # noqa: BLE001 -- deliberately broad: OCR must never propagate
            logger.warning("ocr_failed provider=%s error=%s", self._provider.name, exc)
            return OcrResult(text="", provider=self._provider.name, confidence=None, error=str(exc))
