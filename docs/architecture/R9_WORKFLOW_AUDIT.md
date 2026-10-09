# R9 — Pre-Implementation Workflow Audit

Date: 2026-08-28
Branch: `feature/r9-workflow-product-hardening` (from `main`, which now includes R1–R8; baseline re-verified green before this audit: 600 backend tests, 52 Vitest, 101-module build, 15 Playwright — see the R9 checklist for the fast-forward-merge story).

Scope of this document: satisfy R9 sections 3–4 — inspect the actual repository (not old docs, not memory) and record the real current state before any implementation. Every claim below is backed by a file path (and line numbers for larger files). Nothing here is prescriptive; architecture decisions belong to a follow-up design pass.

---

## 0. Stray/noise directories (checked first, so they're not mistaken for in-scope code)

- `_backup_before_flatten/`, `_recovery_candidates/`, `_live_before_validated_restore_20260513_080814*/`, `massiq-mvp/` at the repo root: all explicitly gitignored (`.gitignore` lines 48–51). Not tracked, not part of any release. Ignore for R9.
- `backend/backend/app/detection/` (nested duplicate path): untracked, **empty** (zero files under it, confirmed via `find -type f`). Filesystem cruft, not gitignored but harmless. Ignore for R9; not worth a cleanup commit on its own but flag if anyone else touches it.

---

## 1. Actual current user paths (13 stages)

| # | Stage | Legacy MVP implementation | R1–R8 implementation |
|---|---|---|---|
| 1 | Project creation | *(none — legacy has no Project concept)* | `LegendFeaturePage.jsx:71-85` (`handleCreateProject`) → `POST /api/projects` (`backend/app/routes/projects.py:19`) |
| 2 | Plan upload | `UploadPanel.jsx:23-43` → `POST /upload-pdf` (`main.py:75`, ephemeral `file_id`, no DB row) | `LegendFeaturePage.jsx:87-101` (`handleUploadPlan`) → `POST /api/projects/{project_id}/plans` (`routes/plans.py:27`), persists `Plan`+`PlanPage` rows |
| 3 | Plan preview | `UploadPanel.jsx:88` renders `<PlanViewer file_id=... page_image_url=...>`; image served via `GET /rendered-page/{file_id}` (`main.py:106`) | `LegendFeaturePage.jsx:104` builds `previewUrl` via `legendApi.planPagePreviewUrl`; served by `GET /api/projects/{p}/plans/{pl}/pages/{n}/preview` (`routes/plans.py:75`) |
| 4 | Scale preparation | `PlanViewer.jsx` — in-memory `scale.pixelsPerMeter` typed by the user, **never sent to backend** (per CLAUDE.md and confirmed in code — no scale API call in `PlanViewer.jsx`) | Persisted `PlanScale` (R7). UI is **not a separate stage** — the scale-confirm form lives *inside* `QuantityPanel.jsx` (rendered from `LegendWorkspace.jsx:604-619`), gated behind `detectionRun.status === 'completed'`. Backend: `GET/PUT /api/projects/{p}/plans/{pl}/pages/{n}/scale` (`routes/plan_scale.py:40,53`) |
| 5 | Legend creation | `LegendAssistantPanel.jsx` (138 lines) — draws legend-area + hatch-sample bbox directly on the plan image, calls `/save-hatch-sample`; no OCR, no material confirmation, no persistence | `LegendWorkspace.jsx` (623 lines, see §5) + `LegendEntryEditor.jsx` (253 lines) + `LegendEntryList.jsx`. Full pattern→description→OCR→correct→confirm flow. Backend: `routes/legend_entries.py` (11 endpoints) |
| 6 | Hatch feature computation | *(none)* | `LegendEntryEditor.jsx` "Compute features" button → `handleComputeFeatures` in `LegendWorkspace.jsx:269-281` → `POST /api/.../legend-entries/{id}/features` (`routes/hatch_features.py:40`) |
| 7 | Pattern Library | *(none)* | `handleAddToLibrary` (`LegendWorkspace.jsx:283-296`) → `POST /api/.../features` `/library` endpoint (`routes/pattern_matches.py:49`); browsed via `PatternLibraryPanel.jsx` (70 lines) → `GET /api/projects/{p}/pattern-library` (`routes/pattern_library.py:20`) |
| 8 | Detection | `HatchDetectionPanel.jsx` (140 lines) — template-match via `POST /detect-hatch` (`routes/detection.py`), returns raw bboxes, nothing persisted | `DetectionPanel.jsx` (86 lines, rendered only once `hatchFeatures` truthy — `LegendWorkspace.jsx:576-587`) → `POST /api/.../pages/{n}/detection-runs` (`routes/detection_runs.py:65`), persists `DetectionRun`+`DetectedRegion` rows |
| 9 | Review (accept/reject) | `DetectionReviewPanel.jsx` (60 lines) — frontend-only accept/reject array, never persisted | Region status PATCH inside `DetectionPanel.jsx` → `PATCH /api/.../detection-runs/{id}/regions/{region_id}` (`routes/detection_runs.py:140`), persists `DetectedRegionStatus` |
| 10 | Manual ADD/SUBTRACT | `RegionEditor.jsx` (104 lines) — frontend-only `corrections` array (see CLAUDE.md's documented state table) | `ManualCorrectionPanel.jsx` (94 lines, rendered only once `detectionRun.status === 'completed'` — `LegendWorkspace.jsx:589-602`) → `POST/GET/DELETE /api/.../detection-runs/{id}/manual-corrections` (`routes/manual_corrections.py`) |
| 11 | Quantity | `quantityEngine.js` — pure frontend function, `SectionHeightPanel.jsx` (23 lines) for height input, **volume never touches backend** (CLAUDE.md, confirmed unchanged) | `QuantityPanel.jsx` (211 lines) → `POST/GET /api/.../detection-runs/{id}/quantity` + `/quantity/confirm` (`routes/quantity.py`), persists `QuantityResult` (DRAFT/CONFIRMED) |
| 12 | Results | *(none — legacy has no results list, only the one just-computed value in `PlanViewer` state)* | `ResultsPanel.jsx` (186 lines, project-scoped, rendered at the bottom of `LegendFeaturePage.jsx:201`) → `GET /api/projects/{p}/results` (`routes/results.py:42`) |
| 13 | Excel export | `ExportButton.jsx` (50 lines) → `POST /export-excel` (`routes/export.py`), trusts frontend-computed `area_m2`/`volume_m3` with zero backend verification (documented, unchanged, in R8 checklist) | Export button inside `ResultsPanel.jsx` → `POST /api/projects/{p}/results/export` (`routes/results.py:57`), CONFIRMED-only, backend-authoritative values |

---

## 2. State ownership table

| Stage | Persisted (table.column) | Frontend-only | Resets on refresh? |
|---|---|---|---|
| Project | `projects` (R1) | — | No — `LegendFeaturePage` re-fetches `listProjects()` on mount, but the **selected** `projectId` itself is plain `useState`, so the open project is lost on refresh (must re-pick from the dropdown). No router/URL param carries it. |
| Plan | `plans`, `plan_pages` | — | Same as above: persisted rows survive; the **selection** (`planId`, `pageNumber`) is component state, lost on refresh. |
| Legacy plan (MVP) | *(nothing — no DB row at all)* | `file_id`, `page_image_url` | `UploadPanel.jsx:13-21` persists the **last** upload's `file_id` to `localStorage` (`massiq-last-upload-result`) and restores it on mount — the only piece of cross-refresh state in the entire legacy flow, and it only remembers one upload globally (not per-project). |
| Scale (new) | `plan_scales.real_meters_per_plan_point` etc. (R7) | — | No — re-fetched by `LegendWorkspace.jsx:130-142` on every mount via `getPlanScale`, 404 treated as "not yet confirmed" (swallowed). |
| Scale (legacy) | *(never persisted)* | `scale.pixelsPerMeter` in `PlanViewer.jsx` | Yes — always lost on refresh, by design (CLAUDE.md). |
| Legend entry | `legend_entries.*` (pattern/description rects, OCR text, material, status) | `activeEntryId` (which entry is selected in the UI) | Entry data survives; the **active selection** does not (component state). |
| Hatch features | `hatch_feature_sets.*` (R4) | — | Re-fetched by `LegendWorkspace.jsx:86-98`, best-effort (404 = not computed yet, not an error). |
| Pattern Library | `pattern_library_entries.*` (R5) | `inLibrary` boolean cache in `LegendWorkspace.jsx:50` | `inLibrary` is set only on successful `handleAddToLibrary` in the current session — **not re-derived from the backend on mount**, so after a refresh the UI can't tell "already in library" without the user re-clicking (a real gap; worth checking during implementation, not just documenting). |
| Detection run | `detection_runs.*`, `detected_regions.*` (R6) | — | Re-discovered via `listDetectionRunsForPage` (`LegendWorkspace.jsx:103-123`) — picks the **most recent** run for the page, nothing lost. |
| Detection (legacy) | *(never persisted)* | raw bbox array in `PlanViewer.jsx` | Yes — always lost. |
| Manual corrections | `manual_region_corrections.*` (R7) | — | Re-fetched alongside quantity (`LegendWorkspace.jsx:148-168`), scoped to the rediscovered `detectionRun.id`. |
| Manual corrections (legacy) | *(never persisted)* | `corrections` array in `PlanViewer.jsx` | Yes. |
| Quantity | `quantity_results.*` (DRAFT/CONFIRMED, R7) | — | Re-fetched with manual corrections (same effect). Recalculation server-side resets `status` to DRAFT and clears `confirmed_at` (`quantity_service.py:161`, confirmed by reading the service, not just the docstring). |
| Quantity (legacy) | *(never persisted, never sent to backend at all — CLAUDE.md's explicit design)* | `heightMeters`, `heightConfirmed`, computed `final_area_m2`/`volume_m3` | Yes. |
| Results | Derived read of `quantity_results` (no new table, R8) | `resultsVersion` counter (`LegendFeaturePage.jsx:31`) used only to force a re-fetch after mutations elsewhere | List itself always reflects current DB truth on fetch. |

**Overall finding:** every persisted entity in the R1–R8 path correctly survives a refresh (services re-derive from the DB, not from client cache). The thing that does **not** survive refresh is *navigational context* — which project/plan/page/legend-entry the user had open — because there is no router and no URL state (see §7 open question). This matches R9 §30's concern directly.

---

## 3. Legacy vs new overlap — KEEP/ADAPT/DEPRECATE/REMOVE

| Legacy piece | Duplicates | Recommendation | Evidence |
|---|---|---|---|
| `UploadPanel.jsx` + `/upload-pdf` | Plan upload (new: `LegendFeaturePage` + `POST /plans`) | **DEPRECATE** (do not remove) | Still covered by a dedicated E2E spec, `e2e/specs/legacy-workflow.spec.js`, and by `test_legacy_upload_pdf.py` (mentioned in R2.5 checklist) — active test dependency. Also the hardcoded fake `workflow-grid` in `UploadPanel.jsx:47-63` (8 steps, statically `'In progress'`/`'Not started'`, not derived from anything) is a concrete example of exactly the anti-pattern R9 §6 warns against — worth citing when designing the real workflow-state UI. |
| `PlanViewer.jsx` (667 lines) | Preview/Detection/Review/Corrections/Quantity/Export, all frontend-ephemeral | **DEPRECATE** | Same E2E dependency as above (`legacy-workflow.spec.js` drives this exact component). Zero DB persistence by design — cannot be silently merged into the new flow without a real migration decision, which R9 explicitly forbids inventing ad hoc (§32). |
| `LegendAssistantPanel.jsx`, `HatchDetectionPanel.jsx`, `DetectionReviewPanel.jsx`, `RegionEditor.jsx`, `SectionHeightPanel.jsx`, `ExportButton.jsx` | Legend/Detection/Review/Corrections/Height/Export, respectively | **DEPRECATE** (children of `PlanViewer`, same reasoning) | Only reachable through `PlanViewer.jsx`; no independent test coverage found calling them outside that tree. |
| `/upload-pdf`, `/rendered-page/{id}`, `/suggest-plan-scale/{id}`, `/analyze-section/{id}`, `/detect-hatch`, `/save-hatch-sample`, `/export-excel` (legacy backend routes) | Their new-path equivalents | **KEEP the endpoints, DEPRECATE the UI path to them** | R8 checklist explicitly re-confirmed "zero diff" on `export.py`/`excel_service.py`/`ExportButton.jsx` and documented the two export paths as "two separate, unconsolidated export experiences" left for a future release to reconcile — i.e. removal was already considered and deliberately deferred, not overlooked. No evidence search found any other code depending on these routes besides the legacy frontend components and `legacy-workflow.spec.js`/`invalid-upload.spec.js`. |
| `quantityEngine.js` | New: `QuantityService` (backend) | **KEEP as-is (legacy-scoped only)** | Still imported by `PlanViewer.jsx` and covered by `quantityEngine.test.js`; the one other hit (`DetectionPanel.jsx:13`) is a comment only, not an import — no accidental coupling between the two quantity systems. |

**No REMOVE recommendation for any file.** Per R9 §4's evidence bar, nothing found in this audit proves the legacy path has zero remaining dependents — the opposite: `legacy-workflow.spec.js` and `invalid-upload.spec.js` actively exercise it, and removing it would fail "Keep existing E2E suite" (§42) unless those specs are also deliberately retired with their own justification, which is a product decision, not an audit finding.

---

## 4. Duplicated workflow controls, dead-end navigation, hidden prerequisites

- **Two upload UIs on the same screen.** `App.jsx` renders `<UploadPanel/>` then `<LegendFeaturePage/>` unconditionally, stacked vertically (`App.jsx:19-22`). A first-time user sees two "upload a PDF" affordances with no explanation of which one matters, no shared state, no navigation between them.
- **A fabricated progress indicator that lies.** `UploadPanel.jsx:47-63` renders an 8-step "Plan / Scale / Legend / Detection / Review / Height / Quantity / Export" grid where every step after the first is hardcoded `'Not started'` regardless of actual state — it never updates even after upload succeeds. This is the single clearest concrete example of the R9 §6 anti-pattern ("Do not base stage completion on arbitrary frontend booleans") already present in the codebase.
- **Scale confirmation is hidden inside Quantity, not its own stage.** `QuantityPanel.jsx` (rendered from `LegendWorkspace.jsx:604-619`) is the *only* place a user can confirm `PlanScale`, and that panel itself is gated behind `detectionRun && detectionRun.status === 'completed'` (`LegendWorkspace.jsx:589,604`). Concretely: **a user cannot confirm scale until after they have already run Detection V2** in the current UI, even though the backend has no such ordering requirement (`PUT /pages/{n}/scale` has no dependency on any `DetectionRun`). This is a hidden prerequisite the R9 spec explicitly asks to eliminate (§7, §11) — Plan Preparation should be reachable and completable right after Plan upload.
- **No visible reason when Detection/Analysis is blocked.** `DetectionPanel` only renders when `hatchFeatures` is truthy (`LegendWorkspace.jsx:576`) — if a user hasn't computed hatch features yet, the Analysis control simply **does not appear**, with no message explaining why (violates R9 §7's "bad UX: hidden, not explained" guidance). Contrast with the backend, which *does* raise a specific, well-designed error (`ReferenceFeatureVersionOutdatedError`, `detection_service.py:91-112`) when features are stale — that good backend error message is never surfaced distinctly in the frontend today; `extractErrorMessage` (`LegendWorkspace.jsx:20-26`) would just dump the raw `"REFERENCE_FEATURE_VERSION_OUTDATED: reference was computed with feature_version=...`" string into the generic error banner, exactly the "bad UX" example R9 §15 warns against.
- **Manual corrections gated behind a run being `completed`**, same pattern as scale (`LegendWorkspace.jsx:589`) — reasonable in isolation, but combined with the scale-in-quantity issue above, a user's forced path today is: Legend → Features → Library(optional) → **Detection** → Review → **then** Scale → Quantity — i.e. Plan Preparation is effectively stage 7 of 8, not stage 3, contradicting the intended canonical order in R9 §5.
- **No dead navigation links found** (there is no navigation/router at all yet — see §7), so there's nothing to click into a dead end; the risk is entirely the reverse (no way to jump anywhere except by re-selecting dropdowns).

---

## 5. Oversized / multi-responsibility components

| File | Lines | Distinct responsibilities mixed together |
|---|---|---|
| `frontend/src/features/legend/LegendWorkspace.jsx` | 623 | (1) plan-image rendering + 3 kinds of overlay drawing (pattern/description/detection/manual, `:475-519`), (2) pointer-selection mode state machine (via `usePageSelection`), (3) Legend CRUD orchestration (create/OCR/correct/confirm, `:214-267`), (4) hatch-feature compute (`:269-281`), (5) Pattern Library add (`:283-296`), (6) Detection run lifecycle (`:298-330`), (7) manual correction CRUD (`:332-344`), (8) **Plan Preparation / scale confirmation** (`:346-370`), (9) Quantity calculate+confirm (`:372-400`), (10) review-count aggregation (`:402-408`). Ten of R9's eight target stages are represented in one component. |
| `frontend/src/components/PlanViewer.jsx` | 667 | Legacy equivalent of the above for the old pipeline: legend-assistant hookup, hatch detection, review, correction drawing, height confirmation, quantity math, export — the same "one component owns the whole pipeline" shape, just for the legacy path. |
| `frontend/src/features/legend/api.js` | 266 | Not oversized by responsibility (it's a flat API client), but notable that **every** R3–R8 endpoint (legend, features, library, detection, scale, corrections, quantity) lives in one undifferentiated file with no per-stage grouping — makes it harder to tell which calls belong to which future stage component. |
| `frontend/src/features/legend/LegendFeaturePage.jsx` | 204 | Project/Plan/Page selection (three concerns) + mounting `LegendWorkspace` + mounting `PatternLibraryPanel` + mounting `ResultsPanel` — this is closer to what a real "ProjectWorkflow" shell should look like, but currently has zero stage-awareness (no completion state, no blocking, no next-action guidance — everything is always rendered if its data exists). |

`LegendEntryEditor.jsx` (253) and `QuantityPanel.jsx` (211) are borderline but each still maps to a single coherent stage (Legend, Quantity respectively) — not flagged for extraction, just noted as the largest "normal" files for scale comparison.

---

## 6. Full backend route inventory

**Legacy (`main.py`, no `/api` prefix):**
- `GET /`
- `GET /health`
- `POST /upload-pdf`
- `GET /rendered-page/{file_id}`
- `POST /suggest-plan-scale/{file_id}`
- `POST /analyze-section/{section_file_id}`

**`routes/detection.py`** (legacy hatch detection, no prefix beyond root — mounted first in `main.py:49`): `/save-hatch-sample`, `/detect-hatch` (exact paths not re-derived here since unchanged since R0; see file directly if needed).

**`routes/export.py`** (legacy export): `/export-excel` (unchanged since R0/R8 audit — zero diff confirmed by R8 checklist).

**`routes/vlm.py`** (`/vlm` prefix): optional AI analysis endpoints, unchanged.

**`routes/projects.py`** — prefix `/api/projects`:
- `POST ""` (create)
- `GET ""` (list)
- `GET "/{project_id}"`
- `PATCH "/{project_id}"`

**`routes/plans.py`** — prefix `/api/projects/{project_id}/plans`:
- `POST ""`
- `GET ""`
- `GET "/{plan_id}"`
- `GET "/{plan_id}/pages"`
- `GET "/{plan_id}/pages/{page_number}/preview"`

**`routes/legend_entries.py`** — prefix `/api/projects/{project_id}/plans/{plan_id}/legend-entries`:
- `POST ""`, `GET ""`, `GET "/{legend_entry_id}"`, `PATCH "/{legend_entry_id}"`
- `POST "/{legend_entry_id}/pattern"`, `GET "/{legend_entry_id}/pattern"`
- `POST "/{legend_entry_id}/description"`, `GET "/{legend_entry_id}/description"`
- `POST "/{legend_entry_id}/ocr"`
- `POST "/{legend_entry_id}/confirm"`

**`routes/hatch_features.py`** — prefix `.../legend-entries/{legend_entry_id}/features`:
- `POST ""`, `GET ""`

**`routes/pattern_library.py`** — prefix `/api/projects/{project_id}/pattern-library`:
- `GET ""`

**`routes/pattern_matches.py`** — prefix `.../legend-entries/{legend_entry_id}`:
- `POST "/library"`, `POST "/matches"`, `POST "/match-decision"`, `GET "/match-decisions"`

**`routes/detection_runs.py`** — two routers:
- `page_router`, prefix `.../pages/{page_number}/detection-runs`: `POST ""`, `GET ""`
- `run_router`, prefix `.../plans/{plan_id}/detection-runs`: `GET "/{run_id}"`, `GET "/{run_id}/regions"`, `PATCH "/{run_id}/regions/{region_id}"`

**`routes/plan_scale.py`** — prefix `.../pages/{page_number}/scale`:
- `GET ""`, `PUT ""`

**`routes/manual_corrections.py`** — prefix `.../detection-runs/{run_id}/manual-corrections`:
- `POST ""`, `GET ""`, `DELETE "/{correction_id}"`

**`routes/quantity.py`** — prefix `.../detection-runs/{run_id}/quantity`:
- `POST ""`, `GET ""`, `POST "/confirm"`

**`routes/results.py`** — prefix `/api/projects/{project_id}/results`:
- `GET ""`, `POST "/export"`, `GET "/export/preflight"`, `GET "/{quantity_result_id}"`

This gives a clean, already-consistent `/api/projects/{project_id}/...` nesting for everything R1–R8 — a workflow-summary endpoint (R9 §21, if pursued) would naturally live at `GET /api/projects/{project_id}/workflow` alongside these.

---

## 7. Open questions requiring a product decision

1. **Router or no router?** There is currently zero client-side routing (confirmed: no `react-router` in `package.json` dependencies — not checked exhaustively here, verify before deciding). R9 §30 permits either preserving refresh-context without a full router migration, or introducing one "if not already justified." Given the navigation-loss issues in §2/§4, at minimum the selected `projectId`/`planId`/`pageNumber`/active stage should be reflected in the URL somehow (even query params without a full router) — worth a deliberate decision, not a default.
2. **Where does Plan Preparation (scale) move to, structurally?** It's currently embedded in `QuantityPanel.jsx`. R9 §11 wants it as its own visible stage, reachable right after Plan upload, not gated behind Detection. This requires extracting the scale-confirm UI out of `QuantityPanel.jsx` into its own stage component — a real (if small) refactor, not just a label change.
3. **Legacy MVP's place in the new navigation.** Should `UploadPanel`/`PlanViewer` remain reachable from the same screen (as today), move behind an explicit "legacy mode" toggle, or simply stay exactly where they are with the new workflow becoming the dominant/first-shown path? R9 §31 wants "one canonical new workflow" without removing legacy capability yet — the exact UI treatment (tab? separate route? collapsed section?) is a decision for the navigation design step, not this audit.
4. **`inLibrary` staleness on refresh** (§2) — is this a real bug worth fixing in R9, or out of scope? It's a pre-existing gap, not something R9 introduced, but R9's "no stale workflow completion indicators" principle (§22) arguably covers it since Materials-stage completion will need to read real library membership correctly after a refresh.
5. **Feature-version-outdated UX** (§4) — R9 §15 wants an actionable message with "a sensible path/action to resolve it if possible" (i.e., a link/button to go recompute features) without auto-recomputing. Where that action lives (inline in the Analysis stage's blocked-state message, or requiring the user to navigate back to Legend) is a UX decision.
6. **Workflow-summary endpoint vs. pure frontend derivation** (R9 §20–21) — given the route inventory above is already fully namespaced under `/api/projects/{project_id}/...`, a single `GET /api/projects/{project_id}/workflow` is straightforward to add, but whether it's *needed* depends on how many separate calls the new navigation UI would otherwise make per page load. Worth measuring against the real stage components once they exist, not assumed up front.

---

## Summary for the next step

Nothing here requires new algorithms, tables, or services. The dominant finding is structural: one 623-line component (`LegendWorkspace.jsx`) currently plays the role of six of R9's eight target stages, the two workflows (legacy MVP and R1–R8) are simply concatenated on one page with no shared navigation, there is no URL/router state at all, and Plan Preparation is mis-ordered behind Detection purely as an accident of where its form was dropped in JSX — not a deliberate design. All persisted domain state itself is sound and survives refresh correctly; the work is presentation/navigation/consolidation, exactly as R9's brief describes.
