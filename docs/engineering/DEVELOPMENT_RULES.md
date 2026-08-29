# MassIQ Development Rules

Permanent engineering principles for this repository, established across R1–R9. Future release prompts should reference this file instead of repeating these rules from scratch.

## 1. Inspect before editing

Never assume behavior from an old doc, a comment, or memory of a prior release. Read the actual current code — models, routes, components — before making an architecture decision or writing a checklist claim. Every R1–R9 release audit was based on direct code inspection with file/line citations, not on summarizing prior checklists.

## 2. One release per branch

Each numbered release (`feature/rN-...`) is a coherent, independently reviewable unit of work. Do not mix unrelated scope into a release branch. Do not begin a release's work on `main` directly.

## 3. Independent review before merge

A release branch is merged to `main` only after its own independent review has approved it. If a release's prerequisite branch was approved but not yet fast-forwarded into `main`, surface that gap explicitly and get human confirmation before merging — do not merge silently, even when the merge is a trivial fast-forward.

## 4. Deterministic quantity authority

Area and volume are computed exactly once, by the backend's deterministic geometry/quantity service, from persisted review state (accepted regions + manual corrections + confirmed dimension). No other layer — frontend, export, results view — ever recomputes or re-derives these values. Every consumer (Excel export, Results view) reads the same persisted `QuantityResult` row and nothing else.

## 5. AI/CV suggests, human confirms

Hatch detection, pattern matching, and OCR all produce *candidates* or *suggestions* — a human always makes the final accept/reject/confirm decision through an explicit UI action. No pipeline stage silently promotes a suggestion into confirmed truth.

## 6. Migrations are immutable after release

Once a migration has shipped in a release, it is never edited retroactively. A schema change discovered after the fact gets a new migration, never a rewritten old one.

## 7. Browser E2E for user-visible workflows

Any user-visible interaction involving pointer/mouse behavior, drag-to-select, file upload, or a real download must be proven with a real Chromium Playwright test — not a unit test that calls a React handler directly, and not `page.evaluate()` state injection. R3's native-image-drag bug and R9's stage-rendering-model bug were both found only by a real browser test failing, never by a component or API test.

## 8. No premature infrastructure

Do not introduce a router library, a message queue, a cache layer, a microservice split, or a new database table until a concrete, demonstrated need exists. R9 explicitly evaluated and declined a router migration and a new workflow-summary backend endpoint — see `docs/architecture/PRODUCT_WORKFLOW.md` sections 8–9 for the reasoning, kept as a template for future "should we add X" decisions.

## 9. Final combined verification before every commit

Before any release commit: fresh full backend suite (`python -m unittest discover -s tests -p "test_*.py"`), fresh full frontend Vitest suite, fresh production build, fresh full Playwright Chromium suite. "Fresh" means re-run after all implementation changes are in place, not reused from an earlier point in the session.

## 10. Evidence-based release reports

Every release checklist entry is `PASS` / `FAIL` / `BLOCKED` / `DEFERRED`. `PASS` requires executed evidence (a real test run, a real API response inspected, a real downloaded file's bytes checked) — never code inspection alone. If something was deliberately not done, mark it `DEFERRED` with the reason, not silently omitted.
