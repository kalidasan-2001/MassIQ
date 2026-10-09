# Product Workflow — R9 Canonical Architecture

Date: 2026-08-29
Scope: documents the canonical, user-facing MassIQ workflow introduced by R9 ("Workflow Consolidation & Product Hardening"). R9 introduced no new detection/matching/quantity algorithm — this document is entirely about presentation, navigation, and derived state built on top of the R1–R8 domain model.

See `docs/architecture/R9_WORKFLOW_AUDIT.md` for the pre-implementation audit this design is based on (exact file/line evidence for every claim below).

---

## 1. Canonical stages

```text
Project → Plans → Plan Preparation → Legend → Materials → Analysis → Review → Results
```

Implemented as:

- `frontend/src/features/workflow/ProjectWorkflow.jsx` — the shell (project/plan/page pickers, URL sync, `WorkflowNav`, the shared `PlanCanvas`).
- `frontend/src/features/workflow/useProjectWorkflowState.js` — the single source of truth for one `(projectId, planId, pageNumber)` session: all persisted-state fetching, all mutation handlers, and the derived `stages`/`currentStage`.
- `frontend/src/features/workflow/deriveWorkflowStages.js` — the pure, unit-tested function mapping persisted state → per-stage status. No side effects, no fetching.
- Seven stage components (`PlansStage.jsx`, `PlanPreparationStage.jsx`, `LegendStage.jsx`, `MaterialsStage.jsx`, `AnalysisStage.jsx`, `ReviewStage.jsx`, `ResultsStage.jsx`), each a thin wrapper around existing R3–R8 components.

## 2. Rendering model: additive, not exclusive switching

**This is the single most important architectural decision in R9**, and it reverses an earlier design attempt during implementation — worth recording explicitly so a future release doesn't reintroduce the mistake.

The first implementation rendered exactly one active stage's pane at a time (a classic "wizard" switch), with `WorkflowNav` auto-advancing the active pane as each stage completed. This broke immediately: every R3–R8 Playwright spec was written against the pre-R9 continuous-scroll page, where (for example) clicking "Compute Features" and then immediately clicking "Run Detection V2" both worked because both controls were already on the page — no navigation click in between. Auto-advancing away from a just-completed stage the instant it became `complete` unmounted content the user (and the test) was still using (e.g. confirming a Legend entry immediately hid the entry list before an assertion could see the "Confirmed" label).

**The fix:** every stage component renders unconditionally, in order, inside `ProjectWorkflow.jsx`'s `STAGE_LIST` map. Each stage component internally decides whether to show its own blocked-reason message or its real controls, based on `workflow.stages[key].status`. Nothing is ever hidden by unmounting a sibling stage. `WorkflowNav` still computes a `currentStage` (via `pickCurrentStage`) for the "which stage matters next" highlight, and clicking a nav tab just calls `scrollIntoView` on that stage's section (`id="stage-<key>"`) — it does not change what is rendered.

This satisfies R9's actual requirements (current stage obvious, blocked stage explained, users can revisit earlier stages, guided not a wizard) without the unmount/remount race, and required zero rewrites of the existing R3–R8 pointer-driven interaction sequences.

## 3. `pickCurrentStage`: advance only into actionable stages

`deriveWorkflowStages.js`'s `pickCurrentStage` finds the first stage in `AUTO_ADVANCE_ORDER = ['plans', 'legend', 'analysis', 'review', 'results']` with status `'in_progress'`. If none exists (e.g. Legend just completed but hatch features aren't computed yet, so Analysis is still `'blocked'`), it falls back to the **last `'complete'` stage** rather than jumping into a blocked one. This is what lets the nav highlight move forward exactly when there is real, actionable next work, and stay put otherwise.

`plan_preparation` and `materials` are deliberately excluded from `AUTO_ADVANCE_ORDER` — see section 5.

## 4. Stage completion / prerequisite rules

Verified against the actual SQLAlchemy enums (`backend/app/models/*.py`), not invented:
`PlanProcessingStatus{UPLOADED,INSPECTING,READY,FAILED}`, `LegendEntryStatus{DRAFT,OCR_COMPLETE,CONFIRMED}`, `DetectionRunStatus{PENDING,RUNNING,COMPLETED,FAILED}`, `DetectedRegionStatus{CANDIDATE,ACCEPTED,REJECTED}`, `QuantityResultStatus{DRAFT,CONFIRMED}`.

| Stage | `complete` when | `blocked` reason shown when not reachable |
|---|---|---|
| Project | A project is selected/created | "Create or select a project to begin." |
| Plans | ≥1 `Plan` with `processing_status == READY` | *(never blocked — always the first actionable stage)* "Upload a construction plan to continue." |
| Plan Preparation | A `PlanScale` exists for the current plan page | "Select a plan and page first." |
| Legend | ≥1 `LegendEntry` with `status == CONFIRMED` for the plan page | "Select a plan first." |
| Materials | Informational — `complete` once ≥1 `PatternLibraryEntry` exists in the project | "Compute hatch features on a confirmed legend entry to enable this." |
| Analysis | ≥1 `DetectionRun` with `status == COMPLETED` for the current plan page | "Analysis is available after you confirm at least one legend material and compute its hatch features." |
| Review | The completed run's regions have zero remaining `CANDIDATE` status | "Run analysis first to get candidate regions to review." |
| Results | A `QuantityResult` with `status == CONFIRMED` exists for the current detection run | "Calculate and confirm the quantity to see it in Results." |

**Scope note:** like the rest of the pre-R9 UI, all of the above except Results operate on the *currently selected plan page* — there is no cross-page/cross-plan aggregation. Results is the one project-wide exception (`ResultsPanel` already lists every plan/page's results).

### Materials is not a hard gate for Analysis

`DetectionRun` references exactly one of `reference_legend_entry_id` / `reference_pattern_library_entry_id` (see `backend/app/models/detection_run.py`) — a Detection run can start directly from a confirmed `LegendEntry`, with no `PatternLibraryEntry` involved at all. Requiring a library entry before allowing Analysis would be a stricter rule than the backend itself enforces, so Materials is deliberately excluded from `AUTO_ADVANCE_ORDER` and from Analysis's blocking condition. The "Add to library" action itself stays inside the Legend stage's `LegendEntryEditor.jsx` (immediately after "Compute Features") rather than being moved into the Materials stage — Materials is a read-only browse view of what's already been added ("library suggests, user confirms" — R9 section 13).

### Plan Preparation is not a hard gate for Legend or Analysis either

The pre-R9 audit found Plan Preparation's scale-confirmation form was accidentally nested inside the old `QuantityPanel.jsx`, itself gated behind a completed `DetectionRun` — meaning a user could not confirm scale until *after* running Detection, even though `PUT .../pages/{n}/scale` has no such dependency. R9 extracts scale confirmation into `ScaleConfirmationPanel.jsx` (Plan Preparation stage), reachable as soon as a plan page is selected. Only Review's "Calculate Quantity" action actually requires a confirmed scale (`QuantityPanel.jsx`'s own `disabled={!scale}` check) — so Plan Preparation is excluded from `AUTO_ADVANCE_ORDER` too; nothing else is blocked by it being incomplete.

## 5. Feature-version-outdated UX (R9 section 15)

`ReferenceFeatureVersionOutdatedError`'s route mapping (`backend/app/routes/detection_runs.py`) returns a structured `HTTPException.detail`:

```json
{
  "error_code": "REFERENCE_FEATURE_VERSION_OUTDATED",
  "message": "This hatch was analyzed with an older feature version. Recompute the hatch features before running analysis.",
  "reference_feature_version": "...",
  "current_feature_version": "..."
}
```

This follows the exact precedent already used for validation errors (`{message, reasons: [...]}` — see `extractErrorMessage` in `frontend/src/features/legend/apiErrors.js`). `AnalysisStage.jsx` checks `extractErrorCode(err) === 'REFERENCE_FEATURE_VERSION_OUTDATED'` and renders the friendly message plus a "Go to Legend to recompute" button (`onGoToStage('legend')` — a `scrollIntoView`, not an automatic recompute). No backend auto-recomputation was added.

## 6. Invalidation

`QuantityService.calculate()` (R7, unchanged by R9) always sets `status = DRAFT` and `confirmed_at = None` on every call, even if a `CONFIRMED` result already exists for that `DetectionRun` — recalculation is not automatic the instant a correction is added; it happens on the user's next explicit "Calculate Quantity" click. `ResultsPanel.jsx` re-fetches on every `resultsVersion` bump (already wired via `onResultsChanged`, called from `handleCalculateQuantity`/`handleConfirmQuantityResult`), so Results always reflects the current persisted status. Verified end-to-end in `frontend/e2e/specs/workflow-invalidation.spec.js`.

## 7. Legacy coexistence

`frontend/src/components/UploadPanel.jsx` / `PlanViewer.jsx` and their legacy backend routes (`/upload-pdf`, `/save-hatch-sample`, `/detect-hatch`, `/export-excel`) are classified **DEPRECATE, not REMOVE** — `legacy-workflow.spec.js` and `invalid-upload.spec.js` actively exercise the entire legacy path end to end, so removing it would fail R9's own "keep existing E2E suite green" gate without a separate, evidence-based decision to retire those specs first (not made in R9). `App.jsx` now mounts `ProjectWorkflow` first (the canonical, primary workflow) and the legacy tool second, under an explicit "Legacy single-session tool" heading — no internal behavior of the legacy components changed.

## 8. Navigation / URL state

No router library was introduced (`package.json` had no `react-router` dependency, and a full migration was unjustified for a single-page app). `frontend/src/features/workflow/useWorkflowUrlState.js` synchronizes `projectId`/`planId`/`pageNumber`/`stage` into the URL via `URLSearchParams` + `history.replaceState`, restored on mount and on `popstate`. A page reload restores the full session automatically; legend-entry selection itself is deliberately **not** URL-persisted (matches the pre-R9 behavior — it's ephemeral UI state, not a domain entity).

## 9. No new backend endpoint, no new database table

Every stage's completion data was already being fetched by the pre-R9 `LegendWorkspace.jsx`/`LegendFeaturePage.jsx` at essentially the same granularity R9 needs. `useProjectWorkflowState.js` lifts those same calls one level up (still parallelizable, no new endpoints) and derives status client-side via `deriveWorkflowStages.js`. A dedicated `GET /api/projects/{id}/workflow` endpoint was evaluated (R9 section 21) and deferred: it would consolidate calls the frontend already needs to make for other reasons (rendering each stage's real content), not reduce a genuinely duplicated set of round trips, and would add a new backend surface + tests for marginal benefit. No `WorkflowStage` table was added — all status is derived from R1–R8 tables (`projects`, `plans`, `plan_pages`, `plan_scales`, `legend_entries`, `hatch_feature_sets`, `pattern_library_entries`, `detection_runs`, `detected_regions`, `manual_region_corrections`, `quantity_results`). Alembic head is unchanged from R8 (`c61d4d05e4c9`).

## 10. Known scope limitations (documented, not hidden)

- Stage derivation (except Results) is single-plan-page scoped, matching the app's existing one-page-at-a-time workspace shape — not a project-wide rollup.
- `Materials` completion is a simple non-empty-library check, not "does every confirmed material have a library entry."
- The legacy MVP's own fabricated 8-step progress grid (`UploadPanel.jsx`, hardcoded `'In progress'`/`'Not started'` regardless of real state) was left untouched, per the DEPRECATE-not-modify decision (section 7) — it is the "before" example the new `WorkflowNav` fixes for the canonical path, not something R9 silently carried forward as new.
