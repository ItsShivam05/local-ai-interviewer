# Independent review, round 4: Local AI Interviewer

Reviewer: an independent agent, 2026-11-20. I reviewed the current working tree, including uncommitted files, from a copy in my own scratch directory.
Machine: MacBook Air (Apple Silicon), 8 GB RAM, macOS 26.5.2, Python 3.13.5, Node 24.2, Ollama 0.40.16, with qwen3.5:4b and phonon already installed.
Labels used throughout: VERIFIED means I ran it or read the code. CLAIMED means the docs say so and I could not confirm it. UNKNOWN means I did not check. A green GitHub Actions run counts as CI-verified for that platform. It is not evidence from a real machine.

## 1. Verdict

- **What it is:** a local-first mock-interview coach for tech roles (FastAPI + React + Ollama). It asks your questions aloud, takes typed or spoken answers, has a 4B local model grade them, computes the scores in code, and writes a report.
- **Overall score: 6.5 / 10.**
- **Biggest strength:** careful engineering around a small model, all verified:
  - one guarded state machine,
  - the answer is saved before grading,
  - scores are computed by the app,
  - quote checks on the model's claims,
  - 749 backend tests at 94 % line coverage, plus real-Chrome suites.

  A real interview with the real model worked end to end on the first try.
- **Biggest risk:** a project 11 days old with one person behind it. There are no releases, 2 stars, and 10 Dependabot PRs open and unanswered. A large uncommitted working tree (71 files changed, plus the lock files, the benchmark and new tests) has never been through CI. Second risk: the grader ranks answers well but does not reliably catch a confidently stated wrong claim (see the Proof row and MUST FIX item 3).
- **Recommend today?** Yes, as a private study aid, for technically comfortable users on an Apple Silicon Mac. Not yet for Windows or Linux users, and not for anyone who needs the score to judge subtle correctness.

## 2. Scorecard

| Area | Score | Reason |
|---|---|---|
| Idea and differentiation | 6 | Crowded space with at least 7 local Ollama look-alikes. The real edge is narrow: app-computed scores, quote-checked evidence and a fully offline voice loop. |
| Does it work | 8 | Cold install took 38 s with empty caches. All checks are green. A real 2-question interview with follow-ups ran with the real model: report, summary and PDF all worked, and duplicate submits returned 409. Only verified on macOS. |
| Code quality | 8 | Coherent layering that matches the docs. State transitions are compare-and-set. No bug found in the traced paths. Minor issues: an `assert` used as a runtime guard; dense long lines; a 204-line PDF function. |
| Testing | 8 | Backend: 749 passed, 94 % coverage, with real-thread concurrency tests. Real-Chrome suites pass (basics 53/53, qa-sweep). Gaps: frontend coverage is 41 %; adaptive and resume features were tested only with a mocked model; the current tree has not run in CI. |
| Security | 7 | Strong loopback, Host, Origin and Sec-Fetch guards (probed). Actions are SHA-pinned with read-only token permissions. Audits are clean. Weak points: no branch protection, the Groq key is stored in plaintext in SQLite, and Dependabot PRs are unmanaged. |
| Documentation | 8 | Unusually honest about what is unverified, and claims match what I measured. But the README is 566 dense lines and hard to scan. |
| Ease of adoption | 5 | Needs Python, Node, Ollama, a 4 GB model and 8 GB of RAM (I saw 1 GB free). There is no packaged build or release, and only macOS has been run by a person. |
| Project health | 3 | One contributor, 13 commits in 10 days, 2 stars, 0 forks, 0 issues, no tags. Bus factor 1. The automation PRs are ignored. |
| Proof of core claim | 6 | A real benchmark exists with bands fixed before the run, and my held-out check confirmed the ranking (4/4 questions). But the labels are the project's own, on one machine. Subtle wrong claims are often scored mid-range or not flagged at all. |

**Overall: 6.5 / 10.** How I weighted it:
- Core-claim proof and "does it work" carry the most weight (25 % each).
- Code, testing and security share 30 %.
- Documentation, adoption and health share 20 %.

That weighting gives about 6.9. I then capped the total at 6.5 for two reasons. First, the core claim ("useful, trustworthy grading by a local 4B model") is only partly proven. Second, the project-health signals (bus factor 1, no release, an uncommitted tree that CI has not seen) mean a stranger cannot yet rely on what is on GitHub matching what I tested.

## 3. Advantages (verified)

- **Install works as documented.** `./check.sh` gave a clear read-only report. `./start.sh` with empty pip, uv and npm caches on `APP_PORT=3300` finished with exit 0 in **38.0 s** (the README claims 39 s). The health endpoint was OK.
- **Checks are green:**
  - ruff is clean;
  - the docs link checker passed (25 files);
  - backend pytest: **749 passed, 2 skipped, 94 % line coverage** in 33 s;
  - eslint shows 0 warnings and `tsc` is clean;
  - vitest: **153/153 tests** passed (41.1 % lines);
  - the Vite build succeeds;
  - `npm audit` found 0 issues and `pip-audit` on `requirements.lock` found no known vulnerabilities.
- **The state machine holds up in a real run.** In my real-model interview (`journey.py`, port 3300):
  - a second interview was refused with `409 interview_active`;
  - every duplicate submit of an answer returned 409;
  - follow-ups were asked and capped at 1;
  - the question score equals the documented formula, (7.5 × 2 + 0.5) / 3 = 5.2;
  - the narrative summary completed and the PDF export was a real `%PDF-` file (53 KB);
  - total time was 214 s for 4 graded answers.

  In code: compare-and-set in `backend/app/services/interviews.py:415-427`, and stale results are dropped at `interviews.py:620-621`.
- **The local network boundary works:**
  - a bad `Host` returns 403;
  - a cross-origin POST returns 403 (`backend/app/main.py:71-85`);
  - the listener is bound to `127.0.0.1` only (checked with `lsof`);
  - the built UI contains no external URLs other than SVG namespaces and React's error-doc links.

  The real-Chrome `basics` and `qa-sweep` suites both pass, including "no requests left localhost".
- **Grading ranks answers sensibly with the real model.** In my own 12 answers (not the project's), strong > subtle-error > wrong in all 4 questions. A buzzword-only answer scored 1.5. A terse but correct answer scored 6.5.
- **Upload validation is clear.** A non-PDF was rejected with `not_a_pdf`. An 11 MB file was rejected with `resume_too_large`. Both messages are readable.
- **Supply-chain hygiene:**
  - every workflow action is pinned to a SHA;
  - workflow permissions default to `contents: read`;
  - Dependabot and CodeQL are set up;
  - Python installs are hash-locked (`scripts/manage.py:396-401`);
  - the dependency footprint is small (7 direct backend runtime deps and 3 frontend runtime deps).
- **The docs are honest about their limits.** The README's §2 and §11 state plainly what is unverified: Windows and Linux, real Groq use, the physical microphone, and benchmark labels that are the project's own.

## 4. Improvements

### MUST FIX (blocks trust or adoption)

| Item | Why | Where | Effort |
|---|---|---|---|
| Commit the working tree and get it green in CI | What I tested is not what GitHub serves. The hash-lock files are untracked, yet the launcher and CI in the working tree install from them. So do the benchmark, the concurrency tests and `docs/verification.md`. The new launcher start/stop CI step has never run. | `git status`: `backend/requirements*.lock`, `backend/benchmarks/`, `backend/tests/test_concurrency.py`, `.github/workflows/ci.yml` | S |
| Triage the 10 open Dependabot PRs (3 have failing checks) | Unanswered automation PRs read as an abandoned project. Dependabot also updates the `.txt` files but not the `.lock` files, so its PRs and the locks will drift apart. | GitHub PRs #1-#10, `.github/dependabot.yml` | S |
| Say plainly that the grader can miss confident wrong claims | In the project's own data, the "subtle" answer (one plausible wrong claim) scores higher than a correct-but-thin answer in 7 of 10 questions. In my run, "choose CA, stay available when the network is cut" was graded 5.9 `correct_incomplete` with no misconception flagged. Users will read 5.9 as "mostly right". | `docs/evaluation.md` §8, report UI, README §11 | S (docs) / M (prompt work with a fresh held-out set) |

### SHOULD DO

| Item | Why | Where | Effort |
|---|---|---|---|
| Turn on branch protection and require CI on `main` | The OpenSSF branch-protection check fails today (the GitHub API returns 404 for protection). | Repository settings | S |
| Have the benchmark labelled by someone outside the project, and add a held-out set | The current labels are written by the author. My 12-answer check is too small to settle the question. | `backend/benchmarks/grading/answers.json` | M |
| Store the Groq key in the OS keychain, or at least keep it out of backups by default | The key sits in plaintext in SQLite (`backend/app/services/ai_config.py:192-206`). The file is mode 0600, but the key travels in every `/api/backup` download (`backend/app/routers/system.py:166`). | ai_config, backup | M |
| Run on a real Windows and a real Linux machine | Today these are CI-verified only (tests and `check`), and the start/stop step has not run there yet. | README §2 | M |
| Replace the `assert` at `interviews.py:647` with an explicit check | An `assert` is removed under `python -O`. | `backend/app/services/interviews.py:647` | S |
| Raise frontend coverage beyond 41 % | Resumes, Questions and Settings are covered only by e2e scripts that CI does not run with a model. | `frontend/src/pages` | M |

### NICE TO HAVE

| Item | Why | Where | Effort |
|---|---|---|---|
| Split the README into a short landing page plus docs pages | 566 dense lines bury the quick start and the limitations. | `README.md` | S |
| Break up `render_pdf` (204 lines) and `interviews.create` (98 lines) | Easier for contributors to work in. | `backend/app/services/report_pdf.py`, `backend/app/services/interviews.py` | S |
| Move off the deprecated `httpx`-based TestClient | It already raises a warning in every test run. | `backend/tests` | S |
| A packaged build (no separate Python or Node) | This is the largest adoption barrier. | Distribution | L |

## 5. Who it is for, and who should not use it yet

**Best for:**
- A developer or student preparing for software, data or backend interviews on an **Apple Silicon Mac with at least 8 GB of RAM** (16 GB is comfortable).
- Someone at ease with a terminal who wants private practice with no account and no cloud.
- Ideally, someone who writes expected answers (rubrics) for the questions they care about.

The tool is good at telling a strong answer from a vague, empty or wrong one, and at making you explain your own resume.

**Should not use it yet:**
- Windows and Linux users who need it to just work: it is CI-verified, but no person has run it there.
- Non-technical job-seekers: it needs Python, Node, Ollama and a 4 GB download.
- Anyone using the numeric score as a pass/fail judgement of factual correctness. It can miss plausible wrong statements, especially without a rubric.
- Teams or institutions: it is single-user with no auth, has no releases, and has a single maintainer.
- Intel Macs or machines with less than 8 GB: untested, and expected to be slow or memory-starved. My 8 GB machine showed 1.0 GB free while the model was loaded.

## 6. Competitors (from Phase 1)

GitHub figures come from the GitHub API, fetched 2026-11-20. Commercial prices come from third-party 2026 reviews and are not verified.

| Tool | Type | Better than this app | Worse than this app | Last activity |
|---|---|---|---|---|
| [GrillKit](https://github.com/Forkfield/grillkit) | OSS, self-hosted | Curated YAML question banks; any OpenAI-compatible LLM | No resume questions or quote-checked grading found; unclear license | 13 stars, push 2026-08-16 |
| [J3rry320/interview-coach](https://github.com/J3rry320/interview-coach) | OSS | CLI as well as web; many LLM providers | Uses browser speech (not fully local); LLM-only scoring | 7 stars, push 2026-07-18 |
| [Vandool/grillme](https://github.com/Vandool/grillme) | OSS | Uses the job description too; works as an MCP server; Docker | edge-tts is a cloud service; stale | 4 stars, push 2026-04-06 |
| [yourspeakreps](https://github.com/iamrishavraj1/yourspeakreps) | OSS | Simpler | macOS only; no adaptivity or evidence checks | 2 stars, push 2026-09-30 |
| [Seekr](https://github.com/mdjamilkashemporosh/Seekr) | OSS | Similar local pitch | No license; small scope | 4 stars, push 2026-01-29 |
| [IliaLarchenko/Interviewer](https://github.com/IliaLarchenko/Interviewer) | OSS | Coding and system-design modes; hosted demo; 128 stars | Dormant; geared to cloud APIs | push 2025-03-16 |
| [offline-interrogator](https://github.com/akshatshahh/offline-interrogator) | OSS | Agent framework | Tiny, early | 1 star, push 2026-10-05 |
| [Final Round AI](https://finalroundai.com) | Commercial | Polish, many formats, large user base | Cloud only; costly (about $90-150/month, unverified) | Active |
| [Yoodli](https://yoodli.ai) | Commercial | Delivery analytics; panel role-play | Cloud; about communication rather than technical correctness | Active |
| [Exponent / Pramp](https://www.tryexponent.com) | Commercial | Human peers, expert content | Paid, cloud | Active |
| [interviewing.io](https://interviewing.io) | Commercial | Real engineers as interviewers | Expensive; no AI or local option | Active |
| Google Interview Warmup | Commercial (free) | — | Appears discontinued (the URL now serves a general article) | — |

**Where it ranks.** Among the open-source local tools, this is the most complete and best-tested I found. It is the only one with app-computed scoring, quote verification, adaptive selection and a fully offline voice loop together. It has the least adoption of any of them apart from the 1-2 star repos. It does not compete with commercial tools on content or polish, only on privacy and cost.

## 7. Promise check

| Promise | Status | Evidence |
|---|---|---|
| Install with check, setup-models and start; first start about 39 s | VERIFIED | 38.0 s cold start with empty caches, exit 0 (my run). `setup-models` not run, because the models were already installed. |
| Binds to 127.0.0.1 only; Host and Origin guarded | VERIFIED | `lsof` showed `127.0.0.1:3300`; bad Host returned 403; cross-origin POST returned 403. |
| No telemetry; UI loads nothing from a CDN | VERIFIED (UI) / CLAIMED (backend fully offline) | The built `dist` has no external hosts. basics and qa-sweep report "no requests left localhost". My `lsof` polling of backend sockets during a real run recorded nothing (connections were too short-lived), so it is not evidence either way. `scripts/offline_check.py` was not run by me. |
| The answer is saved before grading and never lost | VERIFIED (code + tests) | `interviews.py:309-318`; `test_concurrency.py`. |
| A duplicate or stale submit gives 409, with exactly one LLM call | VERIFIED | Real run: 4 of 4 duplicates returned 409. The one-LLM-call part is shown by `test_concurrency.py` (mocked model). |
| One interview active at a time | VERIFIED | `409 interview_active` in the real run. |
| Follow-up limit enforced in code | VERIFIED | `interviews.py:645-648`; the real run asked exactly 1 follow-up per question with max 1. |
| The app computes the score, using the documented formula | VERIFIED | Q1 = (7.5 × 2 + 0.5) / 3 = 5.2 in the real report. |
| Quotes are checked; unquoted mistakes are marked unverified | VERIFIED (code) / CLAIMED (rate) | `grounding.py:77-175`. My 12 gradings produced no unverified misconceptions; the benchmark reports 273/279 quotes found. |
| Grading benchmark: 70/70 pairs ranked, 55/56 in band | VERIFIED (re-analysed the committed data) / CLAIMED (that it was produced as described) | `results/2026-11-19-qwen3.5-4b.md`, consistent with the jsonl. I did not re-run all 168 gradings. |
| Grading ranks strong > partial or subtle > wrong on new answers | VERIFIED (small sample) | My 12 answers: ranking held in 4 of 4 questions. One textbook error (CAP "choose CA") scored 5.9 with no misconception flagged. |
| 18-38 s per evaluation on an 8 GB M2 | Partly FALSE as stated | My runs took **28-76 s** per grading (median about 40). My machine was carrying its other workload at the same time, which may have slowed these runs. The benchmark's own median is 44 s and max 150 s, so "18-38 s" is optimistic. |
| PDF, Markdown and JSON export | VERIFIED (PDF) / UNKNOWN (MD, JSON, redaction) | PDF: 200, `application/pdf`, 53 KB. |
| Resume intelligence, OCR, injection flagging | CLAIMED | Covered by mocked-model tests only (README §11 says so). I tested only upload validation. |
| Adaptive interviews (six strategies) | CLAIMED | Pure-function and API tests only, with a mocked model. |
| Voice: Phonon on Apple Silicon, system voices elsewhere, Whisper mic | CLAIMED / partial | Health shows Phonon with 38 voices. Whisper is not installed on my copy (STT unavailable). No audio was played. |
| Windows and Linux supported | CI-verified (tests + `check`) / CLAIMED (start/stop, real use) | CI run 44367320093 (2026-11-18): backend, frontend and launcher smoke test green on windows-latest and ubuntu-latest. Not run on a real machine. |
| Groq cloud mode, opt-in, no silent fallback | CLAIMED | Not tested (no key). One manual real run is claimed; everything else is against a fake server. |
| Real-Chrome suites pass | VERIFIED (2 of ~18) | basics: 53 PASS. qa-sweep: ALL CHECKS PASSED (46 page states, self-test 8/8). |
| Accessibility | Partly VERIFIED | qa-sweep's automated structure checks pass. No screen-reader test (the ROADMAP admits this). |

## 8. What I could not verify, and how to settle each item

| Item | What would settle it |
|---|---|
| Real Windows and Linux use | Run `start.bat` / `./start.sh` plus one full interview on real hardware, and publish a log and screenshots. Get the new launcher start/stop CI step green. |
| That the uncommitted tree passes CI | Commit it and link the green Actions run. |
| Whether grading quality holds beyond the author's labels | Have a second person label 50 or more new answers, without seeing the prompt, and publish the `run.py` output on that set. Include rubric-free questions and subtle-error cases. |
| Fully offline operation | I did not run `scripts/offline_check.py`. Publishing its output, plus a Wi-Fi-off run, would settle it. |
| Groq mode with a real key | `GROQ_API_KEY=… RUN_INTEGRATION=1 pytest -m integration backend/tests/integration/test_real_groq*.py`; publish the output, including a rate-limit hit. |
| Voice answers and the physical microphone | `./setup-models.sh --stt`, then a recorded interview with a real microphone and two accents; publish what the transcript repair changed. |
| Resume parsing quality | Run 10 real or varied PDF resumes (single- and multi-column, scanned) and publish how many sections were extracted correctly. |
| The adaptive engine with the real model | Run one adaptive interview with the real model per strategy and publish the decision logs. |
| Evaluation time | Publish timings from an idle machine alongside a loaded one. Today's README range is lower than both my runs and the benchmark median. |

## 9. Next five actions, in order

1. **Commit the working tree, then get it green in CI on all three OSes**, including the new start/stop step. Then tag v2.0.0 with release notes.
2. **Triage the Dependabot PRs**, make Dependabot keep the lock files in step with the `.txt` files, and **turn on branch protection**.
3. **Commission an independently labelled held-out grading set**, including rubric-free subtle errors, and publish the result next to the existing benchmark.
4. **Show users a "may contain an unflagged error" signal** when there was no rubric and confidence is not high. Document that subtle wrong claims can score 5-8. Correct the 18-38 s timing claim.
5. **Get one real Windows and one real Linux user report** (a full interview) and record it in `docs/verification.md`.

---

## Appendix: working notes and commands

- Scratch copy: `/private/tmp/claude-501/-Applications-Local-AI-Interview/220def82-37b6-4baa-a53f-ef1359e1d4e1/scratchpad/reviewer5/repo`, made from `git ls-files -co --exclude-standard`, excluding `data/`, `logs/` and `reviews/`.
- My scripts and raw outputs are in `…/scratchpad/reviewer5/bench/`:
  - `heldout.py` and `heldout.jsonl`: 12 gradings;
  - `journey.py`, `report.json` and `report.pdf`: the real interview.
- Real-model work was run one job at a time. Memory was tight throughout (the health endpoint reported 1.0 GB available; `memory_pressure` reported 18 % free), which may have inflated the timings.
- A bug in my journey script: it sent the answers in turn order, so Q1's follow-up received an answer about idempotency. The grader correctly scored that follow-up 0.5 (classified "uncertain"). That is a reasonable outcome for an off-topic reply, and it did not affect any other conclusion.
- Everything I started was stopped: `stop.sh` closed port 3300, and the e2e suites closed port 3101. The owner's instance and `data/` were not touched. Ollama was left running because it was not started by me.

Phase notes written during the run:

### Phase 0 notes
- What: a local-first mock-interview web app (FastAPI + React) that asks user/resume questions aloud, takes typed/spoken answers, has a local LLM (qwen3.5:4b via Ollama) grade them with app-computed scores, and writes a report.
- For: individual job-seekers in tech roles who want private practice on their own machine.
- Promises: offline by default, loopback-only, no telemetry; evidence-checked grading; adaptive interviews; resume intelligence; voice in/out; cross-platform (macOS verified, Win/Linux CI only); ~39 s first start; 18-38 s per evaluation on M2 8 GB; grading benchmark 70/70 pairs.
- Size: backend/app 10.1k lines, backend/tests 8.1k, frontend/src 10.1k, frontend/e2e 2.5k, scripts 1.1k. 13 commits, one author.

### Phase 1 notes
- Crowded space; closest twins: GrillKit (13 stars), J3rry320/interview-coach (7 stars), grillme. Edge: app-side deterministic scoring + quote verification + fully local voice loop.

### Phase 2 notes
- `./start.sh` with empty pip/uv/npm caches on APP_PORT=3300: exit 0 in 38.0 s (claim: 39 s). Health endpoint OK.
- check.sh: clear read-only report. Backend: ruff clean; docs checker 25 files OK; pytest 749 passed, 2 skipped, 14 deselected (integration), coverage 94% (6692 stmts, 413 missed), 33 s.
- Frontend: eslint 0 warnings, tsc clean, vitest 20 files / 153 tests passed, line coverage 41.1% (1008/2452); vite build OK.
- npm audit 0; pip-audit on requirements.lock: no known vulns.
- Held-out real-model check running (12 answers I wrote, no rubric).

### Phase 3 notes
- Interview state machine (backend/app/services/interviews.py:304-460, 550-670): compare-and-set guard `_expect`, answer saved before evaluation, stale results dropped in `_apply`. No bug found in submit/skip/pause/end paths. `assert` used as a runtime guard at interviews.py:647 (stripped under -O).
- Largest functions: report_pdf.render_pdf 204 lines; interviews.create 98; reports.render_markdown 92.

### Phase 4 notes
- Host check (bad Host -> 403), cross-origin POST -> 403, bound to 127.0.0.1 only (lsof). All workflow actions SHA-pinned; default permissions contents: read. Dependabot configured. Branch protection: none on main (gh api 404).
- Groq key stored in plaintext in the SQLite settings table (ai_config.py:192-206); data dir 0700 / db 0600 (deps.py:45-48); backup includes the key (documented, system.py:166).

### Phase 5 notes
- 13 commits, all by one author, 2026-11-09..2026-11-18; 2 stars, 0 forks, 0 issues; 10 Dependabot PRs open since 2026-11-15, unanswered, 3 with failing checks. No tags/releases.
- Large uncommitted working tree: 71 files changed (+1808/-348) plus untracked lock files, benchmark, concurrency tests, verification doc. None of this has been through CI; last green CI is for commit f756a87 (2026-11-18).
- Input validation probes on my instance: non-PDF upload -> 400 `not_a_pdf`; 11 MB PDF -> `resume_too_large`; empty question -> `invalid_request` with a readable message. Built UI contains no external URLs except w3.org namespaces and react.dev error links.
- Benchmark re-analysis (committed jsonl): in 7 of 10 questions the "subtle" answer (contains a confidently stated wrong claim) has a higher median score than the "partial" (correct but thin) answer.
- Held-out real-model check (my own 4 questions x 3 answers, no rubric, qwen3.5:4b, same evaluate+finalize path as the benchmark; script and raw output in the reviewer scratchpad bench/heldout.py, heldout.jsonl): strong 8.5/7.8/7.6/7.9; subtle-error 5.5/1.9/3.2/5.9; wrong 0.7/0.6; terse-correct 6.5; buzzword fluff 1.5. Ranking strong > subtle > wrong held in all 4 questions. The CAP answer "most databases choose CA ... stay consistent and available when the network is cut" (a textbook error) got 5.9, "correct_incomplete", no misconception recorded. 28-76 s per grading.

