# MassIQ

This repository was restructured to use a clean root layout:

- `backend/`
- `frontend/`
- `docs/`

Recovery notes:

- The recoverable backend snapshot was found in `_backup_before_flatten/massiq-mvp-backup/backend`.
- The recoverable frontend snapshot was found in `_backup_before_flatten/massiq-mvp-backup/frontend`.
- The current root-level copy is a safe recovery copy only. The frontend snapshot contains `package.json` but no `src/` or Vite config, and the backend snapshot contains `app/` but key Python files are empty.

Backups and generated folders were intentionally preserved and are ignored by Git until the app source is fully verified.
