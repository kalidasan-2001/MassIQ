# R9 — Workflow Consolidation & Product Hardening: Checklist

Date: 2026-08-29
Repository: `C:\Users\kalid\MassIQ`, branch `feature/r9-workflow-product-hardening` (created from `main` after fast-forward-merging `feature/r8-results-export-hardening`, per R8's independent review approval — the R7→R8 gap pattern repeated here, surfaced to the user, who approved the fast-forward).
Scope: turns the R1–R8 functional pipeline into one coherent, navigable, self-explaining product workflow. No detection/matching/quantity algorithm was redesigned; no new database table was added.

Status legend: **PASS** (executed with evidence), **FAIL**, **BLOCKED**, **DEFERRED**. PASS requires executed evidence, not code inspection alone.

---

## Branch and baseline

**PASS.** `feature/r8-results-export-hardening` was confirmed independently reviewed and approved (per its own checklist), but not yet merged into `main` — `main` still pointed at the R7 commit. Surfaced to the user; fast-forward merge (`git merge --ff-only`, zero conflicts) approved and executed. Baseline re-verified on `main` after the merge: `alembic heads` → `c61d4d05e4c9 (head)`; backend suite → 600 tests, 0 failures; `npx vitest run` → 52 passed; `npm run build` → 101 modules; `npx playwright test --project=chromium` → 15 passed. `feature/r9-workflow-product-hardening` created from `main` only after this full green baseline.

## Pre-implementation audit (R9 sections 3-4)

**PASS.** `docs/architecture/R9_WORKFLOW_AUDIT.md` — every one of the 13 listed stages traced to exact files/line numbers in the actual current code (not old docs), covering both the legacy MVP tree and the R1–R8 tree. Found: `LegendWorkspace.jsx` (623 lines) played six of R9's eight target stages; Plan Preparation was accidentally reachable only after a completed Detection run; the legacy MVP was stacked unconditionally above the new workflow with a fabricated, always-static progress grid; no router/URL state existed at all. Legacy vs. new: **KEEP** the legacy backend routes (zero diff, R8 already documented them as a deliberately unconsolidated second export path); **DEPRECATE** (not REMOVE) every legacy frontend component — `legacy-workflow.spec.js`/`invalid-upload.spec.js` actively exercise them end to end, and R9's evidence bar for removal (proof nothing depends on it) was not met.

## Canonical workflow / navigation (R9 sections 5-9)

**PASS.** `ProjectWorkflow.jsx` + `WorkflowNav.jsx` present all 8 stages (Project/Plans/Plan Preparation/Legend/Materials/Analysis/Review/Results) with an explicit text status label per stage (`Complete`/`In progress`/`Blocked` — never color alone, `WorkflowNav.test.jsx`). Blocked stages remain clickable and show a specific, actionable reason (R9 section 7's "good UX" example implemented verbatim for the feature-version-outdated case). Project landing shows plan count and a confirmed-quantity hint (`project-landing-summary`).

**Architectural correction made during implementation, documented in `PRODUCT_WORKFLOW.md` section 2:** the first implementation switched between stage panes exclusively; this broke every existing R3–R8 Playwright spec (they assume continuous visibility, matching the pre-R9 single-scrolling-page UX) by unmounting a stage's controls the instant it completed. Fixed by rendering every stage additively (all present, each showing its own blocked-reason message), with the nav serving as an orientation/scroll-to header, not a pane switcher. This is the single biggest lesson of this release and is recorded in `PRODUCT_WORKFLOW.md` so it is not reintroduced.

## Stage completion / prerequisite rules (R9 sections 6-7)

**PASS.** `deriveWorkflowStages.js` — every rule verified against the actual persisted enums (`PlanProcessingStatus`, `LegendEntryStatus`, `DetectionRunStatus`, `DetectedRegionStatus`, `QuantityResultStatus`), not invented. Materials is documented as deliberately not a hard gate for Analysis (`DetectionRun` can reference a `LegendEntry` directly — verified in the model). 17 unit tests in `deriveWorkflowStages.test.js` cover every stage transition, including the "never advance into a still-blocked stage" correction above.

## Workflow state implementation (R9 sections 20-21, 45, 47)

**PASS, documented deliberately.** No new backend endpoint, no new database table — every stage status is derived client-side in `useProjectWorkflowState.js`/`deriveWorkflowStages.js` from the same API calls the pre-R9 UI already made. A dedicated `GET /api/projects/{id}/workflow` endpoint was evaluated and explicitly deferred (`PRODUCT_WORKFLOW.md` section 9) — it would not reduce genuinely duplicated round trips, since each stage's real content still needs the same data independently.

## Project landing / Plans / Plan Preparation (R9 sections 9-11)

**PASS.** Project block shows plan count + next-action hint. `PlansStage.jsx` shows every plan's processing status, upload control, and page picker — replaces the plan `<select>` with a status-pill list per plan (a UX improvement, not just a rename). `PlanPreparationStage.jsx` extracts scale confirmation from the old `QuantityPanel.jsx` into its own stage, reachable immediately after a plan page is selected — fixes the audit-identified mis-ordering with zero new backend dependency.

## Legend / Materials stages (R9 sections 12-13)

**PASS.** `LegendStage.jsx` wraps the existing, unmodified `LegendEntryList`/`LegendEntryEditor` (select hatch → select description → OCR → correct → confirm → compute features, unchanged R3/R4 flow). `MaterialsStage.jsx` wraps the existing `PatternLibraryPanel.jsx` as a read-only browse view; "Add to library" stays on the Legend stage (immediately after feature computation, matching R9 section 19's own suggested next-action sequence) rather than being relocated. Audit-flagged `inLibrary` staleness fixed: derived from the fetched library list (`isEntryInLibrary`, unit-tested) instead of a session-only flag that forgot state across a refresh.

## Analysis / feature-version UX (R9 sections 14-15)

**PASS.** `AnalysisStage.jsx` wraps the split-out `DetectionRunPanel.jsx` (run button + status + counts; region review moved to the Review stage). `ReferenceFeatureVersionOutdatedError`'s route mapping now returns a structured `{error_code, message, ...}` detail (only backend change in this release besides tests); the frontend renders the friendly message plus a "Go to Legend to recompute" action instead of the raw backend string, without auto-recomputing. Covered by a new backend route test (`test_start_run_outdated_feature_version_returns_structured_400`).

## Review / Quantity confirmation (R9 sections 16-17)

**PASS.** `ReviewStage.jsx` combines the split-out `RegionReviewList.jsx` (accept/reject, all existing testids preserved), the unmodified `ManualCorrectionPanel.jsx`, and the trimmed `QuantityPanel.jsx` (dimension + calculate + result) in one place — quantity controls are exactly where review happens, not elsewhere on the page. Draft/Confirmed status shown as an explicit text pill (`quantity-status`), matching R7's existing convention.

## Results stage (R9 section 18)

**PASS.** `ResultsStage.jsx` wraps the unmodified, R8-authoritative `ResultsPanel.jsx` — no quantity calculation added; confirmed/draft rows, material, plan/page, area, dimension, volume, and export exactly as R8 built them.

## Next-action guidance (R9 section 19)

**PASS.** Every blocked stage's reason string doubles as next-action guidance (e.g. "Confirm the drawing scale for this page.", "Review the detected regions -- N still need a decision."). Not a chatbot; concise, stage-scoped text only.

## State invalidation (R9 sections 22, 38)

**PASS.** `workflow-invalidation.spec.js` proves the full loop through the real UI: CONFIRMED quantity → return to Review → add a manual correction → the quantity panel keeps showing the stale Confirmed value until the user explicitly recalculates (matches R7's actual authority model — not automatic) → recalculating flips it to DRAFT (backend-reported) → the Results stage's row for the same material updates from Confirmed to Draft in the same session.

## Loading / error / empty states (R9 sections 23-25)

**PASS.** Every mutating action already had busy/disabled states from R3–R8 (preserved verbatim through the component splits). Empty states: `plans-empty` ("Upload your first construction plan."), `legend-entry-list` empty message, `library-entry-list` empty message (R5, unchanged), `results-empty` (R8, unchanged). Errors: `extractErrorMessage`/`extractErrorCode` (`apiErrors.js`) render backend `detail` (string or structured) as a human message, never a raw exception dump; console-only hiding never happens (every error path also renders a visible `.error` element).

## Refresh behavior / URL state (R9 sections 30, 39)

**PASS.** `useWorkflowUrlState.js` — no router library added (none existed; migration was unjustified for this SPA). `projectId`/`planId`/`pageNumber`/`stage` synced to the URL via `URLSearchParams` + `history.replaceState`. A reload restores the full session; five existing E2E specs' post-reload manual re-selection code was removed as no-longer-necessary (a real product improvement, verified by the specs still passing without it). Entry-level selection remains intentionally unsaved (ephemeral UI state).

## Legacy consolidation (R9 sections 31-32)

**PASS.** `App.jsx` reordered: `ProjectWorkflow` (canonical) renders first/primary; the legacy tool renders second under an explicit "Legacy single-session tool" heading. Zero changes to `UploadPanel.jsx`/`PlanViewer.jsx`/legacy routes' internal behavior — no silent data migration, no behavior change to the legacy path at all.

## Accessibility basics (R9 section 28)

**PASS, not audited beyond R9 scope.** Every new/modified control uses a real `<button>`/`<label htmlFor>` pair (no icon-only unlabeled controls introduced). Stage status is always a text label, never color alone (`WorkflowNav.test.jsx` asserts this directly). No new `data-testid`-only selectors were introduced where a role/label would do (`WorkflowNav`'s tabs are real `<button>`s with visible text). Full accessibility audit (screen-reader pass, full keyboard-only walkthrough) was not performed — out of scope per R9's own "without turning R9 into an accessibility overhaul" instruction.

## Responsive behavior (R9 section 27)

**DEFERRED.** The existing R7 coordinate-resilience check (`review-quantity.spec.js`, resize to 900px width, overlay stays over the same physical plan region) continues to pass unchanged, proving `usePageSelection.js`'s `ResizeObserver`-based tracking is untouched. A dedicated pass testing the new `WorkflowNav`/stage layout specifically at a "smaller laptop width" was not performed this release — flagged as risk-before-R10 below, not silently skipped.

## Security / ownership (R9 section 46)

**PASS (by construction, not newly tested).** No new endpoint was added; every existing route already enforces project-scoped ownership checks (R1–R8, unchanged). The frontend's URL state carries only IDs already validated server-side on every request — no new trust boundary introduced.

## Backend tests

**PASS.** **601 tests, 0 failures** (600 R8 baseline + 1 new: `test_start_run_outdated_feature_version_returns_structured_400`).

## Frontend unit tests

**PASS.** `npx vitest run` → **75 tests, 0 failures** (52 R8 baseline, with `DetectionPanel.test.jsx`/`QuantityPanel.test.jsx`'s scale-related cases redistributed into `DetectionRunPanel.test.jsx`/`RegionReviewList.test.jsx`/`ScaleConfirmationPanel.test.jsx`/trimmed `QuantityPanel.test.jsx` at equal-or-greater coverage, + 21 new: 17 `deriveWorkflowStages.test.js` + 4 `WorkflowNav.test.jsx`).

## Frontend build

**PASS.** `npm run build` → **115 modules**, 0 errors (101 R8 baseline + 14 new workflow/split-component files).

## Playwright — mandatory hard gate (R9 sections 33-37, 39, 42, 44)

**PASS.** `npx playwright test --project=chromium` → **18 scenarios, 0 failures**: all 15 R3–R8 scenarios green (5 required fix-forward changes for locator robustness / the new URL-persistence behavior — none a product behavior regression, all documented in `docs/testing/R9_END_TO_END_WORKFLOW.md`) + 3 new: E2E-09 (`workflow-journey.spec.js`, the full 40+-step real-UI journey including a real Excel download and a genuinely cold project re-open), prerequisite-blocking (`workflow-prerequisites.spec.js`), invalidation (`workflow-invalidation.spec.js`). Zero `page.evaluate()` state injection anywhere in the new specs. Console/network monitoring (`attachMonitoring`/`monitor.assertClean()`) unchanged and passing on every spec.

## Migration

**PASS — no migration required, as documented in advance (R9 section 47).** Zero new SQLAlchemy models. `alembic heads` remains `c61d4d05e4c9` (unchanged from the R8 baseline) throughout this release.

## CI compatibility

**PASS (by construction).** Zero new backend or frontend dependencies (confirmed via `git status` on `requirements.txt`/`requirements-minimal.txt`/`package.json`/`package-lock.json` — none touched).

## Scope compliance

**PASS.** No new hatch features, similarity formula, Detection V3, ML segmentation, embeddings, vector database, office/company/global Pattern Library, LLM agent workflow, automatic material truth, automatic candidate acceptance, PDF report generator, BIM/IFC export, new quantity formula, microservices, Redis, Celery, Kafka, or Kubernetes were introduced. Reviewed every file changed in this release.

---

## Deferred technical debt

- Full responsive/viewport audit of the new `WorkflowNav`/stage layout at a "smaller laptop width" specifically (beyond the existing R7 coordinate-resilience check).
- Full accessibility audit (screen reader, full keyboard-only walkthrough) — basics verified, full audit out of scope per R9's own instruction.
- `Materials` stage completion is a simple "library non-empty" check, not "every confirmed material has a library entry."
- Stage derivation is single-plan-page scoped (matches the app's existing one-page-at-a-time shape) — not a project-wide rollup across every plan/page.
- The legacy MVP's fabricated 8-step progress grid (`UploadPanel.jsx`) was left untouched, per the DEPRECATE-not-modify decision — it remains a known, pre-existing anti-pattern in the legacy-only path.
- The two export experiences (legacy `/export-excel` and the new `/results/export`) remain unconsolidated, as R6/R7/R8 already deliberately left them.

## Risks before R10

- The additive-rendering model means the page grows taller as more stages have real content — no pagination/collapsing was added; worth watching if a project accumulates many plan pages' worth of visible stage content in one session (today's UI is one plan page at a time, so this is currently bounded).
- `pickCurrentStage`'s "stay on the last complete stage until something becomes actionable" heuristic was tuned against the specific R3–R8 test flows; a future stage addition to `AUTO_ADVANCE_ORDER` should re-verify no existing spec depended on the exact current ordering.
- URL state does not validate that a `planId`/`pageNumber` combination in the URL actually belongs to the `projectId` also in the URL before use — the existing backend ownership checks (R1–R8) are the real enforcement boundary, but a stale/hand-edited URL could momentarily request a mismatched combination before a 404 surfaces it.

---

**No R10 functionality (further algorithm work, new detection version, ML segmentation, embeddings, automatic acceptance, global library, async infrastructure, microservice split) was introduced.** STOP here.
