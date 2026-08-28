# Results & Export (R8) — Architecture

Date: 2026-08-28
Scope: turns R7's authoritative, persisted `QuantityResult` rows into a project-level Results view and a reliable, backend-generated Excel export — the final stage of the intended MassIQ workflow (`Project -> Plans -> Plan Preparation -> Legend -> Materials -> Analysis -> Results`). No detection, matching, or quantity algorithm was touched or redesigned in this release.

## Non-negotiable source of truth

```
QuantityResult (R7, persisted, authoritative)
  -> ResultsService (read model, no recalculation)
  -> Export DTO (results_export.py)
  -> ExcelService (formatting only)
  -> .xlsx
```

`ResultsService`/`ExcelService` never call `app.geometry.service.compute_final_area_m2`, never re-derive scale, and never trust a frontend-supplied area/volume. Every `Area [m²]`/`Dimension [m]`/`Volume [m³]` value that ends up in a workbook cell is read directly off a persisted `QuantityResult` row — proven directly by `tests/test_results_workbook.py::AuthoritativeValueRegressionTests` and end-to-end by `tests/test_results_routes.py::test_exported_values_match_authoritative_quantity_result`.

## Legacy export audit (R8 section 3)

Read in full before any code changed: `backend/app/routes/export.py` (`POST /export-excel`, no project/ownership scoping — a standalone, file-agnostic legacy endpoint), `backend/app/services/excel_service.py::build_excel_report` (a single "MassIQ Report" sheet, label/value rows, an optional deductions table), and `frontend/src/components/ExportButton.jsx` (the legacy MVP's own export trigger). Confirmed: the legacy flow **already trusts the frontend's own computed `area_m2`/`volume_m3`** — `PlanViewer.jsx` computes these client-side (via the untouched `quantityEngine.js`) and POSTs the final numbers directly; the backend performs zero recalculation or verification. This is acceptable for the legacy MVP flow exactly as it always has been, but is precisely the pattern R7/R8 do **not** repeat for the new authoritative path. The legacy route, service function, and frontend button are **completely untouched** by R8 (R8 section 33) — `git diff` on `backend/app/routes/export.py`/`backend/app/services/excel_service.py`'s original function/`frontend/src/components/ExportButton.jsx` shows zero changes to any of them; R8 only *adds* new functions/routes alongside.

## R7 hardening fix (R8 section 4)

The R7 independent review flagged a MEDIUM defense-in-depth gap: `compute_final_area_m2` trusted every caller to have already validated its geometry, so a NaN/Infinity coordinate would raise a raw `shapely.errors.GEOSException` rather than a controlled error. Fixed minimally, without touching the union/subtraction algorithm itself:

- `app/geometry/service.py` gains `GeometryValidationError` and a `_require_finite()` check before any `shapely.box()` call, plus a `try/except ShapelyError` safety net around both box construction and the union/difference operations themselves.
- `QuantityService.calculate()` catches `GeometryValidationError`, logs it (`quantity_geometry_invalid`, since reaching this indicates a real data-integrity problem, not a bad request), and raises a new `GeometryStateError`.
- `routes/quantity.py` maps `GeometryStateError` to a controlled `500` — a `500`, not a `400`, because the current request's own input (the confirmed dimension) was fine; a *persisted* row was not.
- Permanent regression tests: `tests/test_geometry_service.py::GeometryDefenseInDepthTests` (5 cases: NaN/Infinity in every position, both positive and negative rects) plus a regression case proving valid input still works identically after the change.

## ResultsService (R8 section 5)

No new database table — every field a result row needs already exists on `QuantityResult`/`DetectionRun`/`LegendEntry`/`PatternLibraryEntry`/`Plan`/`PlanPage`/`PlanScale` (R8 section 46). `ResultsService.list_results`/`get_result` enforce project ownership via `ProjectService.get_project`, batch-fetch every referenced row (N+1 avoidance, see below), and return a plain `ResultRow` dataclass — never a raw SQLAlchemy model, never an internal filesystem path.

### Material provenance (R8 section 7)

Resolved through the exact same chain R6/R7 already established — `QuantityResult.detection_run_id -> DetectionRun.reference_legend_entry_id` (or `reference_pattern_library_entry_id`) `-> LegendEntry.material_name/material_code` (or `PatternLibraryEntry.canonical_material_name/material_code`). Never re-inferred, never a fresh R5 similarity computation — `ResultsService` never imports or calls anything from `app.hatch.similarity`.

### N+1 avoidance (R8 section 44)

This codebase's established precedent (R1 onward) is unidirectional FKs with no `relationship()`/`back_populates` added to a model by a later release, so `ResultsService._to_rows` cannot use SQLAlchemy eager-loading joins without introducing a new modeling pattern. Instead it batch-fetches every referenced `DetectionRun`/`Plan`/`PlanPage`/`LegendEntry`/`PatternLibraryEntry`/`PlanScale` via one `IN (...)` query per table, plus one `GROUP BY` query for every run's rejected-region count — a small, constant number of queries (~7) regardless of how many `QuantityResult` rows are being listed, not one query per row.

### Deterministic ordering (R8 section 10)

`plan_name -> page_number -> material_name -> quantity_result_id` (the ID as a final, always-unique tie-breaker). Repeated calls with unchanged data return identical order — verified directly (`test_deterministic_ordering_repeated_calls_match`).

## Draft vs. confirmed policy (R8 section 8)

**Chosen deliberately: default export = CONFIRMED only.** `GET /results` returns every result regardless of status (the Results *view* must show drafts too, clearly labeled — R8 section 24); `POST /results/export` always filters to `QuantityResultStatus.CONFIRMED` before generating anything. A DRAFT result is, by R7's own state model, not yet a number a human has explicitly signed off on — it must never silently appear in a report a user might hand to a client or contractor as final. No override/flag was added to allow draft export in R8; if a future release needs that, it should be a deliberate, separate decision.

## Empty results / empty export (R8 sections 9/32)

`GET /results` on a project with zero results returns `[]` — a normal, successful response, never an error. `POST /results/export` on a project with zero **CONFIRMED** results returns **HTTP 409** (a real state conflict, not a malformed request) with a clear message — never a workbook that merely *looks* like a valid final estimate but contains no rows. A cheap `GET /results/export/preflight` endpoint lets the frontend disable the Export button and show an accurate confirmed-count without generating a workbook just to find out there's nothing in it.

## Excel architecture (R8 sections 12-13)

`ExcelService.build_results_workbook(dto: ResultsExportDTO, material_totals: list[MaterialTotal]) -> bytes` performs **zero** business calculation — it only formats numbers `results_export.py` already computed. Three sheets:

- **Summary** — project name, export timestamp (UTC), plan count, confirmed quantity count, the disclaimer, and a **"Totals by Material"** table (see Aggregation safety below). No single cross-material grand total anywhere.
- **Quantities** — one row per exported `QuantityResult`: `Plan | Page | Material | Material Code | Area [m²] | Dimension [m] | Volume [m³] | Status | Calculation Version | Quantity Result ID | Detection Run ID | Source Reference`.
- **Audit** (R8 section 19) — `Quantity Result ID | Detection Run ID | Reference Type | Reference ID | Accepted Regions | Rejected Regions | Manual Additions | Manual Subtractions | Scale Method | Calculation Version`. `Rejected Regions` is computed on demand by `ResultsService` (not persisted anywhere — R6's `DetectedRegion.status` is the only source of truth for it); `Scale Method` is read from the page's `PlanScale`.

## Aggregation safety / material grouping (R8 sections 14-15)

`results_export.group_totals_by_material` sums `area_m2`/`volume_m3` **only** across rows sharing the exact same `(material_name, material_code)` identity — verified directly: same name + same code groups together; same name + *different* code does **not**; two different names (e.g. "Concrete" vs. "Existing Concrete") never merge. There is no code path anywhere that sums area/volume across unrelated materials into one number.

## Units and precision (R8 sections 16-17)

Canonical units throughout — normalized page coordinates never appear in the export at all; only `m²`/`m`/`m³`, explicit in every header. Precision is a **presentation-only** concern: `AREA_FORMAT = "0.00"`, `DIMENSION_FORMAT = "0.000"`, `VOLUME_FORMAT = "0.000"` are Excel `number_format` strings applied to cells — the underlying stored float is always the full-precision authoritative value, never rounded before being written (R8 section 17 — "Excel formatting should affect display, not authoritative persisted values").

## Excel formulas vs. values (R8 section 18)

No workbook formula is used anywhere — every cell (including the material-total subtotals) is a plain, already-computed numeric value written by Python. Simpler and more auditable than a formula-driven subtotal, and avoids any risk of Excel recalculating something differently across locales/versions.

## Formula-injection protection (R8 section 41)

`app/services/export_security.py::sanitize_cell_text` prefixes any user-controlled text value that starts with `=`, `+`, `-`, `@`, tab, or CR with a leading apostrophe (Excel's own "force text" convention) before it is ever written to a cell — applied to every material name/code and the project name. Never applied to MassIQ-controlled values (IDs, enum values, `calculation_version`), which can never begin with a trigger character. Tested directly against `=1+1`, `+cmd|...`, `-2+3`, `@SUM(...)`, and confirmed ordinary text (including text that merely *contains* `=` mid-string, e.g. `"f=30MPa"`) is left untouched.

## Filename sanitization (R8 section 42)

`sanitize_filename_component` NFKD-normalizes to ASCII, strips everything except letters/digits/spaces/hyphens/underscores (so `../../project`, embedded slashes, and every Windows-illegal character are removed), truncates to 80 characters, and falls back to `"project"` if the result would otherwise be empty. The generated filename is always `MassIQ_<sanitized-project-name>_quantities_<YYYYMMDD>.xlsx` — the sanitized component is always embedded between a fixed prefix and suffix, so even a reserved Windows device name (`CON`, `NUL`, etc.) can never become the literal filename.

## Temporary-file strategy (R8 section 26)

The workbook is built entirely in memory (`io.BytesIO`, exactly like the legacy `build_excel_report`) and streamed directly to the client via `StreamingResponse` — no temporary file is ever written to disk, so there is nothing to clean up and nothing that can accumulate in production storage.

## Export snapshot semantics (R8 section 20)

**Generated live from current persisted CONFIRMED results, every time** — no `ExportJob` table, no persisted snapshot. Re-exporting after a user changes reviewed geometry and recalculates always reflects the new authoritative state (proven directly: `test_reexport_after_recalculation_reflects_new_state_not_stale_cache`). If a project needs a frozen historical export, that is a deliberate future decision, not something R8 quietly half-implements.

## Auditability (R8 section 19)

Every exported row traces back, without ambiguity: `Quantity Result ID -> Plan -> Page -> Material -> DetectionRun -> reference (LegendEntry or PatternLibraryEntry) -> accepted/rejected/manual-add/manual-subtract counts -> PlanScale method -> calculation_version`. Nothing important lives only in browser state — every one of those facts is queryable from persisted rows.

## Frontend (functional, R8 section 22)

`ResultsPanel.jsx` renders at the project level (a sibling of `PatternLibraryPanel.jsx`, same "functional, not polished" discipline), showing every result (draft and confirmed, clearly labeled with text, not color alone — R8 section 26) with an expandable per-row detail panel (R8 section 23) and an Export button labeled `Export confirmed quantities (N)` that is disabled at `N=0` with a visible explanatory hint. The download itself reuses the exact technique the legacy `ExportButton.jsx` already established (`Blob` + `URL.createObjectURL` + a synthetic `<a download>` click) — the filename is read from the server's own `Content-Disposition` header, never constructed client-side.

## Known limitations

- No override exists to export DRAFT results (by design — see "Draft vs. confirmed policy" above); a future release may add one if a real workflow need for it appears.
- The legacy `/export-excel` MVP path remains completely separate and untouched; consolidating the two export experiences is explicitly deferred, same as R6/R7 left the two review experiences unconsolidated.
- Material identity grouping is `(material_name, material_code)` exact-match only — no fuzzy/normalized matching (e.g. trimming whitespace differences) is attempted; this mirrors LegendEntry's own free-text material_name precedent from R3 onward.
