# R3 — Legend Workflow Core: Checklist

Date: 2026-08-25
Repository: `C:\Users\kalid\MassIQ`, branch `feature/r3-legend-workflow` (created from `main` after fast-forward-merging `release/r1-r2-foundation`)
Scope: persisted Plan Page → select hatch pattern → select description → OCR → correct → confirm material → persist `LegendEntry`. No R4/R5 features introduced (see the explicit exclusion list at the end).

Status legend: **PASS** (executed with evidence), **FAIL**, **BLOCKED**, **DEFERRED**. PASS requires executed evidence, not code inspection alone.

---

## Branch correct

**PASS.** `git rev-parse --show-toplevel` → `C:/Users/kalid/MassIQ`. `release/r1-r2-foundation` was confirmed NOT merged into `main` (`git merge-base --is-ancestor` returned false) before this release started — per the task's explicit precondition, this was surfaced to the user, who approved a fast-forward merge (`git merge --ff-only`, zero conflicts possible since `main` was a direct ancestor). `feature/r3-legend-workflow` was created from `main` only after that merge and the full baseline re-verification below.

## Baseline tests green

**PASS.** Re-verified on `main` immediately after the merge, before creating the feature branch: `alembic current`/`heads` → `709345772063 (head)`; `python -m unittest discover` → **125 tests, 0 failures**; `npm run build` → 85 modules, 0 errors; live check of the R2.5 preview endpoint (`GET .../pages/1/preview` → 200) against a real uploaded plan.

## Migration up/down/up

**PASS.** New migration `15bc524c492f` (`down_revision = 709345772063`), generated via `alembic revision --autogenerate` then hand-fixed with the same enum-drop-on-downgrade pattern both prior migrations needed (autogenerate never emits it). Executed against the real dev Postgres: `upgrade head` created `legend_entries` with all 22 columns, 3 FKs (`project_id`/`plan_id`/`plan_page_id`, all `ON DELETE CASCADE`), and 3 indexes exactly matching the ORM model; `downgrade -1` removed the table AND the `legend_entry_status` enum type (`\dT+` confirmed 0 rows afterward) while leaving `projects`/`plans`/`plan_pages` untouched; `upgrade head` again succeeded cleanly. Re-executed a second time from a genuinely empty ephemeral Postgres instance (see CI-compatible commands below) to prove the full 3-migration chain (`None → 72c82e8ce581 → 709345772063 → 15bc524c492f`) bootstraps cleanly, not just incrementally on an already-migrated DB.

## LegendEntry persistence

**PASS.** `test_legend_service.py::RetrievalAndIsolationTests::test_persists_across_a_brand_new_engine_and_session` proves cross-engine persistence (mirrors R1's proof). Additionally, live end-to-end: created a confirmed LegendEntry via the running HTTP API against the real `test_plan/floorplan.pdf`, killed the server process entirely, started a fresh process on a different port, and re-fetched the same entry — every field (status, corrected text, material, both crop presence flags, raw OCR text) was intact. See "Manual real-plan validation" below for the full transcript.

## Pattern crop

**PASS.** `test_legend_crop_service.py` proves the correct pixel region is actually cropped (a red/blue split test image, cropping each half and asserting the resulting pixel color) — not just that some bytes come back. `test_legend_service.py::SelectionAndCropTests::test_save_pattern_selection_persists_fields_and_file` and the route-level `test_legend_routes.py::test_get_pattern_crop_returns_png` (asserts real PNG magic bytes) both pass. Live-verified against the real floorplan (50,722-byte real PNG returned).

## Description crop

**PASS.** Same evidence pattern as pattern crop, plus: description crops are the ones OCR actually reads (see OCR below) — proving the stored crop is the real selected region, not a placeholder. Live-verified against the real floorplan (10,136-byte real PNG returned).

## OCR success

**PASS.** `test_ocr_service.py::RealRapidOcrProviderTests` — real (non-mocked) inference on a generated text image reads back the expected text at confidence >0.5, no technical error. Live, on the real floorplan's title-block crop: `rapidocr` returned real (imperfect, as expected of OCR on a compressed scan) text at confidence 0.86, `ocr_error: null`.

## OCR failure / manual fallback

**PASS.** `test_legend_service.py::OcrTests::test_ocr_failure_still_allows_manual_correction_and_confirmation` — forces the OCR provider to raise, confirms `raw_ocr_text` stays `null`, `status` still advances to `OCR_COMPLETE` (the *step* happened even though it produced nothing usable), and then proves the user can still type a correction, set material info, and successfully confirm the entry despite the OCR failure. `OcrService.extract_text` never raises (`test_ocr_service.py::OcrServiceFakeProviderTests::test_provider_exception_never_propagates`).

## User correction persistence

**PASS.** `test_legend_service.py::OcrTests::test_raw_ocr_text_never_overwritten_by_correction` — proves `raw_ocr_text` and `corrected_text` are independently persisted provenance, not one field overwriting the other. Route-level `test_patch_updates_corrected_text_and_material` confirms the same over HTTP.

## Material confirmation persistence

**PASS.** `test_legend_service.py::ConfirmationTests` — confirm requires pattern + description + non-blank corrected text + non-blank material name (each checked independently, with specific reasons returned on failure); `test_cannot_silently_confirm_via_update` proves `PATCH` alone can never flip status to `CONFIRMED` — only the explicit `/confirm` call can. Live: `thickness_mm=365` and `material_name="Mauerwerk (Aussenwand)"` both survived the process restart described above.

## Ownership isolation

**PASS.** `test_legend_service.py::CreateDraftTests::test_cannot_create_for_plan_belonging_to_another_project`, `RetrievalAndIsolationTests::test_entry_from_other_plan_is_not_found_via_wrong_plan_id`, `test_entry_from_other_project_is_not_found` — all reuse `PlanService.get_plan`'s existing isolation check rather than duplicating logic. Route-level `test_legend_routes.py::test_cross_project_access_returns_404` confirms the same over HTTP.

## Crop bounds validation

**PASS.** Three independent layers, all tested: (1) Pydantic `Field` constraints reject negative coordinates and zero-size selections at the HTTP boundary (`test_negative_coordinate_returns_400` — actually 422, Pydantic's own validation code; `test_zero_size_selection_returns_422`); (2) `RegionSelection.__post_init__` (service layer, defense in depth, tested directly and via the route for the "extends past page" case Pydantic's per-field constraints can't express — `test_selection_extending_past_page_returns_400`); (3) `LegendCropService.crop_region`'s own pixel-level check. 9/9 `test_legend_crop_service.py` tests pass.

## Normalized coordinate tests

**PASS.** `frontend/src/features/legend/coordinates.test.js` — the central assertion: the identical proportional drag at two very different `viewSize`s (simulating "preview displayed at another size") produces the identical normalized rect. Also covers minimum-drag-size rejection, missing-natural/view-size handling, and edge clamping.

## Frontend quantity tests

**PASS.** `frontend/src/utils/quantityEngine.test.js` — 5 tests covering `final_area_m2 = accepted + added - subtracted`, `volume_m3 = final_area_m2 × height`, combined, zero/undefined-input safety, and the deterministic-source tag.

## Frontend legend tests

**PASS.** `frontend/src/features/legend/LegendEntryEditor.test.jsx` — 5 tests, including the required "OCR text → user edits → confirmed value uses edited text" case: renders with a deliberately OCR-garbled `raw_ocr_text`, simulates the user clearing and retyping the textarea, and asserts the value passed to `onSaveCorrection` is the edited text, not the original OCR string.

## Backend full suite

**PASS.** **177 tests, 0 failures** — 125 baseline (R1/R2/R2.5) + 52 new R3 tests (4 `test_ocr_service.py` + 9 `test_legend_crop_service.py` + 20 `test_legend_service.py` + 19 `test_legend_routes.py`), executed against the real dev Postgres, then re-executed a second time end-to-end against a genuinely fresh ephemeral Postgres instance (`ci-check-postgres-r3`, migrated from empty) to prove clean-checkout reproducibility — both runs green.

## Frontend build

**PASS.** `npm run build` → 95 modules (85 baseline + 10 new R3 feature files), 0 errors.

## CI-compatible commands

**PASS.** Full CI simulation re-run for R3, exactly as done for R2.5: a fresh `postgres:16-alpine` container on an unused host port, `alembic upgrade head` from empty (all 3 migrations), full backend suite, `npm ci` (clean lockfile-only install after `npm install` regenerated `package-lock.json` for the 5 new devDependencies: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`), `npm test`, `npm run build`. `.github/workflows/ci.yml` updated with one new `npm test` step in the frontend job; no other CI structure changes.

## Old MVP regression

**PASS.** Live, after every R3 change: `/upload-pdf` (valid → 200, fake `.pdf` → 400) → `/rendered-page/{id}` (200) → `/save-hatch-sample` (200) → `/detect-hatch` (200) → `/export-excel` (200, real `.xlsx`).

## Project/Plan regression

**PASS.** Live: `POST /api/projects`, `POST /api/projects/{id}/plans`, `GET .../pages/{n}/preview` all still 200 with the real floorplan PDF. Route-level `test_legend_routes.py::test_existing_plan_and_project_routes_unaffected` covers this automatically too.

## No R4/R5 features introduced

**PASS.** Reviewed every file changed in this release: no hatch-angle/line-spacing/density/periodicity extraction, no embeddings, no similarity search, no pattern library (project/office/company/global), no tile-based detection, no similarity heatmap, no automatic material decision anywhere. The pattern crop is stored (for a *future* release to extract features from) but nothing in R3 reads it for anything beyond display.

---

## Manual real-plan validation

Per the explicit instruction not to fake success: `test_plan/floorplan.pdf`'s rendered preview was visually inspected (rendered at 144 DPI and 300 DPI, several regions cropped and viewed) before writing this section. **Finding: this real scanned floor plan does not contain an unambiguous, classic "hatch-pattern-sample next to its text label" legend box** at the resolution the scan was captured at — it has room/apartment schedule tables (unit numbers and areas, not hatch definitions) and a standard German architectural title block (project name, sheet number, scale, date), plus real wall cross-hatching within the drawing itself. This is reported honestly rather than assumed away.

Given that, the manual validation performed is an **infrastructure smoke test using real regions of this real file** (not a legend-content validation, since no legend exists to validate against):

- **Pattern region**: a real cross-hatched wall/material area within the plan drawing (normalized `x=0.3266, y=0.4618, width=0.1485, height=0.1259`).
- **Description region**: the real, legible title-block text ("Grundriss Erdgeschoss", "Ausführungsplanung", project/sheet numbers, date, scale) (normalized `x=0.727, y=0.705, width=0.1568, height=0.0806`).

Full sequence executed against a live server with this real PDF: `POST /api/projects` → `POST .../plans` (real file, `pdf_type: raster`) → `POST .../legend-entries` (draft) → `POST .../pattern` → `POST .../description` → `POST .../ocr` → **real OCR output**: `"YORA\nGrundriss Erdgeschoss\nAusfuhru\n2123.055\nBR-EI\n74002024\nM15I\nMMIPZ"` at confidence 0.79–0.86 (genuinely imperfect — "VORABZUG" read as "YORA", "2023-058" read as "2123.055" — exactly the kind of error the human-correction step exists for) → `PATCH` with a human-corrected description (`"Grundriss Erdgeschoss, Ausfuehrungsplanung, Projekt 2023-058, Blatt GR-ED, 24.09.2024, M 1:50"`) and material (`"Mauerwerk (Aussenwand)"`, `thickness_mm: 365`) → `POST .../confirm` → `status: confirmed`. Both crop GET endpoints returned real PNGs (50,722 and 10,136 bytes). The confirmed entry was then re-fetched successfully after killing and restarting the backend process entirely (different port, fresh process) — full persistence proof on real, non-synthetic bytes.

**Conclusion:** the plumbing (upload → selection → crop → OCR → correction → confirmation → persistence) is proven end-to-end on a real file. The *content* of a real hatch-pattern legend has not been validated because no such legend was available in this environment — flagged honestly as an open item, same spirit as R2's classifier-calibration gap.

---

## Deferred technical debt

- `requirements-minimal.txt` reconciliation — still not touched (R2.5 decision, unchanged).
- `npm audit` findings — now 8 (was 7 after R2.5; the new frontend test tooling added one more, a transitive dependency) — not remediated, consistent with the standing decision not to do dependency cleanup inside a feature release.
- Frontend `LegendEntryEditor.test.jsx` shows a harmless React "not wrapped in act(...)" console warning during `userEvent` interactions (all assertions still pass) — a known, cosmetic interaction between this `@testing-library/user-event`/`@testing-library/react`/React 18 version combination; not a real bug, not chased further given no failing assertion.
- No composite DB constraint enforcing `plan_page.plan_id == legend_entry.plan_id` at the schema level — deliberately not added (see the coordinate/ownership design section of the implementation plan); ownership is enforced in the service layer instead, per the task's own instruction.
- `LegendFeaturePage.jsx`'s Project/Plan/Page picker is intentionally minimal (plain `<select>`s, no pagination, no search) — functional, not polished, per R3's explicit scope boundary.
- No interactive/headed-browser click-through of the frontend was performed (no browser automation tooling exercised in this environment beyond the existing Playwright *devDependency*, which was not invoked — full E2E infra is explicitly deferred per the task's own instruction). Frontend correctness for R3 rests on: a clean production build, the Vitest/RTL suite, and a byte-for-byte comparison of `features/legend/api.js`'s request shapes against the live-verified backend contract.

## Risks before R4

- **No real hatch-pattern legend has been validated end-to-end** — only infrastructure-level real-file validation exists (see above). Before R4 (Hatch Feature Engine) invests in extracting features from stored pattern crops, it would be valuable to source at least one real plan with an actual legend box to confirm the two-selection UX produces genuinely useful crops in practice, not just structurally valid ones.
- **`pdf_type` remains advisory** (per R2.5's calibration gap, unchanged) — R3 correctly never branches on it for anything load-bearing, but this constraint should stay visible to whoever scopes R4+.
- **OCR latency** (~2s per call, cold engine load ~0.9s the first time) is fine for a single-user synchronous MVP request but would need reconsidering if R4+ ever needs to OCR many crops in bulk — no action needed now, flagged for later.
