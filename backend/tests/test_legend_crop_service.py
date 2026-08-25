"""R3: LegendCropService tests. Uses a real PlanPage-shaped object pointing
at a real PNG on disk (via a temp StorageService root), and verifies both
the happy path (correct pixel region actually cropped) and every bounds
violation the R3 checklist requires: negative coordinates, zero-size
selections, and a selection extending past the page.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from PIL import Image

from app.models.plan_page import PlanPage
from app.services.legend_crop_service import CropBoundsError, LegendCropService, RegionSelection
from app.services.storage_service import StorageService

PAGE_WIDTH = 800
PAGE_HEIGHT = 400


class LegendCropServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.storage = StorageService(root=Path(self._tmp.name))
        self.plan_id = uuid.uuid4()

        # Build a real preview PNG: left half red, right half blue -- lets a
        # test assert the crop actually came from the requested region, not
        # just that *some* bytes came back.
        image = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), color=(0, 0, 255))
        for x in range(PAGE_WIDTH // 2):
            for y in range(PAGE_HEIGHT):
                image.putpixel((x, y), (255, 0, 0))
        content = _png_bytes(image)
        reference = self.storage.save_page_preview(self.plan_id, 1, content)

        self.plan_page = PlanPage(
            id=uuid.uuid4(),
            plan_id=self.plan_id,
            page_number=1,
            width=float(PAGE_WIDTH),
            height=float(PAGE_HEIGHT),
            rotation=0,
            vector_content_available=False,
            preview_reference=reference,
        )
        self.service = LegendCropService(self.storage)

    def tearDown(self):
        self._tmp.cleanup()

    def test_crop_region_returns_correct_pixel_area(self):
        # Left quarter of the page -- entirely within the red half.
        selection = RegionSelection(x=0.0, y=0.0, width=0.25, height=0.5)
        result_bytes = self.service.crop_region(self.plan_page, selection)
        with Image.open(_bytes_to_path(result_bytes, self._tmp.name)) as cropped:
            self.assertEqual(cropped.size, (PAGE_WIDTH // 4, PAGE_HEIGHT // 2))
            self.assertEqual(cropped.getpixel((0, 0)), (255, 0, 0))

    def test_crop_region_right_half_is_blue(self):
        selection = RegionSelection(x=0.75, y=0.0, width=0.2, height=1.0)
        result_bytes = self.service.crop_region(self.plan_page, selection)
        with Image.open(_bytes_to_path(result_bytes, self._tmp.name)) as cropped:
            self.assertEqual(cropped.getpixel((0, 0)), (0, 0, 255))

    def test_negative_x_rejected(self):
        with self.assertRaises(CropBoundsError):
            RegionSelection(x=-0.1, y=0.0, width=0.2, height=0.2)

    def test_negative_y_rejected(self):
        with self.assertRaises(CropBoundsError):
            RegionSelection(x=0.0, y=-0.5, width=0.2, height=0.2)

    def test_zero_width_rejected(self):
        with self.assertRaises(CropBoundsError):
            RegionSelection(x=0.1, y=0.1, width=0.0, height=0.2)

    def test_zero_height_rejected(self):
        with self.assertRaises(CropBoundsError):
            RegionSelection(x=0.1, y=0.1, width=0.2, height=0.0)

    def test_selection_extending_past_right_edge_rejected(self):
        with self.assertRaises(CropBoundsError):
            RegionSelection(x=0.9, y=0.0, width=0.5, height=0.2)

    def test_selection_extending_past_bottom_edge_rejected(self):
        with self.assertRaises(CropBoundsError):
            RegionSelection(x=0.0, y=0.9, width=0.2, height=0.5)

    def test_missing_preview_raises_crop_bounds_error(self):
        page_without_preview = PlanPage(
            id=uuid.uuid4(),
            plan_id=self.plan_id,
            page_number=2,
            width=float(PAGE_WIDTH),
            height=float(PAGE_HEIGHT),
            rotation=0,
            vector_content_available=False,
            preview_reference=None,
        )
        selection = RegionSelection(x=0.1, y=0.1, width=0.2, height=0.2)
        with self.assertRaises(CropBoundsError):
            self.service.crop_region(page_without_preview, selection)


def _png_bytes(image: Image.Image) -> bytes:
    import io

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _bytes_to_path(content: bytes, tmp_dir: str) -> Path:
    path = Path(tmp_dir) / f"_check_{uuid.uuid4().hex}.png"
    path.write_bytes(content)
    return path


if __name__ == "__main__":
    unittest.main()
