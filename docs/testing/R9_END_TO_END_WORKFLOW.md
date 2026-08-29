# R9 — End-to-End Workflow Testing

Date: 2026-08-29
Scope: the browser test coverage added for R9's workflow consolidation, plus the actual measured results from the final combined run.

---

## E2E-09: complete MassIQ project journey

File: `frontend/e2e/specs/workflow-journey.spec.js`

Drives the full product journey end to end through the real UI, real Chromium pointer/mouse input, no `page.evaluate()` state injection, no direct API calls for any critical action:

1. Open MassIQ, create a Project via the real form.
2. Verify project landing (`project-landing-summary`: "0 plans in this project.") and the `WorkflowNav` is present.
3. Plans: verify the empty state, upload a real synthetic PDF, wait for it to reach `READY`, verify the Plans stage shows `Complete`.
4. Plan Preparation: verify it starts `In progress`, confirm a declared 1:100 scale via a real form submission, verify it becomes `Complete`.
5. Legend: real mouse drag to select the hatch pattern region, real mouse drag to select the description region, run OCR, correct the text, confirm the material, verify the entry reaches `confirmed`, compute hatch features, verify the Legend stage shows `Complete`.
6. Materials: add the confirmed hatch to the Project Pattern Library via a real click, verify the library entry appears with the correct material name, verify the Materials stage shows `Complete`.
7. Analysis: run Detection V2, wait for ≥2 real candidate regions, verify the Analysis stage shows `Complete`.
8. Review: ACCEPT one real candidate, REJECT another, manually ADD a region with a real pointer drag, manually SUBTRACT a region with a real pointer drag.
9. Confirm the dimension, calculate the quantity (verify it starts `Draft`), confirm it (verify it becomes `Confirmed`), verify the Results stage shows `Complete`.
10. Results: verify the material, the authoritative area, and the authoritative volume match the backend response exactly (not re-derived client-side).
11. Export: real click on the Export button, a real `page.waitForEvent('download')`, verify the filename pattern (`MassIQ_<project>_quantities_<date>.xlsx`) and a non-zero file size.
12. Reload the page — verify the Results stage still shows `Complete` and the same confirmed row is visible (proves URL-based session restoration, R9 section 30).
13. Navigate to `/` fresh (no URL state at all) and re-select the same Project by name from the picker — verify the same confirmed material, status, and area are still shown (proves persistence is server-side truth, not just URL convenience).
14. Assert zero unexpected console errors and zero unexpected 5xx responses throughout.

**Measured result:** PASS, ~12s.

## Prerequisite-blocking E2E

File: `frontend/e2e/specs/workflow-prerequisites.spec.js`

A new Project starts with Analysis showing a specific, actionable blocked-reason message (not just an absent control) and `Blocked` status. Uploading a plan alone does not unblock it. Confirming a Legend entry alone does not unblock it either (features must also be computed — Materials/library membership is deliberately *not* required, per `PRODUCT_WORKFLOW.md` section 4). Only once hatch features are computed does the blocked message disappear, `run-detection-btn` become visible, and the stage status flip to `In progress`.

**Measured result:** PASS, ~3s.

## Invalidation E2E

File: `frontend/e2e/specs/workflow-invalidation.spec.js`

Drives a full flow to a `CONFIRMED` QuantityResult, then returns to Review, adds one more real manual correction, and explicitly recalculates (matching R7's actual authority model: recalculation is not automatic the instant a correction is added — it happens on the next explicit "Calculate Quantity" click). Verifies:

- The quantity panel keeps showing the (now stale) `Confirmed` value until recalculation is explicitly triggered — no silent background recompute.
- After recalculating, the backend response itself reports `status: "draft"`.
- The quantity panel updates to `Draft` and the "Confirm Result" button reappears.
- The Results stage's row for the same material updates from `Confirmed` to `Draft` in the same session, without a page reload.

**Measured result:** PASS, ~5s.

## Refresh behavior

Covered directly inside E2E-09 (step 12) and already-existing R3–R8 specs (`persistence.spec.js`, and the reload sections of `detection-v2.spec.js`, `review-quantity.spec.js`, `pattern-library.spec.js`, `results-export.spec.js`) — all of these were updated during R9 to rely on the new URL-based session restoration (`useWorkflowUrlState`) instead of manually re-selecting the project/plan through `<select>` elements after `page.reload()`, since that manual re-selection is no longer necessary (a real, measured product improvement, not just a test simplification).

## Viewport / responsive

`review-quantity.spec.js`'s existing coordinate-resilience check (manual-correction overlay stays over the same physical plan region after a viewport resize to 900px width) continues to pass unchanged — R9 did not touch `usePageSelection.js`'s `ResizeObserver`-based `viewSize` tracking.

## Existing R3–R8 regression suite

All 15 pre-existing scenarios remain green, with the following fix-forward changes (documented here since they were caused by R9's restructuring, not by any algorithm change):

- `app-actions.js`'s `r3Section()` now locates the workflow root by `data-testid="project-workflow-root"` instead of heading text — a strictly more robust locator, and the single point of change that kept every spec importing `r3Section` working unchanged.
- `legend-workflow.spec.js`: three assertions that used `.status-pill` with `.last()`/`.first()` DOM-order matching were switched to `page.getByTestId('legend-status-pill')` — the app now has many more `.status-pill` elements on the page (`WorkflowNav`'s 8 stage badges, the legacy tool's own pills), so DOM-order matching is no longer reliable (R9 section 43: prefer testids over DOM order).
- `detection-v2.spec.js`, `review-quantity.spec.js`, `pattern-library.spec.js`, `persistence.spec.js`, `results-export.spec.js`: the post-`page.reload()` manual project/plan re-selection (via `document.querySelectorAll('select')[1]`) was removed — R9's URL-based session state restores it automatically, and the plan picker itself changed from a `<select>` to a status-pill list (`PlansStage.jsx`), so the old index-based selector no longer applied anyway.
- `project-plan.spec.js`, `invalid-upload.spec.js`: assertions on the plan `<select>`'s option text were updated to check `PlansStage.jsx`'s new `plan-list`/status-pill markup instead.
- `smoke.spec.js`: the hero heading assertion was updated to the new copy ("Construction quantity takeoff"), and now also asserts the "Legacy single-session tool" heading is present — proving both the canonical and legacy paths render in the same page load.

None of these were behavior regressions in the product — every one was either a locator robustness fix or a reflection of a genuine, intentional UI change (URL persistence, plan list redesign, hero copy).

---

## Final measured totals (fresh combined run)

| Suite | Command | Result |
|---|---|---|
| Backend | `python -m unittest discover -s tests -p "test_*.py"` | **601 tests, 0 failures** (600 R8 baseline + 1 new structured-error-detail test) |
| Frontend unit (Vitest) | `npx vitest run` | **75 tests, 0 failures** (52 R8 baseline + 2 split-component test files replacing 2 originals with equal-or-greater coverage + 21 new workflow tests) |
| Frontend build | `npm run build` | **115 modules, 0 errors** |
| Playwright (Chromium) | `npx playwright test --project=chromium` | **18 scenarios, 0 failures** (15 R3–R8 baseline, all still green + 3 new: E2E-09, prerequisite-blocking, invalidation) |

Zero unexpected console errors, zero unexpected 5xx responses across every spec (enforced by `attachMonitoring`/`monitor.assertClean()`, unchanged from R3.5).
