# R8 — Results & Export Hardening: Checklist

Date: 2026-08-28
Repository: `C:\Users\kalid\MassIQ`, branch `feature/r8-results-export-hardening` (created from `main` after fast-forward-merging `feature/r7-review-quantity-integration`, per R7's independent review approval)
Scope: turns R7's authoritative, persisted `QuantityResult` into a project-level Results view and a reliable, backend-generated Excel export. No detection/matching/quantity algorithm was redesigned.

Status legend: **PASS** (executed with evidence), **FAIL**, **BLOCKED**, **DEFERRED**. PASS requires executed evidence, not code inspection alone.

---

## Branch and baseline

**PASS.** R7 (`feature/r7-review-quantity-integration`) was confirmed independently reviewed and approved, but not yet merged into `main`. Fast-forward merged (`git merge --ff-only`, zero-conflict). Baseline re-verified on `main` after the merge: `alembic current`/`heads` → `c61d4d05e4c9 (head)`; backend suite → 538 tests, 0 failures; `npx vitest run` → 44 passed; `npm run build` → 100 modules; `npx playwright test --project=chromium` → 13 passed. `feature/r8-results-export-hardening` created from `main` only after this full green baseline.

## Legacy export audit (R8 section 3)

**PASS.** `backend/app/routes/export.py`, `backend/app/services/excel_service.py::build_excel_report`, and `frontend/src/components/ExportButton.jsx` read in full before any code changed. Documented: the legacy flow already trusts the frontend's own client-computed `area_m2`/`volume_m3` with zero backend verification — acceptable for the legacy MVP flow as it always has worked, and explicitly not repeated for the new path. All three files have **zero diff** in this release (confirmed via `git diff`).

## R7 hardening fix (R8 section 4)

**PASS.** `app/geometry/service.py` gains `GeometryValidationError` + a finite-value check before every `shapely.box()` call + a `try/except ShapelyError` safety net around the union/difference operations. `QuantityService.calculate()` translates it into a new `GeometryStateError`, logged and mapped to a controlled `500` (not `400` — the request's own input was fine) in `routes/quantity.py`. 5 new permanent regression tests (`GeometryDefenseInDepthTests`), including a same-input-still-works case proving the hardening didn't change valid-input behavior. The union/subtraction algorithm itself was not touched.

## ResultsService / Result DTO (R8 sections 5-6)

**PASS.** `ResultsService` (no new database table — R8 section 46) reads `QuantityResult` and resolves material provenance through `DetectionRun -> LegendEntry`/`PatternLibraryEntry` (never re-inferred, no R5 matching invoked). `ResultRow` exposes only IDs/names/numbers/status — no internal filesystem path anywhere (verified directly, `test_no_internal_filesystem_path_exposed`).

## QuantityResult authority (release-critical, R8 sections 1-2)

**PASS.** `ResultsService`/`ExcelService` never import or call `app.geometry.service.compute_final_area_m2`, never re-derive scale, never recompute anything. Proven directly by reopening generated workbooks and comparing cell values byte-for-byte against the persisted `QuantityResult` row (`AuthoritativeValueRegressionTests`, `test_exported_values_match_authoritative_quantity_result`) and by a re-export-after-recalculation test proving no stale caching.

## Material provenance (R8 section 7)

**PASS.** Tested for both reference types directly: a `LegendEntry` reference resolves `material_name`/`material_code` from that entry; a `PatternLibraryEntry` reference resolves them from the library entry. Neither path calls anything from `app.hatch.similarity`.

## Draft/confirmed policy (R8 section 8)

**PASS, documented deliberately.** `GET /results` returns every status (the Results view must show drafts, clearly labeled). `POST /results/export` filters to `QuantityResultStatus.CONFIRMED` only, unconditionally — no override. Verified directly: 2 CONFIRMED + 1 DRAFT in a project → exported workbook contains exactly 2 rows (`test_export_excludes_draft_rows`).

## Empty results / empty export (R8 sections 9/32)

**PASS.** `GET /results` on an empty project returns `[]`, HTTP 200. `POST /results/export` with zero CONFIRMED results returns HTTP **409** with a clear message, never a workbook. A cheap `GET /results/export/preflight` lets the frontend disable Export without generating anything.

## Deterministic ordering (R8 section 10)

**PASS.** `plan_name -> page_number -> material_name -> quantity_result_id`. Verified: two separate `list_results` calls with unchanged data return identical order.

## Results API (R8 section 11)

**PASS.** `GET /results`, `GET /results/{id}`, `POST /results/export`, `GET /results/export/preflight` — all thin, all exception-mapped to controlled 404/409/500. Literal routes (`/export`, `/export/preflight`) deliberately registered before the parameterized `/{quantity_result_id}` route to avoid any path-matching ambiguity.

## Excel architecture / workbook sheets / columns (R8 sections 12-13)

**PASS.** `ExcelService.build_results_workbook` performs zero business calculation — verified by direct code inspection and by the authoritative-value regression tests above. Three sheets (`Summary`/`Quantities`/`Audit`) with exactly the documented headers, verified by reopening the workbook with `openpyxl` (`WorkbookStructureTests`).

## Units (R8 section 16)

**PASS.** Every numeric header is explicit (`Area [m²]`, `Dimension [m]`, `Volume [m³]`); no normalized coordinate or raw mm value ever appears in the export.

## Precision (R8 section 17)

**PASS.** Presentation-only `number_format` strings (`"0.00"`/`"0.000"`); the underlying stored cell value is always the full-precision authoritative float, never rounded before being written — verified directly (`test_excel_values_equal_authoritative_persisted_values` compares the raw, unrounded value).

## Formulas vs. values (R8 section 18)

**PASS.** No workbook formula anywhere; every cell (including material-total subtotals) is a plain pre-computed value.

## Grouping / aggregation safety (R8 sections 14-15)

**PASS.** `group_totals_by_material` sums only rows sharing the exact `(material_name, material_code)` identity. Verified: same-name/different-code kept separate; different names never merged; the Summary sheet's grouped subtotals are present and no misleading single cross-material grand total exists (`MaterialGroupingTests`).

## Auditability (R8 section 19)

**PASS.** `Audit` sheet: Quantity Result ID, DetectionRun ID, reference type/ID, accepted/rejected/manual-add/manual-subtract counts, scale method, calculation version — every field traceable to a persisted row, none duplicating full geometry.

## Export snapshot semantics (R8 section 20)

**PASS, documented deliberately.** Generated live from current persisted CONFIRMED state on every call; no `ExportJob` table. Proven directly: re-export after a geometry change/recalculation reflects the new number, not a stale one.

## Filename (R8 sections 21/42)

**PASS.** `MassIQ_<sanitized-project-name>_quantities_<YYYYMMDD>.xlsx`. Sanitizer strips path-traversal sequences, slashes, and every Windows-illegal character; truncates to 80 chars; falls back to `"project"` on empty input. Tested with 8 adversarial cases plus a real end-to-end HTTP `Content-Disposition` check.

## Temporary-file strategy (R8 sections 25-26)

**PASS.** In-memory `BytesIO` workbook, streamed directly via `StreamingResponse` — no temp file written to disk, nothing to clean up.

## Legacy export coexistence (R8 section 33)

**PASS.** Confirmed zero diff on the three legacy files (see "Legacy export audit" above).

## Frontend Results UI (R8 sections 22-24, 34)

**PASS.** `ResultsPanel.jsx` (project-level, mirrors `PatternLibraryPanel.jsx`'s shape) shows plan/page/material/area/dimension/volume/status for every result, an explicit "Confirmed"/"Draft" text label (not color alone), an expandable per-row detail panel with provenance counts, and an Export button labeled `Export confirmed quantities (N)`, disabled with a visible hint at `N=0`. 8 new Vitest/RTL tests (empty state, rendering, draft/confirmed distinction, export enable/disable, detail expansion, error state, real-download-flow simulation).

## Backend workbook tests (R8 section 27)

**PASS.** Every workbook test actually reopens the generated `.xlsx` with `openpyxl.load_workbook` and inspects sheet names, headers, numeric cell values, row counts, ordering, grouping totals, and formula-injection sanitization — never just "bytes were returned."

## Formula-injection protection (R8 section 41)

**PASS.** 16 pure unit tests + 4 workbook-level tests; every trigger character (`=`, `+`, `-`, `@`, tab, CR) neutralized with a leading apostrophe; ordinary text (including mid-string `=`/`+`/`-`) untouched.

## Performance (R8 sections 43-44)

**PASS.** Workbook generation: ~73ms/10 rows, ~114ms/100 rows, ~540ms/1,000 rows — comfortably interactive; permanent regression test asserts a generous 5-second ceiling at 1,000 rows. `ResultsService` batch-fetches every referenced table in a small constant number of queries (not one per row) — verified by direct code inspection.

## Backend tests

**PASS.** **600 tests, 0 failures** (538 R7 baseline + 62 new: 5 geometry hardening + 10 results-service + 14 results-routes + 17 workbook + 16 export-security), executed against the real dev Postgres.

## Frontend unit tests

**PASS.** `npx vitest run` → **52 tests, 0 failures** (44 baseline + 8 new `ResultsPanel.test.jsx` tests).

## Frontend build

**PASS.** `npm run build` → **101 modules**, 0 errors (100 baseline + 1 new `ResultsPanel.jsx`).

## Playwright — mandatory hard gate (R8 sections 35-40)

**PASS.** `npx playwright test --project=chromium` → all scenarios green, including the new `E2E-08` (2 scenarios: full workflow with a real browser download, and draft-exclusion). Zero `page.evaluate()` state injection; the export itself is proven via a real click + Playwright's real `page.waitForEvent('download')`, not a direct API call. A genuine, only-visible-in-a-real-browser bug was found and fixed: `Content-Disposition` was not exposed via CORS, so the frontend could not read the real export filename cross-origin — fixed with `expose_headers=["Content-Disposition"]` in `main.py`, re-verified passing after the fix. All 13 pre-existing scenarios remain green (15 total).

## Migration

**PASS — no migration required (R8 section 46), as documented in advance.** R8 introduces zero new SQLAlchemy models; `ResultsService` reads exclusively from tables R1–R7 already created. `alembic heads` remains `c61d4d05e4c9` (unchanged from the R7 baseline) throughout this release.

## CI compatibility

**PASS (by construction).** Zero new backend or frontend dependencies (confirmed via `git status` on `requirements.txt`/`package.json`/`package-lock.json` — neither touched). No GPU, no external API, no customer/private plan data.

## Scope compliance

**PASS.** No detection/matching/quantity algorithm redesign, no R9 export-redesign/PDF-reporting/ML/embeddings/new-library-scope/automatic-material-truth/automatic-acceptance/async-infrastructure/microservice-split. Reviewed every file changed in this release.

---

## Deferred technical debt

- No override exists to export DRAFT results — by design; a future release may add one if a real product need appears.
- The legacy `/export-excel` MVP path and the new `/results/export` authoritative path remain two separate, unconsolidated export experiences — consistent with R6/R7 leaving their own review experiences unconsolidated; a future release should decide whether to merge them.
- Material grouping identity is exact-match `(material_name, material_code)` only — no fuzzy/normalized matching.

## Risks before R9

- If a future release changes `calculation_version`'s semantics, the Audit sheet's per-row `Calculation Version` column is the only place that distinction is currently visible in an export — worth double-checking that's sufficient before relying on mixed-version exports.
- `ResultsService`'s batched-query approach (not SQLAlchemy relationships) works well at the scale measured here (up to 1,000 rows); if a future project's result count grows dramatically beyond that, worth re-measuring rather than assuming linear scaling holds.
- The CORS `expose_headers` fix widens what's visible to any cross-origin caller reading responses from this API, not just the Results export — a reasonable, narrow addition (one header name), but worth being aware of if CORS policy is ever tightened.

---

**No R9 work (further export redesign, PDF reporting, ML segmentation, embeddings, automatic acceptance, global library, async infrastructure, microservice split) was introduced.** STOP here.
