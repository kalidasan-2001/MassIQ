from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook


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
    ]
    for row_index, (label, value) in enumerate(rows, start=1):
        ws.cell(row=row_index, column=1, value=label)
        ws.cell(row=row_index, column=2, value=value)
    output = BytesIO()
    wb.save(output)
    return output.getvalue()
