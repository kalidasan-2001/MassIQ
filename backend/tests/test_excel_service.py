from __future__ import annotations

import sys
import unittest
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.excel_service import build_excel_report

_BASE_PAYLOAD = {
    "project_name": "Test Project",
    "plan_name": "plan-1",
    "component": "Stahlbeton C25/30",
    "detection_method": "Backend hatch detection",
    "accepted_detection_area_m2": 10.0,
    "added_correction_area_m2": 0.0,
    "subtracted_correction_area_m2": 1.8,
    "area_m2": 8.2,
    "height_m": 0.3,
    "volume_m3": 2.46,
    "review_status": "Completed",
    "notes": "Some notes",
}

# The fixed label rows written unconditionally by build_excel_report today.
_BASE_ROW_COUNT = 12


class BuildExcelReportRegressionTests(unittest.TestCase):
    """No deductions supplied -> sheet must be identical to the pre-existing behavior."""

    def _load(self, payload):
        wb = load_workbook(BytesIO(build_excel_report(payload)))
        return wb.active

    def test_no_deductions_key_produces_same_row_count_as_before(self):
        ws = self._load(dict(_BASE_PAYLOAD))
        self.assertEqual(ws.max_row, _BASE_ROW_COUNT)

    def test_empty_deductions_list_produces_same_row_count_as_before(self):
        ws = self._load({**_BASE_PAYLOAD, "deductions": []})
        self.assertEqual(ws.max_row, _BASE_ROW_COUNT)

    def test_subtracted_correction_area_row_unchanged(self):
        ws = self._load(dict(_BASE_PAYLOAD))
        self.assertEqual(ws.cell(row=7, column=1).value, "Subtracted Correction Area (m2)")
        self.assertEqual(ws.cell(row=7, column=2).value, 1.8)


class BuildExcelReportDeductionRowsTests(unittest.TestCase):
    def test_deduction_rows_appended_with_correct_values(self):
        payload = {
            **_BASE_PAYLOAD,
            "deductions": [
                {"type": "window", "count": 2, "unit_area_m2": 0.45, "line_total_m2": 0.9},
                {"type": "door", "count": 1, "unit_area_m2": 1.8, "line_total_m2": 1.8},
            ],
        }
        wb = load_workbook(BytesIO(build_excel_report(payload)))
        ws = wb.active

        # Base rows are untouched.
        self.assertEqual(ws.cell(row=7, column=1).value, "Subtracted Correction Area (m2)")
        self.assertEqual(ws.cell(row=7, column=2).value, 1.8)

        header_row = _BASE_ROW_COUNT + 2
        self.assertEqual(ws.cell(row=header_row, column=1).value, "Type")
        self.assertEqual(ws.cell(row=header_row, column=2).value, "Count")
        self.assertEqual(ws.cell(row=header_row, column=3).value, "Unit Area (m2)")
        self.assertEqual(ws.cell(row=header_row, column=4).value, "Line Total (m2)")

        window_row = header_row + 1
        self.assertEqual(ws.cell(row=window_row, column=1).value, "Window")
        self.assertEqual(ws.cell(row=window_row, column=2).value, 2)
        self.assertEqual(ws.cell(row=window_row, column=3).value, 0.45)
        self.assertEqual(ws.cell(row=window_row, column=4).value, 0.9)

        door_row = header_row + 2
        self.assertEqual(ws.cell(row=door_row, column=1).value, "Door")
        self.assertEqual(ws.cell(row=door_row, column=2).value, 1)
        self.assertEqual(ws.cell(row=door_row, column=3).value, 1.8)
        self.assertEqual(ws.cell(row=door_row, column=4).value, 1.8)

    def test_line_total_equals_unit_area_times_count_as_passed_through(self):
        # The backend trusts the frontend-computed line_total_m2 (consistent with how
        # subtracted_correction_area_m2 itself is already frontend-computed) -- this
        # test just proves it passes through unmodified, not that the backend recomputes it.
        payload = {
            **_BASE_PAYLOAD,
            "deductions": [{"type": "window", "count": 3, "unit_area_m2": 0.5, "line_total_m2": 1.5}],
        }
        wb = load_workbook(BytesIO(build_excel_report(payload)))
        ws = wb.active
        data_row = _BASE_ROW_COUNT + 3
        unit_area = ws.cell(row=data_row, column=3).value
        count = ws.cell(row=data_row, column=2).value
        line_total = ws.cell(row=data_row, column=4).value
        self.assertAlmostEqual(unit_area * count, line_total)


if __name__ == "__main__":
    unittest.main()
