# Independent review, round 3: Local AI Interviewer

Reviewer: an independent agent with no part in writing the project, 2026-11-20. Reviewed: the working tree at `/Applications/Local_AI_Interview`, branch `review-improvements` (HEAD f756a87 plus about 70 modified and 19 untracked files). Every run used a private copy of that tree in a scratch folder, on port 3217/3218. Neither the owner's `data/` nor port 3000 was touched. Earlier reviews in `reviews/` were not opened.
Labels: **VERIFIED** = I ran or read it; **CLAIMED** = the docs say so and I could not confirm it; **UNKNOWN** = no evidence either way. "CI-verified" = a green GitHub Actions run, not a test on a real machine.

## 1. Verdict

- **What it is:** a single-user, local-first mock-interview app for tech roles. FastAPI + React, started with three commands. A local 4B model (Ollama `qwen3.5:4b`) grades typed or spoken answers. The app (not the model) computes scores, and a scored report comes out at the end. Groq cloud is optional and off by default.
- **Overall score: 6.5 / 10.**
- **Biggest strength:** the engineering around a small model is unusually careful, and I checked it. The answer is saved before grading. Double submits get 409 and only one model call is made. The server binds to loopback with Host/Origin/Sec-Fetch guards. 747 backend tests pass at 94 % line coverage. Install-to-report works first time on an 8 GB Mac.
- **Biggest risk:** what the user is taught is only as right as a 4B model. In my real-model run, a wrong answer ("a tuple containing a list can be a dict key") was listed under *correct points*. It scored 4.5 "partially correct" with no misconception, and the **reference answer shown to the user was itself false**. A second risk: the project has one maintainer, it is 11 days old, nobody uses it yet, and much of what this review checked is not committed.
- **Recommend today?** Yes, as a private practice tool on an Apple Silicon Mac for people comfortable with a terminal, provided they write expected answers (rubrics) for questions they care about. Do not use it as a source of truth for technical facts, and do not use it on Windows or Linux unless you are prepared to report bugs.

## 2. Scorecard

| Area | Score | Reason |
|---|---|---|
| Idea and differentiation | 6 | Real gap: no maintained, end-to-end offline spoken mock interviewer was found. But the idea is easy to copy, and the wider AI mock-interview market is crowded. |
| Does it work | 8 | Clean install (check, then start in 10 s with warm caches). The full real-model journey, PDF and redacted exports all worked. The guards behave as documented. Marked down for the wrong-fact grading seen in the run. |
| Code quality | 7 | Coherent layering, a careful state machine, one gateway for all model traffic. Dense code (157 lines over 160 characters in services), a few 90-200-line functions, an `assert` used as a safety check. |
| Testing | 8 | 747 backend tests at 94 % with a real concurrency test, 152 frontend tests, real-Chrome scripts that pass, and an opt-in real-model benchmark. Frontend unit coverage is only 41 %. |
| Security | 7 | Strong local exposure model. CI actions pinned to SHAs with least privilege. Audits clean. But `main` has no branch protection, the hash locks are not committed, and the API key is stored in plain text (documented). |
| Documentation | 7 | Very thorough and unusually honest about limits. But the README is 566 lines / 65 KB, which is heavy for newcomers, and its "Supported/verified" claims depend on uncommitted work. |
| Ease of adoption | 6 | Three commands, and a setup page that guides the user. But it needs Python, Node and Ollama plus a 4 GB model, 8 GB of RAM is tight, Windows/Linux are CI-only, and there is no packaged release. |
| Project health | 2 | One human committer, 13 commits in 11 days (the first is a 26k-line dump), 2 stars, 0 forks, no tags or releases, 10 Dependabot PRs left open, no branch protection. |
| Proof of core claim | 5 | A real-model benchmark exists (70/70 pairs ranked correctly), but it has 56 answers labelled by the author. Its known miss reproduced in my independent run, together with a false reference answer. |

**Weighting.** The weights follow what decides whether a user should rely on it: proof of core claim ×2, does it work ×2, testing ×1.5, security ×1.5, idea, code and docs ×1, adoption ×1, health ×0.5. The weighted mean is about 6.6. The **core claim is only partly proven** (graded feedback can be confidently wrong), so the total is capped at 7. I round down to **6.5**, because the low health score means none of this is maintained by anyone but one person yet.

## 3. Advantages (verified only)

- **Local by default, and it holds up under test.** The server listens on `127.0.0.1:3217` only (`lsof`). A bad Host header, a foreign Origin, or another localhost port all get 403 (curl, Phase 2). The e2e check "no requests left localhost" passed (`basics.mjs`, 53/53).
- **No lost answers, no double grading.** Three duplicate submits during grading all got 409. The design is in `backend/app/services/interviews.py:303-318` and `:547-607`, and it is tested with 8 truly concurrent threads (`backend/tests/test_concurrency.py`).
- **The app owns the score.** Scores are computed from the dimension ratings with editable weights (`services/evaluator.py:252-289`). Provenance (prompt version, model, temperature, input hash) is stored with every grading (seen in the report JSON).
- **Works on an 8 GB laptop.** A full 2-question interview with a follow-up, 3 gradings and the summary took about 2 minutes (≈30-40 s per grading), which matches README §7.
- **Exports.** A valid 4-page PDF. The redacted Markdown contains no answer text.
- **Healthy test and CI setup.** 747 + 152 tests pass, lint and typecheck are clean, and the last `main` CI run was green on ubuntu, macos and windows (run 44367320093, 2026-11-18). pip-audit and npm audit are clean. Actions are pinned to SHAs.
- **Honest docs.** Limitations are stated, including the exact grading miss I reproduced (`docs/evaluation.md` §8), and `docs/verification.md` logs what was run and when.

## 4. Improvements

**MUST FIX**
1. **Commit (and get CI to run) the work this tree depends on.** That means the hash lock files the launcher now requires (`scripts/manage.py:393`), the 8 new test files, `docs/verification.md`, `scripts/offline_check.py` and the new launcher start/stop CI step. *Why:* today the public repo is not what the README describes, and the Windows/Linux start/stop step has never run. *Where:* git. *Effort:* S.
2. **Do not present the model's reference answer as authoritative when there is no rubric.** Label it "model-written, unchecked" in the UI, PDF and Markdown, and/or show it only when the question has a rubric. Flag contradictions between a main answer's reference and its follow-up's reference. *Why:* in my run the user was taught a false Python fact twice in one report. *Where:* `services/evaluator.py` (finalize), report rendering in `services/reports.py`, `report_pdf.py` and `frontend/src/pages/Report*`. *Effort:* S-M.
3. **Turn on branch protection for `main`** (required CI checks, no force-push). *Why:* a single-maintainer repo has no guard against a bad push. *Where:* GitHub settings. *Effort:* S.

**SHOULD DO**
4. **Grow the grading benchmark beyond self-labelled data.** Add a held-out set labelled by other people, and add subtle-error cases with and without rubrics. Publish the per-kind confusion. *Where:* `backend/benchmarks/grading/`. *Effort:* M.
5. **Triage the 10 Dependabot PRs.** Fix or close the failing ruff bump. Decide on TypeScript 7, ESLint 10 and reportlab 5. *Where:* GitHub PRs #1-10. *Effort:* S-M.
6. **Cut a first tagged release** with the checklist in `docs/maintainers/releasing.md`. *Why:* users need a stable thing to install and to report bugs against. *Effort:* S.
7. **Run once on a real Windows and a real Linux machine** and record the result in `docs/verification.md`. *Effort:* M.
8. **Raise frontend unit coverage** for the Setup, ResumeDetail and Settings pages (41 % lines today). *Effort:* M.
9. **Make the backend log useful at INFO for lifecycle events**, or correct README §9. Uvicorn runs at `warning` (`scripts/manage.py:549`), and `logs/backend.log` stayed empty for my whole session. *Effort:* S.

**NICE TO HAVE**
10. Split `report_pdf.render_pdf` (204 lines), `InterviewService.create` (98) and `reports.render_markdown` (92). Consider a line length closer to 120. *Effort:* M.
11. Replace the `assert` safety check at `services/interviews.py:643` with an explicit error. *Effort:* S.
12. Shorten the README to a landing page and move the storyboard table and API lists into `docs/`. *Effort:* S.

## 5. Who it is for, and who should not use it yet

- **Best for:** software, data or ML job seekers on an **Apple Silicon Mac with 8 GB+ RAM** (16 GB is more comfortable). They should be able to run three terminal commands, should want practice that never leaves the laptop, and should be willing to add expected answers to their important questions. Also good for people who will practise many short technical Q&A rounds and want progress tracking.
- **Not yet for:** non-technical users (no installer; Python, Node and Ollama needed). **Windows/Linux users who expect it to just work** (only CI-verified, never run on a real machine). Anyone who will treat the feedback as factual teaching on subtle topics without a rubric. Intel Macs or machines with less than 8 GB. Teams or bootcamps (single user, no auth). Coding-interview practice (no code execution).

## 6. Competitors and ranking

Sourced by a research sub-agent on 2026-11-20 (GitHub API for stars/pushes, third-party sites for prices; approximate).

| Name | Type | Link | Stars / price | Last activity | Better than this project | Worse than this project |
|---|---|---|---|---|---|---|
| Liftoff | OSS | github.com/Tameyer41/liftoff | ~1.5k | 2023-12 | Polish, video answers | OpenAI-only, abandoned |
| IliaLarchenko/Interviewer | OSS | github.com/IliaLarchenko/Interviewer | ~128 | 2025-03 | Coding and system-design modes, any model | Cloud by default, Gradio UI, quiet |
| GPTInterviewer | OSS | github.com/jiatastic/GPTInterviewer | ~266 | 2024-04 | Job description + resume questions | OpenAI-only, abandoned |
| DeepInterview | OSS | github.com/ngoanpv/DeepInterview | ~74 | 2026-11-16 | Company research, real-time multilingual voice | Cloud keys and a heavy stack, early |
| Multi-Agent-Mock-Interview | OSS | github.com/XUZIAa/Multi-Agent-Mock-Interview | ~148 | 2026-09 | Full-duplex voice, real question bank | Windows/Chinese-focused, realtime cloud voice |
| interview-gym | OSS | github.com/anesriad/interview-gym | ~18 | 2026-07 | Offline Ollama *and* executes code against tests | No voice, default 30B model |
| InterviewWarmupLocal | OSS | github.com/amar-chheda/InterviewWarmupLocal | ~18 | 2024-09 | Same idea (closest match) | Prototype, no reports, inactive |
| intervyu | OSS | github.com/sahu-adarsh/intervyu | ~21 | 2026-06 | Live coding with sandboxed tests | Cloud only |
| Final Round AI | Commercial | finalroundai.com | ~$25-150/mo | active | Breadth, polish | Cloud, cost, "copilot" ethics |
| Yoodli | Commercial | yoodli.ai | free tier, ~$8-20/mo | active | Delivery analytics | Cloud; not technical correctness |
| interviewing.io | Commercial | interviewing.io | ~$179-225/session | active | Real human engineers | Expensive, scheduling |
| Exponent (incl. Pramp) | Commercial | tryexponent.com | ~$79-99/mo | active | Peer mocks, courses | Subscription, mostly not AI-graded |
| Google Interview Warmup | Commercial (free) | grow.google/interview-warmup | free | reportedly shut down (UNVERIFIED) | Was simple and free | No scores, no resume |

**Ranking.** Among *offline, privacy-first* tools it is the most complete and the most carefully engineered of the projects found: first of about 3 real contenders. Across the whole market it is a niche option. Human mocks (interviewing.io) and cloud products beat it on feedback quality, and none of the OSS projects in its niche has traction, this one included (2 stars).

## 7. Promise check

| # | Promise | Status | Evidence |
|---|---|---|---|
| P1 | Offline by default; no cloud, keys or telemetry | VERIFIED (local mode, in-app) / CLAIMED (full network-off) | Health `local_only:true`; e2e "no requests left localhost"; `scripts/offline_check.py` sandbox result is the maintainer's (not rerun) |
| P2 | Loopback only, Host/Origin guarded | VERIFIED | `lsof` 127.0.0.1 only; 403 for foreign Host, foreign Origin, other localhost port |
| P3 | Three-command install; cold start 39-49 s | VERIFIED (works) / CLAIMED (timing) | check exit 0; start 9.8 s with warm caches; cold-cache timing not reproduced |
| P4 | Answer saved first; duplicate submit → 409, one call | VERIFIED | 3/3 duplicates 409 in the real run; `test_concurrency.py` |
| P5 | App computes the score; unverifiable quotes flagged | VERIFIED (mechanism) | `evaluator.py:252-289`; provenance in the report JSON. Note: a verified quote does not mean the judgement is correct |
| P6 | 70/70 pairs ranked, 55/56 in band | CLAIMED (not rerun); its known miss VERIFIED | My run reproduced the tuple/list miss, with a false reference answer |
| P7 | Adaptive interviews, six strategies | CLAIMED | Mocked-model tests only (`test_adaptive_*`); not run with a real model |
| P8 | Resume intelligence, injection flagged, per-resume consent | PARTLY VERIFIED | `not_a_pdf` rejection verified; parsing and questions only in mocked tests; consent enforcement read in `gateway.py:100-121` |
| P9 | PDF/MD/JSON and share-safe exports | VERIFIED (PDF, redacted MD) | 4-page valid PDF; redacted MD contains no answers |
| P10 | Cloud strictly opt-in, budget before each call, no silent fallback | VERIFIED by code reading / CLAIMED in practice | `gateway.py:94-143`; real Groq not tested (no key) |
| P11 | macOS Apple Silicon verified; Windows/Linux CI-only | VERIFIED as stated | My Mac run; CI run 44367320093 green on windows/ubuntu (CI-verified, not real machines); new start/stop step never ran in CI |
| P12 | 746 tests, 94 %; 152 frontend tests, 41 % | VERIFIED | 747 passed / 2 skipped, 94 %; 152/152, 41.1 % |
| P13 | Hash locks, SHA-pinned CI, audits clean | VERIFIED in the tree; FALSE for the public repo | Locks untracked in git; pins and audits verified |
| P14 | Phonon / OS voices; offline Whisper | CLAIMED | Health showed Phonon installed with 38 voices; STT not installed; not exercised |
| P15 | 18-38 s per evaluation on an 8 GB M2 | VERIFIED (≈30-40 s) | 3 gradings + summary in ~2 min |
| P16 | Early load, unload when idle, low-memory warning | CLAIMED | Logic read (`sysmem.py:69-73`); not measured (the owner's Ollama was shared) |

## 8. What I could not verify, and how to settle it

| Item | What the maintainer could run or publish |
|---|---|
| Real Windows / Linux behaviour | A screen recording or log of `start.bat` → interview → report on a real Windows 11 and Ubuntu machine, added to `docs/verification.md`; and a green CI run of the new launcher start/stop step after committing it |
| Grading quality beyond self-labelled data | A held-out answer set labelled by 2+ outside people, with inter-rater agreement and the app's agreement, published under `backend/benchmarks/grading/results/` |
| Real Groq cloud mode (rate-limit wait, fallback, budget) | Run `GROQ_API_KEY=… pytest -m integration backend/tests/integration` and publish the log; one deliberate rate-limit run |
| Adaptive and resume flows with the real model | A real-model e2e run of `resumes.mjs` (it uses a fake model today) and of one adaptive interview, with the report attached |
| Fully offline (network off) | Rerun `scripts/offline_check.py` in CI on macOS, or publish its log; repeat by hand with Wi-Fi off |
| Cold-start timing and model download time | `time ./start.sh` on a fresh clone with empty caches, and `time ./setup-models.sh` on a clean machine |
| Voice (TTS/STT) quality and physical microphone | A manual test with a real microphone and 2-3 accents; `e2e/mic.mjs` output |
| Remaining e2e suites (full-flow, ui-audit, cloud, resumes, …) | They exist; publish CI artifacts from a Linux job that runs them |

## 9. Next five actions, in order

1. Commit the uncommitted work (locks, tests, docs, CI step), get one green CI run on all three OSes, and turn on branch protection.
2. Label model-written reference answers as unchecked (or hide them without a rubric), and flag contradictions inside a report.
3. Build an externally labelled, held-out grading set with subtle-error cases, and publish the results, including where it fails.
4. Tag v2.0.0 with release notes, and triage the 10 Dependabot PRs.
5. Get one real Windows and one real Linux run recorded (ask in an issue labelled `help wanted`), and update README §2 from those runs.

---

# Appendix: phase notes (written during the review)

## Phase 0 notes: orientation

**Size (lines, VERIFIED with `wc -l`):** backend/app 10,091 (Python); backend/tests 8,050; backend/benchmarks 377; frontend/src 9,054 (TS/TSX/CSS); frontend/e2e 2,468; scripts 1,081; docs 1,192; README 566 lines (65 KB); guide.md 248. Largest files: `backend/app/services/interviews.py` 819, `reports.py` 698, `resumes.py` 636, `schemas.py` 528, `frontend/src/pages/Setup.tsx` 448.

**Three sentences.** A single-user web app (FastAPI + React, launched by a Python stdlib launcher) that runs mock technical interviews: it speaks your questions, takes typed or spoken answers, grades them with a local 4B LLM via Ollama (or, opt-in, Groq cloud) and produces a scored report. It is for job seekers in tech who want private practice on their own laptop, including 8 GB machines. It promises privacy (offline by default, loopback only, no telemetry), deterministic app-side scoring with evidence-checked feedback, adaptive and resume-based interviews, and cross-platform support.

**Promise list (checked in Phase 2):**
1. P1 Runs fully offline by default; no cloud, no API keys, no telemetry (README L26, L147).
2. P2 Server binds 127.0.0.1 only; Host/Origin guarded (README L26, L113, §10).
3. P3 Install with 3 commands; first start 39-49 s excluding model (README L176).
4. P4 State machine: answer saved before evaluation; double submit -> 409, one LLM call (README L113-119).
5. P5 App (not model) computes scores from dimension scores; unverifiable quotes flagged (README L47, §6).
6. P6 Grading quality: 70/70 pairs ranked, 55/56 in band on own benchmark (README L473-476, docs/evaluation.md §8).
7. P7 Adaptive interviews with six strategies and time limit (README L48).
8. P8 Resume intelligence: PDF parsing, OCR optional, injection flagged, per-resume cloud consent (README §5a).
9. P9 Reports with PDF/Markdown/JSON and share-safe redacted exports (README L50, L266).
10. P10 Cloud mode (Groq) strictly opt-in, consent, budget enforced before every call, never silent fallback (README §7a).
11. P11 Platforms: macOS Apple Silicon fully verified; Windows/Linux implemented, CI-only (README §2).
12. P12 Tests: backend 746 passed, 94% coverage; frontend 152 tests, 41% coverage; lint/typecheck clean (docs/verification.md).
13. P13 Supply chain: hash-locked Python deps, SHA-pinned least-privilege CI, Dependabot, pip-audit/npm audit clean (CHANGELOG).
14. P14 Voice: Phonon TTS on Apple Silicon, OS voices elsewhere (localService only); Whisper STT offline (README §2, §8).
15. P15 Evaluation 18-38 s per answer on M2 8 GB (README §7).
16. P16 Model memory: loads early, unloads when idle, warns on low memory (README §7).

## Phase 1 notes: idea and market

**Problem.** Interview practice is a real pain (anxiety, cost of human mocks: interviewing.io charges roughly $179-225 a session; commercial AI tools ~$8-150/month), and existing AI mock tools send your answers and resume to a cloud. The privacy angle matters to a minority of candidates; the cost angle matters to many. Pain: moderate, widespread.

**Alternatives** (stars and last push from the GitHub API on 2026-11-20 via a research sub-agent; commercial prices from third-party review sites, approximate): see section 6 table. Open source: Liftoff (~1.5k stars, last 2023-12, OpenAI-only, abandoned), IliaLarchenko/Interviewer (~128, 2025-03, coding/system design, any model incl. local), GPTInterviewer (~266, 2024-04, OpenAI), DeepInterview (~74, 2026-11-16, cloud voice stack), Multi-Agent-Mock-Interview (~148, 2026-09, full-duplex voice), interview-gym (~18, 2026-07, offline Ollama, executes code), InterviewWarmupLocal (~18, 2024-09, closest match, abandoned prototype), intervyu (~21, 2026-06, cloud). Commercial: Final Round AI, Yoodli, interviewing.io, Exponent (absorbed Pramp), Google Interview Warmup (reportedly shut down in 2026, UNVERIFIED).

**Differentiation.** "AI mock interviewer" is crowded; "fully offline spoken interview on an 8 GB laptop with local TTS + STT + small-model grading, resume questions and scored reports" is nearly empty: the only close match found is an abandoned prototype. **Edge in one sentence:** it is the only actively maintained, end-to-end offline spoken mock interviewer that a non-developer can start with three commands and that measures (on its own small benchmark) whether its small-model grading ranks answers sensibly. Weaknesses vs field: no live code execution, no real-time interruptible voice, no job-description/company research, 4B grading quality, and zero adoption so far. The idea is easy to copy (Ollama + Whisper + a prompt); the moat is the engineering around reliability, not the idea.

## Phase 2 notes: does it work (all VERIFIED unless marked)

Environment: MacBook (Apple Silicon, 8 GB), macOS 26.5.2, Python 3.13.5, Node 24.2, Ollama 0.40.16 with `qwen3.5:4b` and `phonon` already installed (by the owner, so model download time was not measured). Private copy of the working tree, `APP_PORT=3217`.

**Install, following README Quick start.**
- `./check.sh`: exit 0, 1.7 s, clear report (Node, Python, Ollama, model, Phonon, Tesseract found; deps "not installed yet").
- `./start.sh`: exit 0 in 9.8 s (warm uv/npm caches on this machine, so not comparable to the README's 39-49 s cold figure). Prints the URL and "bound to 127.0.0.1 only". Nothing unclear. Not done: `./setup-models.sh` (models already present) and a cold-cache start.
- `lsof` shows `127.0.0.1:3217` only. `GET /api/health` returns `local_only: true`. Host `evil.example` -> 403; POST with `Origin: http://evil.example` -> 403; POST with `Origin: http://localhost:9999` (other local port) -> 403.
- `./stop.sh`: stopped the backend, left the (not-ours) Ollama running, port closed.

**Static checks and tests (in the copy):**
| Check | Result |
|---|---|
| `ruff check .` | All checks passed |
| `python3 scripts/check_docs.py` | 25 Markdown files OK (reviews/ folder not copied, hence not 27) |
| `pytest backend --cov=backend/app` | **747 passed, 2 skipped, 14 deselected (integration), 94 % line coverage**, 28 s. One deprecation warning (Starlette testclient/httpx) |
| `npm run lint` / `typecheck` / `build` | clean / clean / built |
| `npm run coverage` (Vitest) | **152 / 152 passed, 41.1 % lines** (37 % statements, 28.6 % functions) |
| `pip-audit` on `requirements.lock` and `requirements-dev.lock` (`--require-hashes`) | no known vulnerabilities |
| `npm audit` | 0 vulnerabilities |
| Real-Chrome e2e suites | NOT run (time and memory budget on an 8 GB machine; UNKNOWN beyond the maintainer's log in docs/verification.md) |

**Main user journey, real model (`qwen3.5:4b`, local mode), via the HTTP API the UI uses** (script in my scratchpad): create set, add 2 questions (one with rubric), start a fixed interview (follow-ups max 1, `at_end`), answer, finish, report, PDF, redacted Markdown export.
- Q1 process vs thread (rubric, strong answer): **8.2 "Good"**, no follow-up.
- Q2 "Can a tuple that contains a list be a dict key?" (no rubric) answered **wrongly** ("Yes, any tuple is hashable ... even if it contains a list"): **4.5 "Weak", classification `partially_correct`, zero misconceptions**. The grader listed "A tuple containing a list can be used as a dictionary key" under *correct points*, and the **reference answer shown to the user is also wrong** ("Yes, but ... if you try to modify the list inside the tuple, Python will raise a TypeError"). In reality `hash((1, []))` raises `TypeError: unhashable type: 'list'`. The follow-up it asked was reasonable; its *own* reference answer for the follow-up said the opposite ("No ... raises a TypeError"), so one report contains two contradictory model answers. This is the same miss the project's own benchmark records (docs/evaluation.md §8), now reproduced on a fresh run, and it shows the downstream harm: the user is taught a false fact.
- Follow-up answer "I am not sure..." -> 0.6, `no_attempt`. Final 5.7 "Partial". 3 gradings + summary in about 2 minutes total (≈30-40 s per grading), consistent with README §7 (18-38 s).
- Every duplicate submit of the same turn got **409** while the first was evaluating (3 of 3).
- Report summary (`narrative_status: ready`) within about a minute after finishing. It says the candidate "failed to explain the critical requirement for inner list elements" rather than "the answer was wrong".
- PDF export: 200, `application/pdf`, valid 4-page PDF. Redacted Markdown export: contains neither answer text (grep 0 hits).
- Input validation: an 8,001+ character answer -> 400 `answer_too_long`; a text file named `.pdf` -> `not_a_pdf`; `DELETE /api/interviews` without `confirm=true` -> 400.
- Resume upload with the real model, adaptive mode, voice in/out and cloud mode: NOT exercised with real models (UNKNOWN beyond mocked tests).
- `logs/backend.log` stayed empty for the whole session (uvicorn runs at `--log-level warning`, `scripts/manage.py:549`), so "logs contain ids and timings" (README §9) only holds for warnings and resume jobs. Minor.

**Core claim.** The project lives or dies on: *a small local model on an ordinary laptop gives grading and feedback good enough to practise with, privately.* Evidence: (a) the privacy half is well supported (loopback binding and guards verified above; offline sandbox check CLAIMED by the maintainer on 2026-11-19); (b) the grading half has a real-model benchmark, but it is small (56 answers, 10 questions), labelled by the author, on one machine, and its documented miss (plausible wrong claims without a rubric) reproduced in my single run, including a wrong reference answer. So the core claim is partially proven: ranking good vs bad answers is plausible; *correctness of feedback on subtle errors* is not, and the UI presents the model's reference answer as authoritative.

**Repo vs. public state.** The reviewed working tree has about 70 modified and 19 untracked files (1,748 insertions), including the hash lock files the launcher now requires (`scripts/manage.py:393`), 8 new test files, `docs/verification.md` and a new CI launcher start/stop step. The last green CI run (`gh run view 44367320093`, 2026-11-18, all 11 jobs green on ubuntu/macos/windows) is for commit f756a87, **not** this tree. Anything in this review that depends on uncommitted files is not yet what a person cloning GitHub gets.

Real-Chrome e2e (added after the above, no model needed, `E2E_PORT=3218`): `basics.mjs` 53 PASS / 0 FAIL (51 s, incl. "no requests left localhost"); `qa-sweep.mjs` "ALL CHECKS PASSED" (46 page states, no accessibility/structure problems by its own automated rules). Other e2e suites not run (UNKNOWN).

## Phase 3 notes: code and architecture

- **Coherent, and matches the docs.** Routers -> services -> SQLite, one FastAPI process serving the built UI; an `LLMGateway` (`backend/app/services/gateway.py`) is the single routing point for local vs cloud, budget and per-resume consent, as `docs/architecture.md` says.
- **Trace 1, answer submission** (`services/interviews.py:303-662`): compare-and-set inside `BEGIN IMMEDIATE` (`db.py:266-269`), answer persisted before the model call, single-worker executor, `_evaluate` catches `LLMError`, `AppError` and any `Exception` and moves to `evaluation_failed` (L585-601); `_apply` re-checks phase/turn and drops stale results (L615); `recover()` turns a stuck `evaluating` into Retry on restart (L57-65). I found no race or data-loss bug here; the real-concurrency test (`backend/tests/test_concurrency.py`, 8 threads behind a barrier, real worker) checks behaviour, not mocks of the hard part. One nit: a safety invariant uses `assert` (L643), which `python -O` would strip.
- **Trace 2, scoring** (`services/evaluator.py:252-289`): the model supplies dimension scores and lists; `eval_profiles.score_answer` computes the score; quotes are verified (`grounding.py`). Limitation shown in Phase 2: verification only checks that a *quote exists*; it cannot detect that the model filed a false claim under "correct points", and the model-written `ideal_answer` is shown without any check.
- **Trace 3, cloud routing** (`gateway.py:94-143`): budget checked before every call (a single call can still overshoot the limit by its own cost, which is inherent); no-retry codes enforced; local fallback only for essential work and only when enabled. Consistent with README §7a.
- **Test quality.** 747 backend tests; HTTP-level tests use a fake Ollama via `httpx.MockTransport`, which is the right seam. Real-model coverage is opt-in (`backend/tests/integration`, 14 deselected by default) plus a benchmark script; they did not run in my default suite. Frontend unit coverage is low (41 % lines); pages are mainly exercised by real-Chrome scripts that CI only partly runs.
- **Maintainability.** Largest functions: `report_pdf.render_pdf` 204 lines, `InterviewService.create` 98, `reports.render_markdown` 92. Code is dense: 157 lines over 160 characters in `backend/app/services/*.py` (ruff line-length is 160 and only bug rules are enabled; a style choice, not a defect, but it slows reading). Dependencies are few (8 runtime Python packages, 3 runtime npm packages, no frontend router/state library). Freshness: 10 Dependabot PRs open since 2026-11-15, unmerged, including ruff 0.8.6 -> 0.17.5 (its CI run failed), TypeScript 7, ESLint 10, reportlab 5.
- **First-hour contributor.** Plausible: `docs/development.md`, a single `pytest` command that runs in under 30 s, ruff with only bug rules, ADRs. The 566-line README and comment-dense code are the main friction.

## Phase 4 notes: security and supply chain

| OpenSSF-style check | Finding (VERIFIED) |
|---|---|
| Pinned dependencies | GitHub Actions all pinned to 40-char SHAs (26 `uses:` lines). Python installed from hash locks with `--require-hashes` (`scripts/manage.py:393-397`) **but the lock files are untracked in git**, so the public repo does not have them yet. npm via `package-lock.json`. |
| Token permissions | Every workflow defaults to `contents: read`; only the release job gets `contents: write`. |
| Dependency update tool | Dependabot configured (pip, npm, weekly). 10 PRs open and untriaged. |
| Security policy | `SECURITY.md` with private reporting and a clear threat model. |
| Branch protection | **None** on `main` (`gh api .../branches/main/protection` -> 404 "Branch not protected"). |
| Binary artifacts | None found in the tree (no exe/dll/so/dylib/jar/whl). |
| Known vulnerabilities | pip-audit: none in either lock; npm audit: 0. |
| SAST | CodeQL in `security.yml` (CLAIMED to run; last Security run on main green 2026-11-18). |

- **Network exposure:** loopback bind, Host allow-list (DNS rebinding), Origin same-app check for non-GET, `Sec-Fetch-Site` check for all `/api`, frame-ancestors/nosniff headers (`backend/app/main.py:66-97`); verified with curl. There is no authentication: any local process can call the API (documented, README §11).
- **Secrets:** a Groq key, if entered in the UI, is stored in plain text in SQLite (documented; `GROQ_API_KEY` env alternative). `GET /api/backup` returns the whole DB including that key (documented in SECURITY.md).
- **What leaves the machine:** local mode: nothing beyond 127.0.0.1 in my e2e run ("no requests left localhost"); cloud mode: question, rubric, answers and (with per-resume consent) resume text to Groq. Matches the docs.
- **Input validation:** Pydantic limits on all bodies, answer length cap, PDF magic-byte check, size/page limits (checked above for answer and PDF).

## Phase 5 notes: project health (VERIFIED with git and gh on 2026-11-20)

- **History:** 13 commits, 2026-11-09 to 2026-11-18, one human author, plus Dependabot. The first commit added 26,404 lines in one go; 10 commits landed on 2026-11-15, several of them over 900 lines (`git log --shortstat`). That pattern means the history cannot be used to review how the code evolved.
- **Bus factor:** 1. ROADMAP.md says so.
- **Releases:** no tags, no GitHub releases (`git tag` empty; CHANGELOG "No version has been tagged"). A release workflow exists.
- **Responsiveness:** 10 Dependabot PRs, all opened on 2026-11-15, still open; two of them failed CI. No human issues or PRs to judge response time.
- **Adoption:** 2 stars, 0 forks, 0 watchers; the repo was created on 2026-11-09. Discussions are disabled.
- **License:** MIT, clear; the bundled font's OFL is stated.
- **Governance:** CODE_OF_CONDUCT, CONTRIBUTING, SUPPORT, SECURITY, issue templates, ADRs and a maintainer release guide. That is generous for an 11-day-old one-person project. It is not a problem, but it is process ahead of community.
- **Six months without the maintainer:** the app would keep working locally (pinned dependencies, local model), but nobody would merge security updates. Ollama model tags or Groq API changes would break it with no one to fix it. Survival depends entirely on one person.

## Phase 6 notes: user and contributor experience

- **Onboarding:** `check.sh` output is clear and actionable. `start.sh` explains what it is doing. Error messages I triggered are plain English with a code (`answer_too_long`, `not_a_pdf`, `confirm_required`, 409 `wrong_phase`). `guide.md` gives a gentler path than the 566-line README.
- **Doc accuracy:** the numbers I could check matched (94 % backend, 41 % frontend, 152 frontend tests, green CI on 2026-11-18). One small drift: README §9 says logs contain ids and timings, but at the default log level the backend log stayed empty for my whole session. The README's platform section is careful to separate CI from real machines.
- **Accessibility:** an automated sweep (`qa-sweep.mjs`, 46 page states: unnamed controls, headings, duplicate ids, overflow) passed for me. No screen-reader test exists (ROADMAP admits this). Keyboard shortcuts and a command palette exist (CLAIMED; not exercised by me).
- **Platform coverage:** tested on macOS Apple Silicon (by me and the maintainer); Windows and Linux are CI-verified only for the committed tree (backend tests, frontend build, launcher `check`); Intel Mac is untested.

## Load note

The real-model run, the test suites and the Chrome suites were run one after another, never at the same time. The owner's own Ollama was shared (the health check showed the model already loaded and 1.5 GB of RAM free at the start), so the grading times may be slightly optimistic (no cold load) or pessimistic (memory pressure). Neither affects the pass/fail findings.
