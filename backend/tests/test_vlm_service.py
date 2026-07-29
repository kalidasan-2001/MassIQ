from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.vlm_service import (
    LEGEND_CROP_RIGHT_RATIO,
    _crop_legend_region,
    _normalize_candidate,
    suggest_legend_hatch_candidates,
)


def _unset_api_key():
    return mock.patch.dict("os.environ", {}, clear=False)


class CropLegendRegionTests(unittest.TestCase):
    def test_crop_is_within_30_to_35_percent_of_page_width(self):
        image = Image.new("RGB", (1000, 600), color=(255, 255, 255))
        crop, bbox = _crop_legend_region(image)
        self.assertEqual(bbox["height"], 600)
        self.assertEqual(bbox["y"], 0)
        crop_ratio = bbox["width"] / 1000
        self.assertGreaterEqual(crop_ratio, 0.30)
        self.assertLessEqual(crop_ratio, 0.35)
        self.assertEqual(crop.size, (bbox["width"], bbox["height"]))
        self.assertAlmostEqual(bbox["width"] / 1000, LEGEND_CROP_RIGHT_RATIO, delta=0.01)


class NormalizeCandidateTests(unittest.TestCase):
    def setUp(self):
        self.crop_bbox = {"x": 680, "y": 0, "width": 320, "height": 600}
        self.crop_size = (320, 600)

    def test_translates_crop_relative_bbox_to_full_page_coordinates(self):
        raw = {
            "matched_text": "Stahlbeton C25/30",
            "bbox": {"x": 15, "y": 25, "width": 40, "height": 40},
            "confidence": 0.92,
            "reason": "Hatch sample next to the matching label.",
        }
        result = _normalize_candidate(raw, self.crop_bbox, self.crop_size)
        self.assertIsNotNone(result)
        self.assertEqual(result["bbox"], {"x": 695, "y": 25, "width": 40, "height": 40})
        self.assertEqual(result["confidence"], 0.92)
        self.assertEqual(result["matched_text"], "Stahlbeton C25/30")

    def test_clamps_bbox_that_overflows_crop_bounds(self):
        raw = {"bbox": {"x": 300, "y": 590, "width": 100, "height": 100}, "confidence": 0.5}
        result = _normalize_candidate(raw, self.crop_bbox, self.crop_size)
        self.assertIsNotNone(result)
        # x=300 + width should not exceed crop width (320); y=590 should not exceed crop height (600).
        self.assertLessEqual(result["bbox"]["x"] + result["bbox"]["width"], self.crop_bbox["x"] + 320)
        self.assertLessEqual(result["bbox"]["y"] + result["bbox"]["height"], self.crop_bbox["y"] + 600)

    def test_clamps_confidence_to_zero_one_range(self):
        raw = {"bbox": {"x": 0, "y": 0, "width": 10, "height": 10}, "confidence": 1.7}
        result = _normalize_candidate(raw, self.crop_bbox, self.crop_size)
        self.assertEqual(result["confidence"], 1.0)

        raw_negative = {"bbox": {"x": 0, "y": 0, "width": 10, "height": 10}, "confidence": -0.3}
        result_negative = _normalize_candidate(raw_negative, self.crop_bbox, self.crop_size)
        self.assertEqual(result_negative["confidence"], 0.0)

    def test_rejects_missing_or_zero_size_bbox(self):
        self.assertIsNone(_normalize_candidate({"confidence": 0.9}, self.crop_bbox, self.crop_size))
        self.assertIsNone(
            _normalize_candidate(
                {"bbox": {"x": 0, "y": 0, "width": 0, "height": 0}, "confidence": 0.9},
                self.crop_bbox,
                self.crop_size,
            )
        )


class SuggestLegendHatchCandidatesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.page_path = self.tmp_dir / "page.png"
        Image.new("RGB", (1000, 600), color=(255, 255, 255)).save(self.page_path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_api_key_returns_valid_empty_shape(self):
        with _unset_api_key():
            import os

            os.environ.pop("OPENAI_API_KEY", None)
            result = suggest_legend_hatch_candidates(self.page_path, "Stahlbeton C25/30")

        self.assertEqual(
            result,
            {
                "available": False,
                "reason": "OPENAI_API_KEY not configured; AI suggestion unavailable.",
                "component_query": "Stahlbeton C25/30",
                "legend_crop": None,
                "hatch_candidates": [],
                "rejected_candidates": [],
            },
        )

    def test_missing_image_returns_valid_empty_shape_without_raising(self):
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = suggest_legend_hatch_candidates(self.tmp_dir / "does-not-exist.png", "Stahlbeton C25/30")

        self.assertFalse(result["available"])
        self.assertEqual(result["hatch_candidates"], [])
        self.assertEqual(result["rejected_candidates"], [])
        self.assertIsNone(result["legend_crop"])

    def test_mocked_vlm_success_produces_full_page_bbox(self):
        fake_payload = {
            "hatch_candidates": [
                {
                    "matched_text": "Stahlbeton C25/30",
                    "bbox": {"x": 15, "y": 25, "width": 40, "height": 40},
                    "confidence": 0.92,
                    "reason": "Matches the requested component label.",
                }
            ],
            "rejected_candidates": [
                {
                    "matched_text": "Mauerwerk",
                    "bbox": {"x": 15, "y": 100, "width": 40, "height": 40},
                    "confidence": 0.4,
                    "reason": "Different component.",
                }
            ],
        }
        fake_response = SimpleNamespace(output_text=json.dumps(fake_payload))

        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), mock.patch(
            "openai.OpenAI"
        ) as mock_openai_cls:
            mock_client = mock_openai_cls.return_value
            mock_client.responses.create.return_value = fake_response
            result = suggest_legend_hatch_candidates(self.page_path, "Stahlbeton C25/30")

        self.assertTrue(result["available"])
        self.assertEqual(result["reason"], "")
        self.assertEqual(result["component_query"], "Stahlbeton C25/30")
        self.assertEqual(result["legend_crop"], {"x": 680, "y": 0, "width": 320, "height": 600})
        self.assertEqual(len(result["hatch_candidates"]), 1)
        self.assertEqual(result["hatch_candidates"][0]["bbox"], {"x": 695, "y": 25, "width": 40, "height": 40})
        self.assertEqual(len(result["rejected_candidates"]), 1)
        self.assertEqual(result["rejected_candidates"][0]["bbox"], {"x": 695, "y": 100, "width": 40, "height": 40})

    def test_mocked_vlm_no_matches_returns_available_true_with_empty_candidates(self):
        fake_response = SimpleNamespace(output_text=json.dumps({"hatch_candidates": [], "rejected_candidates": []}))

        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), mock.patch(
            "openai.OpenAI"
        ) as mock_openai_cls:
            mock_client = mock_openai_cls.return_value
            mock_client.responses.create.return_value = fake_response
            result = suggest_legend_hatch_candidates(self.page_path, "Stahlbeton C25/30")

        self.assertTrue(result["available"])
        self.assertIn("Stahlbeton C25/30", result["reason"])
        self.assertEqual(result["hatch_candidates"], [])

    def test_mocked_vlm_error_returns_valid_empty_shape_without_raising(self):
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), mock.patch(
            "openai.OpenAI"
        ) as mock_openai_cls:
            mock_client = mock_openai_cls.return_value
            mock_client.responses.create.side_effect = RuntimeError("network down")
            result = suggest_legend_hatch_candidates(self.page_path, "Stahlbeton C25/30")

        self.assertFalse(result["available"])
        self.assertEqual(result["hatch_candidates"], [])
        self.assertEqual(result["rejected_candidates"], [])
        # legend_crop should still be populated since the crop succeeded before the API call failed.
        self.assertEqual(result["legend_crop"], {"x": 680, "y": 0, "width": 320, "height": 600})


if __name__ == "__main__":
    unittest.main()
