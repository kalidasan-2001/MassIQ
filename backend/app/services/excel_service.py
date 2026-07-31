from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook

DISCLAIMER_TEXT = (
    "MassIQ accelerates quantity takeoff and supports your review. "
    "It does not guarantee accuracy — confirm all quantities before use."
)


def build_excel_report(payload: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "MassIQ Report"
    rows = [
        ("Project", payload.get("project_name", "")),
        ("Plan", payload.get("plan_name", "")),
        ("Component", payload.get("component", "")),
        ("Detection Method", payload.get("detection_method", "")),
        ("Accepted Detection Area (m2)", payload.get("accepted_detection_area_m2", 0)),
        ("Added Correction Area (m2)", payload.get("added_correction_area_m2", 0)),
        ("Subtracted Correction Area (m2)", payload.get("subtracted_correction_area_m2", 0)),
        ("Final Area (m2)", payload.get("area_m2", 0)),
        ("Height (m)", payload.get("height_m", 0)),
        ("Volume (m3)", payload.get("volume_m3", 0)),
        ("Review Status", payload.get("review_status", "")),
        ("Notes", payload.get("notes", "")),
        ("Disclaimer", DISCLAIMER_TEXT),
    ]
    row_index = 0
    for row_index, (label, value) in enumerate(rows, start=1):
        ws.cell(row=row_index, column=1, value=label)
        ws.cell(row=row_index, column=2, value=value)

    deductions = payload.get("deductions") or []
    if deductions:
        header_row = row_index + 2
        ws.cell(row=header_row, column=1, value="Type")
        ws.cell(row=header_row, column=2, value="Count")
        ws.cell(row=header_row, column=3, value="Unit Area (m2)")
        ws.cell(row=header_row, column=4, value="Line Total (m2)")
        for offset, deduction in enumerate(deductions, start=1):
            data_row = header_row + offset
            deduction_type = str(deduction.get("type", "")).strip()
            label = deduction_type.capitalize() if deduction_type else "Deduction"
            ws.cell(row=data_row, column=1, value=label)
            ws.cell(row=data_row, column=2, value=deduction.get("count", 1))
            ws.cell(row=data_row, column=3, value=deduction.get("unit_area_m2", 0))
            ws.cell(row=data_row, column=4, value=deduction.get("line_total_m2", 0))

    output = BytesIO()
    wb.save(output)
    return output.getvalue()
