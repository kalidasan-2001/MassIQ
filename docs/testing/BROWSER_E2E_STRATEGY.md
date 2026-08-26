# MassIQ — Browser E2E Strategy

Introduced in **R3.5 — Production Browser E2E Foundation**. This document explains what the Playwright browser E2E suite (`frontend/e2e/`) protects, how it relates to the existing unit/component and backend integration tests, and how to run and debug it.

---

## Why this exists: the R3 native-image-drag bug

R3 (Legend Workflow) shipped with 177 backend tests passing, 16 frontend unit/component tests passing, and a clean production build — and the core drag-to-select interaction was still completely broken for a real user. `<img>` elements are draggable by default; a real mousedown-then-move on the plan preview image made Chromium hijack the gesture into a native OS-level image drag after the first `mousemove`, silently swallowing every subsequent `mousemove`/`mouseup` the app's own selection handlers needed. No pattern or description region could ever be selected through the actual UI.

**No test at any other level could have caught this.** Backend tests never touch a browser. Component tests (`LegendEntryEditor.test.jsx`) call React props/handlers directly — `usePageSelection`'s `onMouseDown`/`onMouseUp` would have worked perfectly if invoked as plain JavaScript functions, because the bug lived entirely in how a *real browser* routes native pointer events once a native drag gesture starts, which unit/component test tooling (jsdom) doesn't simulate at all. Only driving the actual UI in an actual browser, with actual `page.mouse` events, surfaced it — and only after real debugging (see `docs/releases/R3_LEGEND_WORKFLOW_CHECKLIST.md`'s account of that session).

This is the concrete justification for a permanent browser E2E gate, not a one-off manual check: R3.5 exists so this class of bug is caught automatically, every time, before it ships again.

R3.5 building this suite for real found **four more bugs of exactly this kind**, none caught by 193 combined backend+frontend unit tests:
1. `PlanViewer.jsx` (the legacy MVP) had the identical undiscovered `draggable` bug — never caught before because no browser-level test had ever driven that flow either.
2. `PlanViewer.jsx` hardcoded `backendBase = 'http://127.0.0.1:8010'`, ignoring the same `VITE_API_BASE_URL` environment configuration every other API call in the app respects — invisible in normal dev (where the backend genuinely runs on 8010) but a silent, total failure the moment the app runs against any other backend port, exactly what running an isolated E2E backend does.
3. A genuine React race in `LegendEntryEditor.jsx`: two separate `useEffect`s could both fire on the same "load a different entry" render (one seeding from `corrected_text`, one seeding from `raw_ocr_text`), and the second's `setCorrectedText` call silently clobbered the first's — meaning reloading the page and reopening an already-confirmed LegendEntry showed the raw OCR text instead of the saved correction. Caught only by the persistence-across-reload E2E test, fixed by collapsing both effects into one, ref-tracked branch.
4. A caching bug in R3.5's own new `backend/scripts/e2e_server.py`: it called the process-wide `@lru_cache`'d `get_settings()` once before finishing its own `DATABASE_URL` env var override, permanently caching the wrong (dev) database for the app's entire lifetime. Invisible in every local run because Playwright's `reuseExistingServer` kept silently reusing one already-correctly-started process across the whole debugging session — only surfaced once a genuinely fresh, CI-equivalent cold start (`CI=true`, no reuse, fresh ephemeral Postgres) was actually run. A concrete reminder of why "passes locally" and "passes from a clean, fresh CI-equivalent start" are different claims worth verifying separately.

## What each test level protects

| Level | Tool | What it verifies | What it cannot verify |
|---|---|---|---|
| **Backend unit/integration** | `python -m unittest` (177 tests) | Domain logic, DB persistence, migrations, API contracts, ownership isolation, crop math, OCR provider behavior — all in isolation or via `TestClient`, never a real browser | Nothing about the frontend; nothing about how a real browser's DOM/event system behaves |
| **Frontend unit/component** | Vitest + React Testing Library (16 tests) | Pure functions (`quantityEngine.js`, `coordinates.js`), and one component's state-transition logic (`LegendEntryEditor`) via calling its props/handlers directly in jsdom | Real pointer/mouse event routing, real network round-trips, real multi-page navigation, anything that depends on actual browser behavior (native drag, real image loading, real CORS/env wiring) |
| **Browser E2E** | Playwright + Chromium (`frontend/e2e/`) | The actual user-facing product, driven exactly as a person would: real clicks, real file uploads, real mouse drags, real page reloads, against a real (if isolated) backend/DB | Cross-browser behavior (Firefox/WebKit not run yet — see below); is slower and more expensive to run than the levels above, so it stays a smaller, curated set of scenarios, not a replacement for unit tests |

All three levels are required together: unit tests are fast and pinpoint logic bugs precisely; E2E is slow but is the only level that can observe what a real browser actually does with the real DOM. Neither replaces the other.

---

## Fixture strategy

`frontend/e2e/fixtures/plan-fixture.pdf` is a synthetic, committed PDF — generated by `backend/scripts/generate_e2e_fixture.py` (real PyMuPDF vector drawing commands, the same technique `backend/tests/pdf_fixtures.py` already uses for backend synthetic fixtures). It contains:
- plan-like geometry (an outer wall outline + a couple of interior partition lines),
- one real, parallel-line hatch pattern (a genuine vector hatch fill, not a filled block) at a fixed, documented normalized position,
- one real, legible, OCR-friendly text label ("Stahlbeton C25/30" / "d=20 cm") at a fixed, documented normalized position.

Both regions' exact normalized `{x, y, width, height}` coordinates are defined once in `frontend/e2e/fixtures/fixture-regions.js` and must stay in sync with the generator script's own constants if the fixture is ever regenerated. Coordinates are normalized (page-fraction) exactly per the R3 coordinate contract — this is what makes hardcoding them in test specs safe: they're independent of viewport size, render DPI, or how large the browser happens to display the image.

The `.gitignore`'s blanket `*.pdf` rule (which exists specifically to prevent accidentally committing real customer plans) has one explicit, narrow, documented exception carved out for this one file — see the comment above it in `.gitignore`.

A separate, real (non-synthetic) floor-plan PDF (`backend/test_plan/floorplan.pdf`) was used for one-off manual validation during R3 and is deliberately **not** part of the automated E2E suite — it's gitignored, not committed, and its content isn't guaranteed to be available on every machine/CI runner. Automated E2E always uses the committed synthetic fixture.

---

## Database and storage isolation

Every E2E run is fully isolated from a developer's normal dev database and storage:

- `backend/scripts/e2e_server.py` **drops and recreates** its own `massiq_e2e` Postgres database (derived from the dev `DATABASE_URL` with the database name swapped) on every single invocation, then migrates it to head with Alembic. This is the deliberate mechanism for "tests must be rerunnable" and "avoid test ordering dependencies" — every full E2E run starts from a genuinely empty, freshly-migrated schema, not whatever a prior run happened to leave behind.
- The same script generates (or accepts via `MASSIQ_E2E_STORAGE_ROOT`) a fresh temp directory for all file storage (uploaded PDFs, rendered previews, legend crops) — both the new Plan pipeline (`StorageService`, via the already-existing `Settings.storage_root`/`STORAGE_ROOT` override) and the legacy MVP pipeline (`storage_paths.py`, newly wired in R3.5 to respect the same override, which it was designed for but never used before).
- Individual tests within one run don't need per-test cleanup: each spec creates its own uniquely-named Project (`uniqueName()` helper, timestamp + random suffix) through the real UI, so tests never collide with each other's data even though they share the one backend/DB process for the whole run.

This means an E2E run can never write into, or read stale state from, `backend/app/storage/` or a developer's real `massiq` database — even if the developer has a dev server running at the same time (different ports: E2E backend on 8020, E2E frontend on 5190, vs. the normal 8010/5173).

---

## Debugging artifacts

On any test failure, Playwright automatically retains (configured in `frontend/playwright.config.js`):
- a screenshot (`screenshot: 'only-on-failure'`),
- a full trace (`trace: 'retain-on-failure'`) — inspect with `npx playwright show-trace <path>.zip` for a full timeline, DOM snapshots, and network log,
- a video (`video: 'retain-on-failure'`).

None of these are committed to git — `frontend/test-results/`, `frontend/playwright-report/`, and `frontend/blob-report/` are all gitignored, regenerated by every run.

In CI, a failed E2E job uploads the whole `playwright-report/` and `test-results/` directory as a workflow artifact (`.github/workflows/ci.yml`'s `e2e` job) so a failure can be diagnosed without reproducing it locally first.

---

## Console and network failure policy

`frontend/e2e/helpers/monitoring.js`'s `attachMonitoring(page)` watches every test for:
- **Unexpected `console.error` calls or uncaught page exceptions** — these fail the test via `assertClean()`, unless the exact message matches a documented entry in `ALLOWLISTED_CONSOLE_PATTERNS`. Two are allowlisted today, each with a written reason in the source: the React DevTools informational message, a known cosmetic React 18 + `@testing-library/user-event` warning (unrelated to E2E, but the same component code runs there too), and Chromium's own "Failed to load resource: ... status of 4xx" message, which the browser logs as a `console.error` for **any** non-2xx network response regardless of whether application code handled it correctly — genuine negative-path tests (invalid PDF uploads) trigger this by design, and the actual regression signal for "did the app handle the error correctly" comes from each test's explicit UI assertions, not from this generic browser echo.
- **Unexpected HTTP 5xx responses** — always fail the test, with no allowlist. A 4xx is only acceptable when a test is deliberately exercising a negative path (`invalid-upload.spec.js`), and even then the test still asserts the app shows a controlled, visible error — a 4xx alone isn't treated as "success" by omission.

Never suppressed globally — every allowlist entry exists because it is understood, documented, and provably unrelated to application correctness.

---

## Headed / debug mode

Three ways to watch or debug a run without editing any source or config:

```bash
npm run test:e2e            # full suite, headless, Chromium (same as CI)
npm run test:e2e:smoke      # just the tests tagged @smoke (fast developer check)
npm run test:e2e:headed     # full suite, a real visible Chromium window
npm run test:e2e:ui         # Playwright's interactive UI mode (step through, time-travel)
npm run test:e2e:report     # opens the last run's HTML report
```

`--headed` is particularly important for MassIQ specifically because so much of the product is drawing rectangles, coordinate math, and overlays — behavior that's much easier to understand watching a real window than reading a stack trace.

---

## Test execution levels

1. **Developer smoke** (`npm run test:e2e:smoke`) — the single test tagged `@smoke` (`smoke.spec.js`): app loads, critical UI present, backend healthy, no console/network failures. Seconds, not minutes — run this constantly while iterating.
2. **Full E2E** (`npm run test:e2e`) — all eight scenarios across five spec files, Chromium only, serial (`workers: 1`, see below).
3. **CI** — identical to "full E2E" above, run automatically in the `e2e` job of `.github/workflows/ci.yml` after the existing `backend`/`frontend` jobs both pass, uploading failure artifacts.

---

## Browser matrix

**Chromium only, deliberately, for this release.** Firefox and WebKit are documented here as future compatibility expansion, not a current release blocker — adding them now would roughly triple CI runtime for a class of cross-browser bug this application has no evidence of yet (nothing in R1–R3's audits ever surfaced a browser-specific issue; the one real bug this suite exists to prevent, the native-image-drag hijack, is itself a Chromium/WebKit-family behavior, not something Firefox does the same way, so Chromium coverage is already the highest-value single browser to protect). Revisit if/when there's concrete evidence of a cross-browser-specific defect, not preemptively.

## Deferred browser coverage

- Firefox / WebKit projects (see Browser Matrix above).
- Parallel test execution (`fullyParallel`/`workers > 1`) — the suite is deliberately serial in this first version even though each spec's use of uniquely-named projects makes parallelism plausible; proving that out safely is left for a later pass rather than assumed now.
- A secondary, smaller desktop/tablet viewport smoke pass (R3.5 explicitly scopes out comprehensive responsive testing).
- Testing against the production-built/previewed bundle (`vite preview`) rather than the dev server (`vite dev`) — the dev server was chosen for faster local iteration; running E2E against the actual production build is a reasonable future hardening step, not required now.
- The pre-existing `frontend/playwright.smoke.run.js` script (raw `playwright` library, not `@playwright/test`) is now superseded in spirit by this suite; it was already flagged in the R2.5 audit as broken from a clean checkout (a hardcoded path into a gitignored recovery folder) and remains untouched/unremoved here as an explicit scope boundary — cleaning it up is separate, later housekeeping, not part of R3.5.
