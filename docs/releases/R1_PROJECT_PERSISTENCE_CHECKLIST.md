# R1 — Project Persistence: Acceptance Checklist

Date: 2026-08-13
Scope: centralized settings, Postgres + SQLAlchemy + Alembic, `Project` model only, `ProjectService`, thin `/api/projects` routes, tests. No Plan/PlanPage, no Legend, no changes to hatch detection/export/quantity engine/frontend.

Every item below was actually executed against a live PostgreSQL 16 instance (docker-compose, `massiq-postgres`, host port 5433) and a live FastAPI app. No item is marked PASS on code inspection alone.

| # | Acceptance condition | Result | Evidence |
|---|---|---|---|
| 1 | PostgreSQL connection succeeds | **PASS** | `docker exec massiq-postgres pg_isready -U massiq -d massiq` → accepting connections; `psycopg2.connect(host=127.0.0.1, port=5433, ...)` succeeded from the app's own `SessionLocal`. |
| 2 | Alembic upgrade succeeds | **PASS** | `alembic upgrade head` → `Running upgrade  -> 72c82e8ce581, create projects table`. `\d projects` afterward shows all 6 columns (`id uuid`, `name varchar(255)`, `description text`, `status project_status DEFAULT 'active'`, `created_at`/`updated_at timestamptz DEFAULT now()`), matching the ORM model exactly. |
| 3 | Alembic downgrade succeeds | **PASS** | `alembic downgrade -1` → `Running downgrade 72c82e8ce581 -> , create projects table`. Verified after: `\d projects` → "Did not find any relation named 'projects'"; `\dT+ project_status` → 0 rows (enum type also dropped — see Known Limitations/fixes below). |
| 4 | Alembic re-upgrade succeeds | **PASS** | `alembic upgrade head` run again immediately after downgrade → succeeded cleanly, `\d projects` shows the identical schema restored. This full upgrade→downgrade→upgrade cycle was run against the real dev database, not simulated. |
| 5 | Project creation succeeds | **PASS** | `test_project_service.py::test_create_project_generates_uuid_name_timestamps_and_default_status` and `test_project_routes.py::test_create_project_returns_201_with_generated_fields` — both green. Live HTTP smoke test: `POST /api/projects {"name":"Smoke Test Project"}` → `201`, body `{"id":"11849612-...","name":"Smoke Test Project","description":null,"status":"active","created_at":"2026-08-13T21:00:38.41Z","updated_at":"2026-08-13T21:00:38.41Z"}`. |
| 6 | Project retrieval succeeds | **PASS** | `test_project_service.py::test_get_project_returns_created_project`, `test_project_routes.py::test_get_project_returns_created_project` — green. |
| 7 | Project listing succeeds | **PASS** | `test_project_service.py::test_list_projects_returns_all_created` (3 created, all 3 returned), `test_project_routes.py::test_list_projects_returns_all_created` — green. Live smoke test: `GET /api/projects` returned the created project. |
| 8 | Project update succeeds | **PASS** | `test_project_service.py::test_update_project_name_and_description_persist` and `test_partial_update_does_not_clear_omitted_fields` (PATCH with only `name` leaves `description` untouched) — both green, at service and route layer. |
| 9 | Unknown project returns 404 | **PASS** | `test_project_routes.py::test_get_unknown_project_returns_404_without_stack_trace` and `test_patch_unknown_project_returns_404` — green; response body confirmed to contain no `Traceback` text. |
| 10 | Validation behaves correctly | **PASS** | 10 pure-unit tests in `test_project_schemas.py` (blank name rejected, missing name rejected, name trimmed, `id`/`created_at`/`updated_at` cannot be set by the client — `extra="forbid"` → 422) plus route-level `test_create_project_blank_name_returns_422`, `test_create_project_missing_name_returns_422`, `test_create_project_cannot_override_id` — all green. |
| 11 | Project survives application/database-session restart | **PASS** | Two forms of evidence: **(a)** `test_project_service.py::test_project_persists_across_a_brand_new_engine_and_session` — data written via one SQLAlchemy engine/session read back via a completely independent second engine/session against the same DB. **(b)** Genuine cross-process proof: a standalone `python -c` process created 3 projects (`R1 Evidence Project A/B/C`) and exited completely; a second, wholly separate `python -c` process (new interpreter, new engine, no shared memory) then retrieved all 3 by ID and printed `PROCESS 2 CONFIRMED 3/3 projects intact after process restart`. Evidence rows were deleted afterward to leave the dev DB clean. |
| 12 | Existing backend tests remain green | **PASS** | `python -m unittest discover -s tests -p "test_*.py"` → **57 tests, 0 failures** (27 pre-existing: `test_excel_service.py`, `test_hatch_detection.py`, `test_vlm_service.py`, unmodified; 30 new R1 tests). |
| 13 | Existing frontend build remains green | **PASS** | `npm run build` in `frontend/` → `✓ 85 modules transformed`, `✓ built in 3.81s`, no errors. Frontend source was not touched in this iteration. |
| 14 | Existing endpoints remain registered | **PASS** | `app.openapi()` schema dump after wiring the new router shows all pre-existing paths unchanged (`/`, `/health`, `/upload-pdf`, `/rendered-page/{file_id}`, `/suggest-plan-scale/{file_id}`, `/analyze-section/{section_file_id}`, `/save-hatch-sample`, `/detect-hatch`, `/export-excel`, `/vlm/*`) plus the 4 new `/api/projects` paths. Live smoke test confirmed `GET /` and `GET /health` both still return 200 with their original bodies. |
| 15 | No existing MVP workflow was intentionally changed | **PASS** | `hatch_detection.py`, `excel_service.py`, `quantityEngine.js`, `measurement_service.py`, `vlm_service.py`, `routes/{detection,export,vlm}.py`, and all of `frontend/src/**` were not modified. `main.py`'s only change is one import line and one `app.include_router(projects.router)` line (additive, non-behavioral). |

**R1 acceptance gate: 15/15 PASS.**

## How to run this yourself

```bash
# 1. Start Postgres (repo root)
docker compose up -d postgres

# 2. Configure the backend (optional -- defaults already point at the compose service)
cd backend
cp .env.example .env   # adjust only if you changed docker-compose.yml's port/credentials

# 3. Install deps (venv already assumed active)
pip install -r requirements.txt

# 4. Run migrations
python -m alembic upgrade head

# 5. Run tests (spins up + migrates a separate `massiq_test` database automatically)
python -m unittest discover -s tests -p "test_*.py"

# 6. Run the app
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010

# Stop Postgres when done
docker compose down
```

## Known limitations

- The autogenerated Alembic migration initially had two latent bugs, both fixed before this checklist was signed off: (1) the Postgres enum column would have stored Python enum *names* (`ACTIVE`) while `server_default` used the *value* (`active`), which would have made `CREATE TABLE` fail outright the first time anyone ran the migration from scratch (fixed via `values_callable` on the model's `sa.Enum`); (2) the autogenerated `downgrade()` dropped the table but not the `project_status` enum type, which would have broken a subsequent `upgrade head` with "type already exists" (fixed by adding an explicit `sa.Enum(...).drop(...)` call). Both are now covered by the executed up→down→up cycle above, not just present in the migration file.
- Local Postgres runs on host port **5433**, not the Postgres-standard 5432, because this development machine already has an unrelated project's Postgres container bound to 5432. This is recorded in `docker-compose.yml`, `Settings.database_url`'s default, and `.env.example` — consistent everywhere, but worth knowing if you diff this against a machine without that conflict.
- `alembic/env.py` resolves its database URL from `ALEMBIC_DATABASE_URL` (env var) first, falling back to `Settings.database_url`, rather than trusting `Config.set_main_option("sqlalchemy.url", ...)` alone — this was necessary to let the test suite point migrations at a separate `massiq_test` database without touching `alembic.ini` or the dev `DATABASE_URL`. Anyone scripting Alembic programmatically (not via the CLI) needs to know this.
- No connection-pool tuning, no read replicas, no migration for concurrent/multi-instance deployment — intentionally out of scope for "smallest stable persistence foundation."
- `storage_root` was added to `Settings` for forward compatibility but is **not** wired into `main.py`'s existing storage path logic — per scope, PDF ingestion was not touched.

## Technical debt deliberately deferred

- The two divergent `requirements.txt` / `requirements-minimal.txt` files (flagged in the R0 audit) were **not** reconciled. Only the four R1 packages (`sqlalchemy`, `alembic`, `psycopg2-binary`, `pydantic-settings`) were added, to `requirements.txt` only (the file `CLAUDE.md`'s setup instructions actually reference). `requirements-minimal.txt` now diverges further; still tracked as debt, not addressed here.
- `Plan`, `PlanPage`, `LegendEntry`, `HatchPattern`, `Analysis`, `Material`, `Measurement`, `Export` models: none exist yet, as instructed. R2 scope.
- No `ProjectService.delete_project` — not implemented per the explicit instruction not to add it unless already required.
- No structured/request-scoped logging was added around the new routes (matches the existing app-wide absence of logging; not introduced or fixed here since it's out of R1's stated scope).

## Deviations from the approved architecture

None. `Settings`, `db/database.py`, `db/base.py`, `models/project.py`, `schemas/project.py`, `services/project_service.py`, `routes/projects.py`, and the Alembic setup all match the structure specified in the R1 instructions. The only unspecified implementation decisions made were: UUID generation is client-side (Python `uuid.uuid4()`, not a Postgres extension) to keep the schema portable; Postgres host port 5433 instead of 5432 to avoid a real conflict on this machine; `extra="forbid"` (not just omission) on `ProjectCreate`/`ProjectUpdate` so a client attempt to set `id`/`created_at`/`updated_at` fails loudly (422) rather than silently.
