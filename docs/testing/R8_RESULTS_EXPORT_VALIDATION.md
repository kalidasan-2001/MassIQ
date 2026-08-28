# R8 — Results & Export: Validation

Date: 2026-08-28

All numbers below were captured by actually running the real code in this session — backend `unittest` suites against the real dev Postgres, and the real Chromium browser via Playwright — never estimated.

## 1. R7 geometry hardening fix (R8 section 4)

`backend/tests/test_geometry_service.py::GeometryDefenseInDepthTests` (5 cases): NaN width, Infinity width, -Infinity x, NaN inside a negative (SUBTRACT) rect all raise the new `GeometryValidationError` — never a raw `shapely.errors.GEOSException`. A fifth case reproduces the original golden case A to prove the hardening didn't change valid-input behavior. All 5 pass.

## 2. Authoritative-value regression (release-critical, R8 section 28)

`backend/tests/test_results_workbook.py::AuthoritativeValueRegressionTests` (pure, dataclass-constructed) and `backend/tests/test_results_routes.py::test_exported_values_match_authoritative_quantity_result` (full DB + HTTP path) both open the generated `.xlsx` with `openpyxl.load_workbook` and assert the `Area [m²]`/`Dimension [m]`/`Volume [m³]` cell values equal the exact persisted `QuantityResult.final_area_m2`/`confirmed_dimension_m`/`volume_m3` — not re-derived, not rounded before comparison (rounding is a display-only `number_format`, the underlying cell value is the full-precision float).

## 3. Quantity change / re-export (R8 section 29)

`test_reexport_after_recalculation_reflects_new_state_not_stale_cache`: exports a project, adds another accepted `DetectedRegion`, recalculates and reconfirms, exports again. The second export's Area is strictly greater than the first and matches the newly recalculated `QuantityResult.final_area_m2` exactly — proving there is no caching layer serving stale numbers.

## 4. Project isolation (R8 section 30)

`test_cross_project_result_detail_is_404`, `test_cross_project_listing_never_leaks`, `test_cross_project_export_never_leaks` — Project B's result listing/detail/export never contains or is derived from Project A's data (an export attempt on a project with zero of its own confirmed results correctly 409s, never silently returning another project's numbers).

## 5. Draft exclusion (R8 section 31)

`test_export_excludes_draft_rows`: 2 CONFIRMED + 1 DRAFT result in a project → the exported workbook's `Quantities` sheet contains **exactly 2 rows**, and the DRAFT material name never appears anywhere in the workbook.

## 6. Empty export (R8 sections 9/32)

`test_export_with_no_confirmed_results_is_409`: a project with zero confirmed `QuantityResult`s returns **HTTP 409** with a clear message, never a workbook. `test_list_results_empty_project`: `GET /results` on an empty project returns `[]` (HTTP 200), never an error.

## 7. Formula-injection protection (R8 section 41)

`backend/tests/test_export_security.py` (16 cases) plus `test_results_workbook.py::FormulaInjectionTests` (4 cases, actually opening the generated workbook): a material name of `=1+1`, a material code of `+cmd|calc`, and a project name of `@SUM(A1:A9999)` are all written to their respective cells prefixed with a leading apostrophe (`'=1+1`, etc.) — the raw trigger character never reaches a cell as the first character. Ordinary text (including text that merely contains `=`/`+`/`-` mid-string, e.g. `"Concrete (C25/30, f=30MPa)"`) is left completely unchanged.

## 8. Filename sanitization (R8 section 42)

`backend/tests/test_export_security.py::SanitizeFilenameComponentTests` (8 cases): `../../project` and embedded slashes never survive into the sanitized component; every Windows-illegal character (`:*?"<>|`) is stripped; Unicode input degrades gracefully to ASCII rather than crashing; names over 500 characters are truncated to 80; empty/whitespace-only input falls back to `"project"` rather than ever producing an empty filename component.

## 9. Material grouping (R8 sections 14-15)

`test_results_workbook.py::MaterialGroupingTests` (4 cases): same `(material_name, material_code)` → summed together; same name with a *different* code → kept separate (2 distinct groups, not merged); two different material names → never merged; the Summary sheet is proven to contain the per-material grouped subtotals and **not** a single misleading grand total across unlike materials (checked by asserting the naive cross-material sum never appears as a standalone value).

## 10. Workbook structure (R8 section 27)

`test_results_workbook.py::WorkbookStructureTests`: sheet names are exactly `["Summary", "Quantities", "Audit"]`; `Quantities` and `Audit` sheet headers match the documented column lists exactly, including explicit units (`Area [m²]`, `Dimension [m]`, `Volume [m³]`).

## 11. N+1 / performance (R8 sections 43-44)

`ResultsService._to_rows` batch-fetches every referenced table (DetectionRun/Plan/PlanPage/LegendEntry/PatternLibraryEntry/PlanScale/rejected-count) in a small constant number of queries regardless of row count — verified by direct code inspection (one `IN(...)` query per referenced table, one `GROUP BY` for rejected counts).

Workbook generation, measured directly (`build_results_workbook`, pure Python + openpyxl, no DB):

| Rows | Time | Output size |
|---|---|---|
| 10 | ~73ms | 9.3 KB |
| 100 | ~114ms | 30.8 KB |
| 1,000 | ~540ms | 240.6 KB |

Comfortably interactive at every scale tested; `test_results_workbook.py::PerformanceTests` asserts 1,000 rows complete in well under 5 seconds as a permanent, generously-tolerant regression guard (not a tight timing assertion that would be flaky in CI).

## 12. Browser E2E — E2E-08 (mandatory hard gate, R8 sections 35-36)

`frontend/e2e/specs/results-export.spec.js`, 2 real-Chromium scenarios, **zero `page.evaluate()` state injection**, **zero direct-API-call-as-primary-proof for the export itself** — the export is triggered by a real click on the Export button, verified via Playwright's real `page.waitForEvent('download')`:

1. **Full workflow**: confirm reference → compute features → run detection → accept a real candidate → confirm scale → calculate quantity → **confirm the QuantityResult** → scroll to the Results table → verify the confirmed row's displayed Area/Volume match the API response exactly → click Export → **real browser download event** → verify `download.suggestedFilename()` matches `MassIQ_<project>_quantities_<YYYYMMDD>.xlsx` → verify the downloaded file exists and has non-zero size → reload → verify the confirmed result and its numbers persist.
2. **Draft exclusion**: calculate a quantity but deliberately do **not** confirm it → Results shows it labeled "Draft" → the Export button shows `(0)` and is disabled with a visible hint → confirm the result → the button updates to `(1)` and becomes enabled.

Both pass. `monitor.assertClean()` (zero unexpected console errors, zero unexpected 5xx) passes on both.

Per R8 section 37's explicit guidance, the downloaded `.xlsx`'s *content* is not re-parsed inside the Playwright test itself (no new frontend XLSX-parsing dependency was added solely for one E2E assertion) — instead, real browser download proof (this section) is combined with the extensive backend `openpyxl` content tests (sections 2, 7, 9, 10 above), which exercise the exact same `build_results_workbook` function the live export endpoint calls.

## 13. A real bug found and fixed by the mandatory real-download test

E2E-08's download assertion **failed on first run**: `download.suggestedFilename()` returned the frontend's own hardcoded fallback (`MassIQ_quantities.xlsx`) instead of the server-chosen, sanitized filename. Root cause: `Content-Disposition` is not on the browser's CORS-safelisted response-header allowlist, so `ResultsPanel.jsx`'s `response.headers['content-disposition']` read silently returned `undefined` on every cross-origin request (true for local dev and the E2E harness, where the frontend and backend run on different ports) — invisible to any same-process backend test, only reproducible via a genuine cross-origin browser request. Fixed by adding `expose_headers=["Content-Disposition"]` to `main.py`'s CORS middleware. Re-run after the fix: the real filename is read correctly and the assertion passes.

## 14. Existing Playwright regression (R8 section 39)

All 13 pre-existing scenarios (smoke, project-plan, legend-workflow, persistence, pattern-library, detection-v2, review-quantity ×3, legacy-workflow, invalid-upload) re-run and remain green after the R8 changes.

## 15. Legacy export compatibility (R8 section 33)

`backend/app/routes/export.py`, `backend/app/services/excel_service.py::build_excel_report`, and `frontend/src/components/ExportButton.jsx` have **zero diff** in this release (confirmed via `git diff`) — the legacy MVP export path is unmodified and untested-for-regression here only because nothing about it changed.

## Conclusion

All mandatory R8 requirements were executed with real, reproducible evidence: the R7 hardening fix closes the previously-identified MEDIUM defense-in-depth gap with 5 permanent regression tests; the exporter is proven, by directly reopening generated workbooks, to never recalculate a quantity and to always reflect the current authoritative persisted state; draft/empty/cross-project/formula-injection/filename-security behavior is each independently tested; and a real, non-state-injected Playwright scenario proves the entire review → confirm → Results → real browser download workflow end-to-end — surfacing and fixing one genuine, only-visible-in-a-real-browser bug (the CORS header) along the way.
