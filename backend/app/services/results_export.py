"""R8 scope: assembles the export DTO ResultsService's rows are turned
into before ExcelService ever sees them. Deliberately the one place
"business" aggregation (grouping confirmed results by material) happens
-- ExcelService itself only ever formats already-computed numbers (R8
section 12).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.services.results_service import ResultRow

__all__ = ["ResultsExportDTO", "MaterialTotal", "build_export_dto", "group_totals_by_material"]


@dataclass(frozen=True)
class MaterialTotal:
    """R8 sections 14-15: only rows sharing the SAME material identity
    (material_name + material_code -- two materials with the same name
    but a different code, e.g. a revision, are deliberately kept
    separate) are ever summed together. There is no cross-material grand
    total anywhere in the workbook -- summing area across unrelated
    materials would be numerically possible but semantically misleading."""

    material_name: str
    material_code: str | None
    count: int
    total_area_m2: float
    total_volume_m3: float


@dataclass(frozen=True)
class ResultsExportDTO:
    project_name: str
    export_timestamp: datetime
    plan_count: int
    rows: list[ResultRow]


def group_totals_by_material(rows: list[ResultRow]) -> list[MaterialTotal]:
    groups: dict[tuple[str, str | None], list[ResultRow]] = {}
    for row in rows:
        key = (row.material_name, row.material_code)
        groups.setdefault(key, []).append(row)

    totals = [
        MaterialTotal(
            material_name=name,
            material_code=code,
            count=len(group_rows),
            total_area_m2=sum(r.area_m2 for r in group_rows),
            total_volume_m3=sum(r.volume_m3 for r in group_rows),
        )
        for (name, code), group_rows in groups.items()
    ]
    # Deterministic ordering, same discipline as ResultsService.list_results.
    totals.sort(key=lambda t: (t.material_name, t.material_code or ""))
    return totals


def build_export_dto(project_name: str, rows: list[ResultRow]) -> ResultsExportDTO:
    plan_count = len({row.plan_id for row in rows})
    return ResultsExportDTO(
        project_name=project_name,
        export_timestamp=datetime.now(timezone.utc),
        plan_count=plan_count,
        rows=rows,
    )
