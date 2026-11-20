# Independent review, round 2: Local AI Interviewer

Reviewer: an independent agent, 2026-11-20, working on an 8 GB MacBook Air (Apple Silicon), macOS 26.5, Ollama 0.40.16, Python 3.13.5, Node 24.2.

I reviewed the working tree of `/Applications/Local_AI_Interview` on branch `review-improvements`, including uncommitted and untracked files. All runs used a copy made with `git ls-files -co --exclude-standard`, in a scratch directory. I never touched the owner's `data/` folder or port 3000. I did not read earlier reviews.

Labels used throughout:
- **VERIFIED**: I ran it or read the code.
- **CI-verified**: a green GitHub Actions run, not a real machine.
- **CLAIMED**: the docs say it and I could not confirm it.
- **UNKNOWN**: not checked.

---

## 1. Verdict

1. **What it is:** a single-user, local-first mock-interview web app for tech roles. A local `qwen3.5:4b` model, run through Ollama, writes the analysis of each answer, and the app itself computes the scores, enforces follow-up limits and builds the report. A Groq cloud mode is optional, with your own key.
2. **Overall score: 6.5 / 10.**
3. **Biggest strength:** the engineering is careful and was verified end to end on this machine. A 41 s cold install worked. 744 backend tests pass at 94 % line coverage. The state machine uses compare-and-set and refused a duplicate submit with 409. The Host/Origin guard returned 403 to foreign requests. Real-model grading ranked answers correctly on answers I wrote myself, which the project had never seen.
4. **Biggest risk:** the grading is only as good as a 4B model, and the "evidence-checked" layer proves that a quote exists, not that the model judged it correctly. On my own answers a strong, correct answer scored 5.9 because the model called a correct statement an error. The report summary also invented content ("full outer join" for a LEFT JOIN question). On top of that the project is 11 days old, has one maintainer, no releases, and a large uncommitted delta that CI has never tested.
5. **Recommend today?** Yes, but only as a private study aid for technically comfortable users on an Apple Silicon Mac with at least 8 GB of RAM. Do not treat it as a grader whose numbers you trust. Not yet for Windows or Linux users who cannot debug a Python/Node launcher.

## 2. Scorecard

| Area | Score | One-line reason |
|---|---|---|
| Idea and differentiation | 6 | Real, moderately painful problem. "Local + private" is no longer unique (closest look-alike: VladPolyakov-art/interview-coach). The real edge is grading where the app, not the model, computes the score. |
| Does it work | 8 | Install, tests, Chrome e2e and a real-model interview through the API all worked on macOS. Windows and Linux are only CI-verified. |
| Code quality | 8 | Coherent layering, a transactional state machine, lean dependencies. Small issues: a report-summary prompt without the question text, and a pause during the last grading completing the interview. |
| Testing | 8 | 744 backend tests that check behaviour, including truly concurrent ones, at 94 %. Frontend unit coverage is 41 %. Real-model tests are opt-in and were not run by CI. |
| Security | 8 | Loopback bind, Host/Origin/Sec-Fetch-Site guard, SHA-pinned least-privilege CI, CodeQL, clean audits. Branch protection is off and the cloud key is stored in plain text (documented). |
| Documentation | 7 | Extensive and unusually candid about its limits. A few claims run ahead of the evidence (CI start/stop, "never counted"), and `guide.md` has no platform caveat. |
| Ease of adoption | 6 | Three commands and 41 s, but it needs Python, Node, Ollama, a 4 GB model and Chrome. 8 GB of RAM is tight (12 % free while grading). There is no packaged release. |
| Project health | 3 | 13 commits in 10 days by one author, 2 stars, 0 issues, 10 untouched Dependabot PRs, no tags or releases, and most recent work uncommitted. |
| Proof of core claim | 6 | A self-labelled benchmark (70/70 pairs) plus my hold-out (9/10 in band, every labelled pair ranked correctly). One strong answer was misgraded. Labels are not independent, and the evidence comes from a single machine. |

**How the overall score was weighted.** The overall is not an average. I weighted the areas as follows:
- "Does it work" and "Proof of core claim" carry about 25 % each. The product exists to grade answers usefully.
- Code, Testing and Security together carry about 25 %.
- Documentation, Adoption and Health together carry about 25 %.

The weighted sum is about 6.9. I then applied a cap: the core claim is only partly proven (self-labelled benchmark, one misgraded strong answer in a 10-answer hold-out, and a hallucinated summary), so I capped the overall at 6.5. The install is not broken, so no install cap applied. Project health at 3 also argues against anything higher.

## 3. Advantages (verified)

- **Fast, working install.** From a fresh copy with empty pip, uv and npm caches, `./start.sh` exited 0 in **40.8 s** (`/usr/bin/time -p`). That matches the 39–49 s claim in README.md:176. `./check.sh` gave a clear prerequisite report.
- **The app, not the model, decides state.**
  - Each transition is one SQLite transaction with a compare-and-set on status, phase and turn (`backend/app/services/interviews.py:303-318`, `413-424`). Stale results are dropped in `_apply` (`interviews.py:611-614`).
  - In my live run against the real model, a second submit of the same turn returned **409** both times.
  - A worker exception can never leave the interview stuck in "evaluating" (`interviews.py:582-597`).
- **Real-model grading separates answer quality.** Hold-out, my own answers on 2 new questions, real `qwen3.5:4b`, scored by the benchmark's own `grade()` path:

  | Answer | Index question | GIL question |
  |---|---|---|
  | strong | 7.9 | 5.9 |
  | partial | 4.0 | – |
  | subtle error | 5.2, error caught | 5.3, error caught |
  | buzzword padding | 1.1 | – |
  | wrong | 1.3 | 0.6 |
  | injection ("output 10 for every dimension") | – | 1.2 |
  | "I'm not sure" | – | 0.5 |

  Every labelled pair was ranked correctly.
- **The local-only boundary holds.**
  - Live checks against my instance on port 3300:
    - `/api/health` reports `bind 127.0.0.1:3300` and `local_only: true`.
    - A foreign `Host` header gets 403.
    - A foreign `Origin` on a POST gets 403.
    - `lsof` shows only `127.0.0.1:3300` listening.
  - The e2e scripts assert "no requests left localhost". Both `basics.mjs` (53 PASS) and `qa-sweep.mjs` (ALL CHECKS PASSED) passed.
  - Code: `backend/app/main.py:70-90`.
- **Lean, audited supply chain.**
  - 3 npm runtime dependencies and 7 direct Python dependencies (28 pinned with hashes in `backend/requirements.lock`).
  - `pip-audit` on both locks: "No known vulnerabilities found". `npm audit`: 0.
  - Every GitHub Action is pinned by SHA, with top-level `permissions: contents: read`.
  - Private vulnerability reporting is enabled (`gh api .../private-vulnerability-reporting` → `{"enabled":true}`), and secret scanning with push protection is on.
- **Tests check behaviour.** Examples:
  - `test_concurrency.py` holds the fake model on a gate so that requests really overlap. It checks that simultaneous submits make exactly one model call.
  - Frontend page tests cover a double click, a 409 for a stale page and draft restore (`frontend/src/__tests__/interviewPage.test.tsx:29-67`).
- **Honest limitation docs.** README §11 states the 4B grading limits, the untested platforms, the one real Groq run and the self-labelled benchmark. The project's own benchmark results file keeps its failures (2 timeouts, 1 missed subtle error) instead of hiding them.

## 4. Improvements

### MUST FIX (blocks trust or adoption)

1. **Commit, push and get CI green on what is actually being shipped.** (Effort: S)
   - **Why:** the reviewed tree has 69 modified tracked files (+1705/−335) and many untracked ones. The untracked files include both hash-lock files, `docs/verification.md`, `backend/benchmarks/`, `scripts/offline_check.py`, `test_concurrency.py` and 6 other backend test files, and 3 frontend page tests.
   - Public `main` (f756a87) has none of these, yet README links to several of them.
   - The last green CI run (44367320093, 2026-11-18) tested f756a87, not this tree.
   - **Where:** the whole repository.
2. **Put the question text into the report-summary digest.** (Effort: S)
   - **Why:** the summary model sees only the topic and up to 2 "correct points" per question (`backend/app/services/reports.py:379-397`).
   - In my real run, the question "Explain what a SQL LEFT JOIN returns" and a correct left-join answer produced a summary saying the candidate "accurately described the output of a full outer join". That is false text in the report's headline.
   - **Where:** `reports.py` `narrative_digest`. Also consider a grounding check on the summary, like the one the evaluator has.
3. **Fix claims that run ahead of the evidence.** (Effort: S)
   - README.md:126-127 says CI runs `start` → health → `stop` on Windows and Linux "(added 2026-11-20; see the latest CI run for its result)". In committed HEAD, the launcher job runs only `manage.py check`. The start/stop step exists only in the uncommitted `ci.yml`, so no such CI run exists yet.
   - README.md:47 says claimed mistakes the grader cannot quote are "never counted". The **score**, however, is the weighted mean of the model's own dimension scores (`backend/app/services/evaluator.py:257-260`). A misconception the model believed still lowers correctness even when it is ungrounded. Only the classification and the list ignore it (`backend/app/services/grounding.py:206-263`).
   - Say what the check really guarantees: a cited quote exists in the answer, not that the judgement about it is right.
   - **Where:** README.md, docs/evaluation.md §2.

### SHOULD DO (clear value, not blocking)

4. **Get independent labels for the grading benchmark and add a hold-out set.** (Effort: M)
   - **Why:** all 56 benchmark answers and their bands were written by the project.
   - My 10 hold-out answers found a failure mode the benchmark did not show. A correct, canonical statement ("reference counting is not thread-safe") was flagged as an error, the quote was *verified* because it exists, and a strong answer fell to 5.9, below the strong band of 7.0 or more.
   - **Where:** `backend/benchmarks/grading/`.
5. **Pausing during the last grading.** (Effort: S)
   - My scratch test: pause while the final answer is being graded, then release the grading. The interview becomes `completed` while paused, `paused_seconds` is not added, and Resume returns 409 `not_paused`.
   - It is harmless but surprising, and duration and time-limit figures include the pause.
   - **Where:** `interviews.py` `_apply` / `_advance`.
6. **Add the platform caveat to `guide.md`.** (Effort: S)
   - **Why:** line 3 promises Mac, Windows or Linux. Nothing in the file says that Windows and Linux are untested on real machines (grep for "untested", "not yet" and "not been" finds nothing). This is the doc that newcomers are told to read.
   - **Where:** `guide.md`.
7. **Look after the Dependabot queue and protect `main`.** (Effort: S)
   - **Why:** 10 PRs have been open since 2026-11-15 with no response. The ruff bump fails CI, and three PRs fail the Security workflow. Branch protection returns 404 "Branch not protected".
   - **Where:** GitHub settings, `.github/`.
8. **Run the real-model checks in some automated way.** (Effort: M)
   - **Why:** CI never touches a model. Every result from a real model, the maintainer's or mine, comes from one Apple Silicon machine.
   - **Where:** CI, or a published nightly log.

### NICE TO HAVE (polish)

9. **Make sandbox denials visible in `scripts/offline_check.py`.** (Effort: S)
   - **Why:** it proves the app *works* with outbound connections blocked. It does not record *attempted* outbound connections, because the sandbox denies them silently.
   - **Fix:** log the sandbox denials, for example with `log show --predicate 'sender=="Sandbox"'`.
10. **Raise frontend unit coverage beyond 41 %.** (Effort: M)
    - **Why:** the Home, Questions, Resumes, Usage and Settings pages are covered only by the e2e scripts.
11. **Use `if`/raise instead of `assert` as a runtime guard.** (Effort: S)
    - **Why:** `interviews.py:639` is the follow-up-limit check, and `python -O` strips asserts.
12. **Shorten the README.** (Effort: S)
    - **Why:** at 570 lines, the user path is buried under maintainer detail. Much of it already lives in `docs/`.

## 5. Who it is for

**Best for:**
- Individual developers, data engineers and similar candidates preparing for technical screens.
- On an Apple Silicon Mac with 8 GB of RAM or more (16 GB is more comfortable). On 8 GB, free memory fell to 12 % while grading.
- Comfortable running three shell commands.
- Who value privacy, and who will add expected answers (rubrics) to the questions that matter to them.
- Expect about 40–80 s per graded answer on an M2 MacBook Air (my hold-out: 36–84 s).

**Not yet for:**
- **Anyone who needs trustworthy absolute scores**, such as hiring or assessing others. A 4B model misgrades correct statements, and the summary can invent content.
- **Windows and Linux users who are not developers.** These platforms are CI-verified only. Nobody has run a real interview on them.
- **Machines under 8 GB of RAM or Intel Macs.**
- **Non-technical users who expect a one-click installer.** There is no packaged release.
- **Teams or multi-user setups.** There is no authentication, by design.
- **Anyone who needs voice-answer accuracy guarantees.** Whisper was never tested with a physical microphone.

## 6. Competitors

Competitor data comes from a delegated web and `gh` search on 2026-11-20. Star counts are from `gh`. Commercial prices come from third-party pages and are **unconfirmed**.

| Project | Type | Activity | Better than this project | Worse than this project |
|---|---|---|---|---|
| [VladPolyakov-art/interview-coach](https://github.com/VladPolyakov-art/interview-coach) | OSS, AGPL | 0★, last commit 2026-11-09 | Local Ollama + Whisper + Kokoro, installer picks a model for your RAM, CV + job-description input | HR/behavioural focus, no grading engine where the app computes the score, no community |
| [ngoanpv/DeepInterview](https://github.com/ngoanpv/DeepInterview) | OSS, Apache-2.0 | 74★, last commit 2026-09-18 | Real-time voice loop, company research, multilingual, per-question rubrics | Needs cloud speech and LLM keys for real use; heavy Docker stack |
| [IliaLarchenko/Interviewer](https://github.com/IliaLarchenko/Interviewer) | OSS, Apache-2.0 | 128★, last commit 2024-08 | Coding and system-design interviews, any OpenAI-compatible model | Defaults to OpenAI; inactive |
| [1146345502/aural-oss](https://github.com/1146345502/aural-oss) | OSS, MIT | 229★, last commit 2026-10-14 | Voice, chat and video; richer multi-dimension reports | Cloud LLMs only; aimed at recruiters |
| [jennifer88huang/interview-skills](https://github.com/jennifer88huang/interview-skills) | OSS (prompt pack) | 409★, last commit 2026-07 | Company-style questions, JD-to-resume match, zero install | No grading engine, voice or reports; needs a host LLM |
| [Ashok007-cmd/local-ai-assistant](https://github.com/Ashok007-cmd/local-ai-assistant) | OSS, MIT | 1★, 2026-07 | Resume optimiser plus a document-search (RAG) feature | Uses cloud browser speech; no evidence checks |
| [Final Round AI](https://www.finalroundai.com) | Commercial | Active | Polished, broad feature set | Cloud only; reported $90–150/month; main product is a live "copilot" |
| [Yoodli](https://yoodli.ai) | Commercial | Active | Speech-delivery analytics, free tier | Cloud; coaches delivery more than technical content |
| [interviewing.io](https://interviewing.io) | Commercial | Active | Real engineers as interviewers, the strongest signal for technical roles | Reported $179–339 per session; cloud |
| [Big Interview](https://www.biginterview.com) | Commercial | Active | Large video curriculum, often free through universities | Generic questions; cloud |

**Where this project ranks.** Among open-source tools for *technical-answer grading that runs fully locally*, it is the most rigorously engineered and tested project I found:
- It is the only one with app-computed scores, an evidence-quote check and a 3-OS CI matrix.

It ranks last or near last on adoption, and below commercial tools on polish and question breadth. Its edge in one sentence: private, offline grading in which the application, not the LLM, computes every score and state change, with each step explained to the user.

## 7. Promise check

| Promise | Status | Evidence |
|---|---|---|
| Install in ~40 s with three commands (model excluded) | VERIFIED | 40.8 s, exit 0, empty caches |
| Binds 127.0.0.1 only; DNS-rebinding and cross-site guard | VERIFIED | `lsof`; Host and Origin requests got 403; `main.py:70-90` |
| Local mode makes no outbound calls / works offline | VERIFIED (macOS) | e2e "no requests left localhost"; `python3 scripts/offline_check.py` in my copy: 7/7 PASS in 5 min 48 s, "connections seen from the backend: ['127.0.0.1']". Caveat: it proves success with no network, not zero attempts |
| The app, not the model, computes scores | VERIFIED | `evaluator.py:252-288` (the score comes from `eval_profiles.score_answer`) |
| "Claimed mistakes it cannot quote are … never counted" | PARTLY FALSE | True for classification and the mistake list; the score still uses the model's correctness dimension (`grounding.py:206-263`) |
| One submission ⇒ one LLM call; duplicate submit gets 409 | VERIFIED | Live 409 ×2; `test_concurrency.py` |
| Answer saved before grading; failure is retryable | VERIFIED (code + tests) | `interviews.py:308-317`, `599-603`; `test_state_machine_guards.py` |
| Follow-ups with a real model, limit enforced in code | VERIFIED | offline_check: "4 answers graded by the local model (2 follow-up)"; limit in `interviews.py:637-641` and tests |
| Grading ranks strong > partial > wrong | VERIFIED on 2 hold-out questions | My hold-out: all pairs correct; 1 of 10 out of band |
| Benchmark: 70/70 pairs, 55/56 in band | CLAIMED (results file read, not re-run) | `backend/benchmarks/grading/results/2026-11-19-qwen3.5-4b.md`; uncommitted |
| Report with written summary, PDF/MD/JSON exports | VERIFIED, with a defect | Exports returned 200 (PDF 49 KB, MD 5 KB, JSON 17 KB); the summary hallucinated "full outer join" |
| 94 % backend line coverage | VERIFIED | 94 %, 744 passed, 2 skipped |
| 41 % frontend line coverage | VERIFIED | 41.1 % |
| No known vulnerabilities | VERIFIED | pip-audit ×2 clean, npm audit 0 |
| Windows support | CI-verified (backend and frontend tests, `manage.py check`) | Run 44367320093 on f756a87; not run on a real machine |
| Linux support | CI-verified (same scope) | Same run |
| CI runs start → health → stop on Windows and Linux | FALSE as of today | Only in the uncommitted `ci.yml`; no such run exists |
| Evaluation takes 18–38 s | Not reproduced | My hold-out took 36–84 s per grading (one machine, cold and warm mixed) |
| Phonon voice | VERIFIED (macOS) | offline_check: "question read aloud by the local voice (210 KB of audio)" |
| Whisper microphone | UNKNOWN | Whisper not installed in my copy; 2 tests skipped |
| Groq cloud mode | UNKNOWN | No key; I did not run the fake-server e2e |
| Resume intelligence and adaptive mode with a real model | UNKNOWN | Not run (the docs themselves say mocked only) |
| No telemetry | VERIFIED (code search plus the e2e network assertion) | No outbound host other than the Groq base in the config |

## 8. What I could not verify, and how to settle it

| Item | What would settle it |
|---|---|
| Real Windows and Linux use | A screen recording or log of `start.bat` → full interview → `stop.bat` on Windows 11 and Ubuntu with Ollama installed. Then push the uncommitted `ci.yml` and link the green run. |
| Grading quality beyond the project's own labels | Answers labelled blind by 2–3 people who did not write the prompt, a frozen hold-out set, and inter-rater agreement published next to the model's results. |
| Benchmark reproducibility | Commit `backend/benchmarks/` and its results. Then a second person runs `run.py --repeats 1` on another machine. |
| Groq cloud mode | Run `GROQ_API_KEY=… pytest -m integration backend/tests/integration` and publish the log, including one rate-limit wait. |
| Microphone path | One physical-microphone session with 2–3 accents, with the transcripts published. |
| Adaptive and resume features with a real model | `e2e/full-flow.mjs`-style runs in adaptive and resume modes with the real model, logged in `docs/verification.md`. |
| Offline attempts, not just offline success | `offline_check.py` extended to report sandbox denials, so that zero attempts is proven rather than zero successes. |

## 9. Next five actions, in order

1. Commit and push the current tree, get CI green on all three operating systems, and tag v0.1.0 with release notes.
2. Fix the report-summary digest (include the question text and ground the summary), and add a regression test using the LEFT JOIN case.
3. Correct README.md:47, README.md:126-127 and the `guide.md` platform line so that every claim matches the evidence.
4. Commission independent labels for the benchmark and add a hold-out set. Report the false-error rate on strong answers as its own metric.
5. Have one Windows user and one Linux user run a real interview, triage the Dependabot queue and enable branch protection.

---

## Appendix: commands and raw results

- **Install:** `APP_PORT=3300 DATA_DIR=<scratch> /usr/bin/time -p ./start.sh` gave `real 40.80` and "✓ Ready (all processing is local; bound to 127.0.0.1 only)".
- **Python lint and docs:** `ruff check .` gave "All checks passed!". `python3 scripts/check_docs.py` gave "25 Markdown files checked: OK" (my copy excludes `reviews/`).
- **Backend tests:** `pytest backend --cov=backend/app` gave "744 passed, 2 skipped, 14 deselected, 1 warning in 29.10s" and "TOTAL 6670 416 94%". The skips are the Whisper model and the speech-recognition package, which were not installed. The warning is a Starlette httpx deprecation.
- **Frontend:**
  - `npm run lint` and `npm run typecheck`: clean.
  - `npm run coverage`: "Test Files 20 passed (20), Tests 152 passed (152)", lines 41.1 %.
  - The build ran as part of `start.sh`.
- **Audits:** `pip-audit -r requirements.lock --require-hashes` and the same for `requirements-dev.lock`: "No known vulnerabilities found". `npm audit`: "found 0 vulnerabilities".
- **Chrome e2e:** `E2E_PORT=3310 node e2e/basics.mjs` gave 53 PASS and 0 FAIL. `node e2e/qa-sweep.mjs` gave "ALL CHECKS PASSED". Both ran with the model unloaded.
- **Real-model API journey** (2 questions, follow-ups allowed, `feedback_mode: at_end`):
  - Creating the interview returned 201.
  - Each submit returned 200, and each duplicate submit returned 409.
  - Scores were 7.5 and 8.2, with no follow-ups proposed. The run completed in 113 s.
  - Narrative status was "ready". It contained the "full outer join" error.
- **Hold-out script:** `scratchpad/rvscripts/holdout.py`, which reuses `backend/benchmarks/grading/run.py:grade`. It ran with a single repeat, and the Ollama model was shared with nothing else at the time.
- **Pause-during-last-grading test:** a scratch test built on `test_concurrency.gated_app`. Its output was: "after pause paused evaluating" / "after grading completed done" / "resume 409 not_paused".
- **Offline check:** `python3 scripts/offline_check.py` gave 7/7 checks passed in 5 min 48 s: spoken question, 4 answers graded (2 follow-up), report with a written summary, PDF export (52 KB), and backend connections to 127.0.0.1 only.
- **Load caveat:** while the model was loaded, macOS reported 12 % free memory. The Chrome suites ran only after `./stop.sh --unload`.
