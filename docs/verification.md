# Verification log

What was run, on what, and the result. Every line can be repeated with the command next to it. Newest first. Nothing here replaces
running the checks yourself; it records what the maintainer's machine showed.

## 2026-11-19/20 — MacBook Air M2, 8 GB, macOS 26.5, Ollama 0.40.16, qwen3.5:4b + Phonon, Chrome

| Check | Command | Result |
|---|---|---|
| Python lint | `backend/.venv/bin/ruff check .` | clean |
| Docs links | `python3 scripts/check_docs.py` | 27 files OK |
| Backend tests + coverage | `backend/.venv/bin/python -m pytest backend --cov=backend/app` | 746 passed, 94 % lines, no resource warnings (they now fail the run) |
| Backend tests from the hash lock, Python 3.10 / 3.11 | fresh venv, `pip install --require-hashes -r backend/requirements-dev.lock`, then pytest | all passed (3.10: 719, 3.11: 715 + 2 skipped; run before the last tests were added) |
| Lock hashes for other platforms | `pip download --require-hashes --only-binary=:all: --python-version 3.12 --platform <tag> -r backend/requirements-dev.lock` | every wheel matched for `win_amd64`, `manylinux_2_28_x86_64`, `manylinux_2_28_aarch64` |
| Frontend lint, types, build | `cd frontend && npm run lint && npm run typecheck && npm run build` | clean |
| Frontend tests + coverage | `cd frontend && npm run coverage` | 152 passed in 5 of 5 runs on an idle machine; 41 % lines |
| Known vulnerabilities | `pip-audit -r backend/requirements.lock --require-hashes` and the same for `requirements-dev.lock`; `npm audit` | none; none; 0 |
| Cold first start | fresh copy, empty pip/uv/npm caches, `time ./start.sh` | 39 s (pip), 49 s (uv), not counting the 4 GB model |
| Real-Chrome suites, no model | `cd frontend && node e2e/<name>.mjs` | all passed: harness-selftest 4, basics 53, ui-features 66, ui-audit 51, qa-sweep 10, setup-gate 28, install-help 9, resumes 47, cloud (fake Groq) 78, loaders 16, practice 18, active-interview 21, pdf-export 13, ui-redesign 60, voices-system 18 checks |
| Real-Chrome full interview, real models | `cd frontend && node e2e/full-flow.mjs` | 24 / 24 checks, 271 s |
| Real-model grading tests | `RUN_INTEGRATION=1 backend/.venv/bin/python -m pytest -m integration -s backend/tests/integration/test_real_models.py` | 6 / 6 passed, 700 s |
| Works with no network (macOS sandbox) | `python3 scripts/offline_check.py` | 7 / 7: spoken question, 4 answers graded (2 follow-ups), report, PDF; only `127.0.0.1` contacted |
| Term lists stay at or below 3 | `backend/.venv/bin/python backend/benchmarks/grading/term_lists.py` | 7 detected lists 1.2–2.9; 1 not detected (0.7) |
| Launcher start / stop without Ollama (what the new CI step does) | `OLLAMA_AUTOSTART=0 OLLAMA_HOST_URL=http://127.0.0.1:9 ./start.sh`, health, `./stop.sh` | health 200, UI served, port closed after stop (macOS) |
| Report summary names what was asked | real model, summary of a LEFT JOIN + index interview, 3 runs `backend/.venv/bin/python backend/benchmarks/grading/summary_check.py` | 3 / 3 name LEFT JOIN; none mention an outer join (one machine, small check, no before/after comparison) |
| Grading benchmark | `backend/.venv/bin/python backend/benchmarks/grading/run.py` | see [evaluation §8](evaluation.md#8-measured-grading-quality-benchmark): 70 / 70 pairs ranked as labelled, 55 / 56 in band |

**Runs that failed first and why.** While the benchmark, Chrome suites and the model ran at the same time (about 10 GB of swap in
use), five Chrome suites timed out and the frontend unit tests exceeded their time limits. All passed when rerun on an idle machine
(table above). Two of 170 benchmark gradings timed out in that period; they are kept in the benchmark results.

**Not verified here:** Windows and Linux on real machines (CI runs the backend, frontend and launcher checks there), a physical
microphone, the real Groq API, Intel Macs.
