# Contributing

Thanks for helping. This is a local-first app: please keep it that way (no telemetry, no CDNs, no silent network calls).

## Setup

```bash
./start.sh --dev            # backend on :8000 (auto-reload) + Vite on :3000
```

Backend: Python ≥ 3.10, dependencies in `backend/requirements*.txt` (a virtualenv is created in `backend/.venv` by `start.sh`).
Frontend: Node ≥ 18, `cd frontend && npm ci`.

## Before you open a pull request

```bash
backend/.venv/bin/python -m pytest backend          # mocked model, no downloads (CI runs this on macOS, Windows, Linux)
cd frontend && npm run typecheck && npm test && npm run build
```

Optional: the real-Chrome e2e scripts in `frontend/e2e/` and the real-model tests (`RUN_INTEGRATION=1 ... -m integration`).

## Ground rules

- **Never weaken or delete a test to make CI pass.** If behaviour changes on purpose, update the test and explain why in the PR.
- The model never decides a score, a limit or a state transition: put policy in code and test it (see `docs/adr/`).
- Database changes are additive migrations in `backend/app/db.py` with an upgrade test from the previous version; never rewrite user rows.
- Don't change which inference models users depend on; add new ones only as opt-in.
- Treat any user-supplied text (answers, resumes, question imports) as untrusted in prompts.
- Keep UI changes token-driven (CSS variables) so light and dark themes both work; no heavy animation.
- Architecture decisions that change these rules get an ADR in `docs/adr/`.
- Update `CHANGELOG.md` under *Unreleased*.
