# Independent review: Local AI Interviewer

Reviewed 2026-11-19, commit `f756a87` plus the uncommitted working tree (51 modified and 3 new files, +934/−176 lines).
Hardware: MacBook Air M2, 8 GB RAM, macOS 26.5, Ollama 0.40.16, `qwen3.5:4b`, Python 3.13.5, Node 24.2.

To keep the repository read-only, everything ran in a copy of the working tree in a scratch directory, with its own data directory and port (3200). The only file created in the repository is this report.

Labels used throughout:
- **VERIFIED**: I ran it or read the code.
- **CLAIMED**: the docs say so and I could not confirm it.
- **UNKNOWN**: not checked.

---

## 1. Verdict

- **What it is:** a local-first mock-interview coach for tech roles. A local LLM (Ollama) grades typed or spoken answers. The app, not the model, computes the score from validated dimension scores and quotes it has checked against the answer.
- **Overall score: 6 / 10.**
- **Biggest strength:** the grading pipeline works on real hardware. In my 12-answer calibration with the real `qwen3.5:4b`, strong, weak and wrong answers separated cleanly on every question, and all 25 cited quotes were verified against the answers.
- **Biggest risk:** a single maintainer with a 10-day-old repository, no release and no outside users. The project's own docs also say grading quality was never measured. My calibration is the first evidence of it, and it is small.
- **Recommend today?** Yes, as a private study aid for technically comfortable people on Apple Silicon Macs. No for Windows or Linux users who need it to just work, or for anyone who would use the scores to make decisions about other people.

---

## 2. Scorecard

| Area | Score | Reason |
|---|---|---|
| Idea and differentiation | 6 | The space is crowded. The combination of evidence-checked grading, resume questions, adaptive follow-ups and full offline operation is distinctive, but "offline" alone is not unique (§6). |
| Does it work | 7 | Install and the full journey worked first time. Under memory pressure, 4 of 6 real-model tests failed on the 90 s idle timeout (§3, M2). |
| Code quality | 8 | Coherent layers that match the docs. Pure-function engines. Compare-and-set state machine verified. Largest file is 810 lines. |
| Testing | 7 | 709 backend + 140 frontend tests pass, 94 % line coverage, and the tests check behaviour. But only 6 real-model tests exist, they score with the v1 path, and the e2e harness can silently test the wrong server. |
| Security | 8 | Loopback bind, Host/Origin guard, file modes and audits verified. SHA-pinned least-privilege CI. No branch protection, Python deps not hash-locked, API key stored in plain text (documented). |
| Documentation | 8 | Unusually candid and accurate where I checked. Long (README is 62 KB), and one small gap in the dev-tool install step. |
| Ease of adoption | 6 | Needs Python, Node, Ollama and a 4 GB model. On 8 GB machines, other apps must be closed. Windows and Linux have never been run on real machines. |
| Project health | 3 | 13 commits, one author, 2 stars, 0 forks. No tags or releases, 10 untouched Dependabot PRs, unprotected `main`, and a large uncommitted working tree. |
| Proof of core claim | 5 | Positive but thin: my 12-answer run plus 1 passing real-model grading test. Single run, only obvious errors, no subtle-error or injection data that completed. |

**Overall: 6 / 10.** Weights:

| Area | Weight |
|---|---|
| Does it work | 20 % |
| Proof of core claim | 20 % |
| Code | 10 % |
| Testing | 10 % |
| Security | 10 % |
| Documentation | 10 % |
| Adoption | 10 % |
| Idea | 5 % |
| Health | 5 % |

The weighted mean is 6.55. I capped it at 6 for two reasons:
- The core claim is only partly proven: the sample is small and has not been repeated.
- Project health is weak enough that nobody should depend on this project yet.

---

## 3. Phase notes (evidence)

### Phase 0: orient
- **Size (VERIFIED, `wc -l`):**

  | Area | Lines |
  |---|---|
  | `backend/app` | 9,970 |
  | `backend/tests` | 7,535 |
  | `frontend/src` | 8,821 |
  | `scripts` | 930 |
  | `docs` | 1,091 |

- **Runtime dependencies:** 7 Python (`backend/requirements.txt`) and 3 npm (`frontend/package.json`). That is lean.
- **In three sentences:** a self-hosted web app (FastAPI + React) that runs mock technical interviews on the user's own computer. It is for job-seekers in software, data, ML and similar roles who want private practice without accounts or fees. It promises offline-by-default operation, evidence-checked and app-computed scoring, adaptive follow-ups, resume-based questions and detailed reports. All of that is meant to fit on an 8 GB laptop.

### Phase 2: does it work

**Install (VERIFIED).**
- `./check.sh` ran in 1.1 s and exited 0 with a clear report.
- `./start.sh` installed dependencies, built the UI and started in 10.7 s. Package caches were already warm, so this is **not** representative of a cold machine. Cold install time is UNKNOWN.
- No step was broken. One friction point: when `uv` is present, the launcher makes a venv without `pip`. README §12 says "install `backend/requirements-dev.txt` first" but does not mention this. `docs/development.md:73` does give the `uv pip install` command.

**Checks (VERIFIED, in the copy):**

| Check | Result |
|---|---|
| `ruff check .` | All checks passed |
| `scripts/check_docs.py` | 22 Markdown files OK |
| `pytest backend --cov` | **709 passed, 2 skipped**, 14 deselected (integration), 28 s, **94 %** line coverage (6,609 statements, 410 missed; lowest: `stt.py` 45 %, `sysmem.py` 78 %, `ollama.py`/`tts.py` 81 %) |
| `npm run lint` / `npm run typecheck` | Pass |
| `vitest run` | **140 passed** |
| Frontend coverage | Not measurable: `@vitest/coverage-v8` is not a dependency |
| `npm run build` | Passed, as part of `start.sh` |
| CI on GitHub | Last CI and Security runs on `main` succeeded (`gh run list`). Two Dependabot PR runs failed. |

**Main journey with the real model (VERIFIED, scripted over the HTTP API that the UI uses).**
- I created a question set and a 3-question interview with 1 follow-up allowed.
- The answers were partial, good, and "I don't know".
- Every submit returned 200. **Every immediate duplicate submit returned 409**, which confirms the compare-and-set guard.
- The app asked one sensible follow-up: "How would you handle late data in an incremental pipeline using watermarks…"
- The report and its written summary were generated (`narrative_status: ready`).
- PDF (3 pages, valid), Markdown and JSON exports all returned 200.
- The **redacted** versions of all three contained none of the answer text; the non-redacted Markdown did.
- The model was unloaded after the interview (`/api/usage` showed `loaded: []`).
- I did **not** drive the React UI in a browser myself. That is explained in the e2e paragraph below.

**Speed (VERIFIED, `/api/usage`):**
- 16 evaluations averaged **60.8 s** (50.0–73.9 s) at **13.1 tokens/s**, with about 1,800 prompt tokens per evaluation.
- The README says 18–38 s at about 20 tokens/s. My machine had 7.0 of 8 GB swap in use (`sysctl vm.swapusage`), so the README figure may hold on an idle machine. That is CLAIMED.

**Real-model integration suite (VERIFIED).**
- Command: `RUN_INTEGRATION=1 pytest -m integration backend/tests/integration/test_real_models.py`.
- Result: **2 passed, 4 failed** in 9 min 43 s.
- All 4 failures were `LLMError: The local model stopped responding (idle timeout)`. In Ollama's server log, those requests ended at exactly 1 m 30 s with HTTP 500, while the successful ones took 26–56 s.
- The passing grading test scored a clear spoken answer **8.2**, a wrong one **1.6** and "I don't know" **0.9**.
- Cause: severe memory pressure in my environment (two editor sessions, a browser and the user's own instance of the app were running). That is partly environmental, but it is exactly the 8 GB setup the project targets (see M2).

**The core claim** is that a small local model, constrained by evidence checks and app-side scoring, gives grades that track answer quality. Before this review, the only real-model evidence was the 6-test integration file and one hand-run cloud interview (README §11, ROADMAP "Measure grading quality… verified with a mocked model only").

I ran my own calibration: 4 questions with no rubric (concurrency, SQL, ML, networking), each answered three ways, all graded by the real local model through the full app pipeline.

| Answer quality | Race condition | LEFT JOIN | Overfitting | TCP/UDP | Mean | App's verdict |
|---|---|---|---|---|---|---|
| Strong, complete | 7.8 | 8.1 | 7.5 | 8.3 | **7.9** | Good |
| Weak, vague but correct | 5.3 | 6.1 | 3.3 | 4.1 | **4.7** | Weak |
| Confidently wrong | 1.6 | 1.5 | 1.1 | 1.7 | **1.5** | Incorrect |

What the calibration shows:
- Within each question, strong > weak > wrong in **12 of 12 cases**, with no overlap between bands.
- All wrong answers were classified `incorrect`, with misconceptions that quote the actual wrong sentence.
- All strong answers were classified `correct`.
- 25 of 25 evidence quotes were verified as present in the answer (34 of 34 including the journey interview). No misconception was left unverified.

What it does **not** show:
- whether results repeat (one run only);
- how the grader handles subtly wrong answers (my wrong answers were blatant);
- behaviour on rubric-less niche topics;
- resistance to prompt injection (that test timed out);
- calibration against a human grader.

Strong answers top out around 8.3, which matches the documented "conservative" behaviour.

**e2e (UNKNOWN; harness defect found).**
- I ran `node e2e/basics.mjs` in my copy and it reported all PASS.
- A second editor session was already running the same script from the real repo. Both use the hard-coded port 3100 (`frontend/e2e/lib.mjs:10`).
- `startBackend()` (`lib.mjs:33-44`) declares success as soon as *anything* on :3100 answers `/api/health`. It never checks that its own child process bound the port.
- So my run almost certainly tested the other session's server. Its result does not count. I did not rerun it, to avoid disturbing that session.

### Phase 3: code and architecture

**Architecture matches `docs/architecture.md` (VERIFIED).** Routers are thin, services are built in `deps.py`, and one `gateway.py` decides between local and cloud. `adaptive.py` and `grounding.py` are pure functions with 100 % and 99 % coverage. The 8-step evaluation pipeline in the doc matches `interviews._evaluate` / `_apply` and `evaluator.finalize`.

**Workflow traced: submit → evaluate → apply → advance** (`backend/app/services/interviews.py:303-654`):
- The answer is written in a `BEGIN IMMEDIATE` transaction before any model call (`:308-316`).
- Evaluation runs on a single-worker executor (`:49`) behind a global LLM lock (`ollama.py:120`).
- `_apply` re-checks phase, turn and status before writing (`:608`), so stale results are dropped.
- Every exception path except `AppError` calls `_fail` (`:581-594`). I checked the `AppError` branch: only `not_found` for a deleted interview can reach it, and deletion is refused while evaluating (`:402`). So it is not a live bug, though the comment at `:586` overstates the guarantee.
- The follow-up limit is enforced in code, with an `assert` as a final check (`:635`).
- No data-loss path found. Restart recovery is CLAIMED (tested in the suite, not by me).

**Bugs and risks found:**

1. **The idle timeout includes time to first token** (`ollama.py:145-170`). Prompt processing (about 1,800 tokens) under swap can exceed `LLM_IDLE_TIMEOUT_S=90`. The user is then told the model "stopped responding" when it never started, and the answer goes to Retry. I observed this 4 times.
2. **The e2e harness can test a foreign server** (`frontend/e2e/lib.mjs:33-44`). Besides wrong results, an e2e run on a machine where something else already listens on :3100 would write test data into that instance. That breaks the "your data is never touched" promise (`lib.mjs:2`) in that edge case.
3. **The real-model tests use the legacy scorer.** `test_real_models.py` scores with `evaluator.compute_score` (the v1 weighted mean). The app scores through `eval_profiles.score_answer` (`interviews.py:662`, architecture step 6). So even a passing integration run does not check the 2.0 scoring path. My calibration above used the real app path.

**Tests: quality, not just quantity (VERIFIED by reading).**
- The backend tests fake only the model (`tests/conftest.py:47` `FakeOllama` via `httpx.MockTransport`).
- They check real behaviour: scoring maths (`test_grading_fairness.py`), state-machine guards, redaction, migrations and launcher OS decisions.
- That is the right boundary. The consequence is that nothing in the default suite says anything about grading *quality*.

**Maintainability.**
- Largest files: `interviews.py` (810 lines), `manage.py` (796), `reports.py` (683). Reasonable sizes.
- Long single lines are common (180–200 characters) but not a defect.
- **First hour for a new contributor: plausible.** `CONTRIBUTING.md` and `docs/development.md` exist, and the whole backend suite runs in 30 s with no model.
- **Dependency freshness:**

  | Package | Installed | Latest |
  |---|---|---|
  | ruff | 0.8.6 | 0.17.5 |
  | reportlab | 4.5.1 | 5.1.0 |
  | typescript | 5.9.3 | 7.0.2 |
  | eslint | 9.39.5 | 10.15.0 |

  Each has a Dependabot PR open and untouched since 2026-11-15.

### Phase 4: security and supply chain (VERIFIED unless marked)

**Network exposure.**
- `lsof` shows the app listening only on `127.0.0.1`.
- A request with `Host: evil.example` gets **403**; a cross-origin POST gets **403**.
- `/api/docs` returns 404 by default.
- The built `index.html` references no external URLs.

**Files.**
- The SQLite database is mode `0600` (copy and the user's real `data/`), and resume uploads are written `0600` under a `0700` folder with UUID names (`services/resumes.py:250-255`).
- Minor: `data/audio_cache` is `0755`.

**Secrets.** The Groq key is stored in plain text in SQLite unless `GROQ_API_KEY` is used. This is disclosed in README §7a and SECURITY.md.

**Audits.**

| Tool | Result |
|---|---|
| `pip-audit -r backend/requirements.txt` | No known vulnerabilities |
| `npm audit --omit=dev` | 0 |
| `npm audit` (with dev deps) | 7 moderate, all from `minimatch` (ReDoS) via `typescript-eslint`, dev-only |

CI fails only on high-severity dev findings, as SECURITY.md says.

**OpenSSF Scorecard-style checks:**

| Check | Status | Evidence |
|---|---|---|
| Pinned dependencies | Partial | Actions pinned to SHAs (`.github/workflows/*.yml`); npm lockfile present; Python uses version ranges with no lock or hashes (`backend/requirements.txt`) |
| Token permissions | Good | `permissions: contents: read` at top level; `security-events: write` only for CodeQL |
| Dependency update tool | Present, not acted on | `.github/dependabot.yml`; 10 open PRs |
| Security policy | Present | `SECURITY.md` |
| Branch protection | **None** | `gh api …/branches/main/protection` → "Branch not protected" |
| Binary artifacts | None tracked | `git ls-files` contains no binaries beyond screenshots and the logo |
| SAST | Present | CodeQL `security-extended` for Python and JS/TS |

**What leaves the machine.** In local mode, nothing as far as I could see: the only outbound code paths I found are the loopback Ollama client and the opt-in Groq client (`services/ollama.py`, `services/cloud.py`). The README says `test_local_only.py` asserts loopback-only; I did not read that file myself. In cloud mode, the question, rubric, answer and thread go to `api.groq.com` after consent. I did not test cloud mode (no key), so that part is CLAIMED.

### Phase 5: project health (VERIFIED via `git` and `gh`)

**History.** 13 commits from 2026-11-09 to 2026-11-18, all by one author.
- Initial commit: 26,404 lines.
- 10 commits on 2026-11-15.
- Typical commit: 300–2,500 lines.

This is bulk drops, not incremental history. The current working tree has a further 934 uncommitted lines across 51 files, including the grading prompt (`prompts.py`).

**Adoption and activity.**
- 2 stars, 0 forks, 0 watchers.
- No issues from outside users; the only PRs are 10 open Dependabot PRs.
- No tags, no releases; the changelog says 1.0.0 and 2.0.0 are "untagged".

**Bus factor: 1.** Would it survive six months without the maintainer? The code would still run, because the dependencies are few and mainstream. But the Ollama model tag, the Groq model ids and prices, and the dependency ranges would drift, and nobody else has merged anything.

**Governance.** MIT licence (clear). Code of conduct, contributing guide, support doc, ADRs, issue templates and release procedure all exist. That is more governance than a two-star project needs, but it costs nothing and helps anyone who arrives later.

### Phase 6: user and contributor experience

**Onboarding.** The launcher's messages are clear: it refuses non-loopback hosts, reports busy ports and asks before downloading. A first-run setup page and a plain HTML page for a missing Python or Node are CLAIMED; I did not exercise them in a browser.

**Errors.** The API returns `{error:{code,message}}` with human-readable messages (for example the 409 "That question is no longer current"). One exception: the timeout message is misleading (bug 1 above).

**Accessibility.**
- CLAIMED: WCAG contrast, unnamed-control and overflow sweeps (`e2e/ui-audit.mjs`, `e2e/qa-sweep.mjs`). Not run by me.
- The roadmap admits no screen-reader testing.

**Platforms.** macOS on Apple Silicon is verified (by me, for backend, API and real model). Windows and Linux are CI-only for tests and `manage.py check`, and the docs say so plainly.

---

## 4. Advantages (verified only)

- **The app computes the score, and quotes are checked.** The model's own total is ignored. Each evidence quote is string-matched against the answer, and unquotable misconceptions are kept but not counted (`services/grounding.py`, `evaluator.finalize`). In my run every quote checked out, and wrong answers were flagged with their own words.
- **Grading tracks answer quality on real hardware.** 12/12 correct ordering in my calibration (§3).
- **Robust interview state.** Duplicate submits got 409 on every one of 16 tries. Answers are persisted before evaluation. Stale results are dropped.
- **Privacy defaults hold.** Loopback bind, Host and Origin guards, `0600` data files, no CDN, and the model is unloaded after use.
- **Fast, meaningful test suite.** 849 tests in about 35 s, 94 % backend coverage, checking real behaviour.
- **Lean, secure supply chain for its size.** 10 runtime dependencies, no known runtime vulnerabilities, SHA-pinned least-privilege CI with CodeQL.
- **Honest docs.** README §11 lists untested platforms, mock-only verification and the experiments that were never physically done. Everything I checked against them was accurate.

---

## 5. Improvements

### MUST FIX (blocks trust or adoption)

| # | What | Why | Where | Effort |
|---|---|---|---|---|
| M1 | Publish a grading benchmark: a labelled answer set (≥50 answers, including subtle errors, injection attempts and no-rubric niche topics), run ≥3 times, with the script and results committed. | It is the core claim, and the roadmap says it was never measured. | new `backend/tests/integration/benchmark_*` + `docs/evaluation.md` | M |
| M2 | Separate a first-token timeout (scaled to prompt size, or about 240 s) from the inter-token idle timeout. Say "the model is still reading your answer" rather than "stopped responding". | 4 of 6 real-model tests failed this way on the 8 GB target hardware. | `backend/app/services/ollama.py:145-170`, `config.py` | S |
| M3 | Commit the working tree, tag a first release (2.0.0), and enable branch protection on `main`. | Users cannot pin a version. The grading prompt that is running is not in git history. | repo, `docs/maintainers/releasing.md` | S |
| M4 | Make the e2e harness fail if the port is already in use, and allow the port to be set with an env variable. | It silently tests and writes to a foreign server, and it broke this review's e2e run. | `frontend/e2e/lib.mjs:10,33-44` | S |

### SHOULD DO (clear value, not blocking)

| # | What | Why | Where | Effort |
|---|---|---|---|---|
| S1 | Score real-model tests through `eval_profiles.score_answer`, as the app does. | Integration tests currently check the v1 scorer. | `backend/tests/integration/test_real_models.py` | S |
| S2 | Triage the 10 Dependabot PRs. Fix the dev-only `minimatch` advisory by bumping `typescript-eslint`. | Stale update PRs signal an unmaintained repo. | `frontend/package.json`, `backend/requirements*.txt` | S |
| S3 | Hash-locked Python dependencies (`uv pip compile --generate-hashes` or `pip-tools`). | Ranges mean every install can resolve differently. | `backend/` | M |
| S4 | Get one real run on Windows 11 and Ubuntu (start, interview, stop), or a CI job that runs `start`/`stop` plus `basics.mjs` on all three systems. | Two of three advertised platforms have never been run on real machines. | `.github/workflows/ci.yml` | M |
| S5 | Add `@vitest/coverage-v8` and report frontend coverage. | Frontend coverage is currently unmeasurable. | `frontend/package.json` | S |
| S6 | Mention the `uv` / no-pip case in README §12. | It's the first command a contributor hits. | `README.md` §12 | S |

### NICE TO HAVE

| # | What | Why | Where | Effort |
|---|---|---|---|---|
| N1 | Split the 62 KB README into a short landing page plus docs pages. Most content already exists in `docs/`. | Easier to scan. | `README.md` | S |
| N2 | Create `data/audio_cache` with `0700`. | Consistency with the other data files. | `services/tts.py` | S |
| N3 | Ground questions in a job description; add a live coding round. | Gaps competitors already fill (§6). | new feature | L |

---

## 6. Who it is for, and who should not use it yet

**Best for:** individual developers and data or ML engineers preparing for interviews who are comfortable with a terminal (git, Python, Node, Ollama). Best on an Apple Silicon Mac with 16 GB, or 8 GB with other apps closed. Use it as a private study aid, ideally with your own rubrics for questions that matter.

**Not yet for:**
- non-technical users, or anyone on Windows or Linux who needs it to work without debugging;
- 8 GB machines that must keep a browser, editor and chat apps open, where evaluations take about 60 s and can time out;
- schools, bootcamps or recruiters who would rely on the scores (single-user, no login, unmeasured accuracy);
- anyone who needs coding rounds or real-time voice conversation.

---

## 7. Competitors

These come from web research done during this review (GitHub stars and dates via the GitHub API on 2026-11-19; commercial prices from third-party sources). I did not re-check them individually, so treat prices as CLAIMED.

**Open source**

| Project | Activity | Better than this project | Worse |
|---|---|---|---|
| [GrillKit](https://github.com/Forkfield/grillkit) | 13★, push 2026-08-16 | Closest match: Ollama, offline Whisper, Piper TTS, follow-ups, plus **live coding rounds** and Docker | No resume questions or evidence checking; licence unclear |
| [Lemonade Interviewer](https://github.com/lemonade-sdk/interviewer) (AMD) | 15★, push 2026-10-08 | Fully local, backed by an organisation | Calls itself a proof of concept; shallow grading; tied to Lemonade Server |
| [DeepInterview](https://github.com/ngoanpv/DeepInterview) | 72★, push 2026-11-16 | Real-time voice (LiveKit), multilingual, company research | Early build; real voice needs cloud keys |
| [IliaLarchenko/Interviewer](https://github.com/IliaLarchenko/Interviewer) | 127★, push 2025-03-16 | Coding, system design and ML rounds; any OpenAI-compatible model | Inactive about 20 months; no resume or evidence checking |
| [GPTInterviewer](https://github.com/jiatastic/GPTInterviewer) | 265★, push 2024-04-04 | Job description + resume questions | Abandoned; OpenAI-only |
| [ai_mock_interviews](https://github.com/adrianhajdin/ai_mock_interviews) | 574★, push 2025-03-29 | Polished real-time voice UX | Tutorial project; Vapi + Gemini cloud, needs accounts |
| [GrillMe](https://github.com/Vandool/grillme) | 4★, push 2026-04-06 | Grounds questions in CV **and job description** | "Local" TTS is edge-tts (cloud); inactive |

**Commercial**

| Product | Pricing (CLAIMED) | Better | Worse |
|---|---|---|---|
| [Final Round AI](https://finalroundai.com) | Free mock tier; about $50–150/mo | Large library, polish | Cloud and account; mixed reviews |
| [interviewing.io](https://interviewing.io) | About $179 per human session | Real engineers as interviewers | Expensive |
| [Exponent / Aced](https://tryexponent.com) (+ Pramp) | About $79–99/mo; free peer mocks | Curated content, peer practice | Paywalled, cloud |
| [Yoodli](https://yoodli.ai) | About $8–20/mo | Delivery analytics | Focus on speaking style, not technical correctness |
| [Big Interview](https://biginterview.com) | $39–299 | Curriculum, university adoption | Cloud, dated |
| Google Interview Warmup | Reportedly discontinued around 2026-04 | Was free, no account | Gone |

**Ranking.** In open source, this project is the most complete and best-engineered of the local-first options I saw: it has the strongest tests, CI, docs and grading design. But it has the least adoption of the serious ones, and it lacks coding rounds and job-description grounding. It does not compete with human-interviewer services or with the polish of commercial products.

Its actual edge, in one sentence: **auditable, app-computed grading with quotes checked against the answer, running fully offline.** Offline alone is not an edge any more.

---

## 8. Promise check

| Promise (source) | Status | Evidence |
|---|---|---|
| Binds to 127.0.0.1 only (README) | VERIFIED | `lsof`: `127.0.0.1:3200 (LISTEN)` |
| Host/Origin guard, DNS-rebinding safe (README §10) | VERIFIED | `Host: evil.example` → 403; cross-origin POST → 403 |
| No CDN, no telemetry in local mode (README §3) | VERIFIED (code + built HTML) | `index.html` has no external URLs; `/api/docs` off by default (404) |
| Data in local SQLite, mode 600 (README, SECURITY) | VERIFIED | `stat` → `-rw-------` |
| Answer saved before evaluation, never lost on failure (README §1) | VERIFIED (code) | `interviews.py:308-317` (answer committed before the executor is called); `_fail` keeps it on error (`:596-600`) |
| Double click or replay → 409, one LLM call (README §1) | VERIFIED | 16/16 duplicate submits → 409 |
| Follow-up limit enforced in code (README §1) | VERIFIED (code) | `interviews.py:633-635`, `decide_followup` |
| App computes the score, not the model (README §6, ADR 0001) | VERIFIED (code) | `evaluator.finalize`, `eval_profiles.score_answer` |
| Unverifiable misconceptions not counted (README Features) | VERIFIED (code) / partly in run | `grounding.split_misconceptions`; my run had 0 unverified, so the discount path was not exercised live |
| Grades track quality with real `qwen3.5:4b` (README §11) | VERIFIED, small sample | Calibration 12/12 ordered; integration MySQL test passed (8.2 / 1.6 / 0.9) |
| Prompt-injection resistance (README §11 "≈0") | UNKNOWN | My run of that test timed out; unit tests cover fencing only |
| One evaluation in 18–38 s on M2 8 GB (README §7) | NOT REPRODUCED | 50–74 s under heavy swap; may hold on an idle machine |
| Model unloaded when idle (README §7) | VERIFIED | `/api/usage` → `loaded: []` after the interview finished |
| `start` refuses a second copy, `stop` leaves a foreign Ollama alone (README §4) | Partly VERIFIED | `stop.sh` printed "Ollama left running (it was not started by this app)"; second-copy refusal not tested |
| PDF/MD/JSON and redacted exports (README Features) | VERIFIED | All 200; redacted copies contain no answer text; PDF 3 pages |
| Backend coverage 94 % (README §12) | VERIFIED | 94 % |
| CI on macOS/Windows/Linux (README §12) | VERIFIED | `ci.yml` matrix; latest `main` run succeeded |
| Works on Windows and Linux (README §2) | CLAIMED (honestly labelled untested) | Docs say not run on real machines |
| Offline voice (Phonon / system), Whisper mic (README §8) | Phonon VERIFIED; Whisper UNKNOWN | Integration `test_phonon_speaks…` passed; `faster-whisper` not installed |
| Groq cloud mode, budget, rate-limit wait (README §7a) | CLAIMED | No key available; docs admit one real run |
| WCAG contrast / a11y sweeps (README §12) | CLAIMED | e2e not run (port conflict) |
| Fully works with Wi-Fi off (README §10) | CLAIMED | Docs admit not physically done; I did not do it either |

---

## 9. What I could not verify, and how to settle it

| Item | Why not | What the maintainer could run or publish |
|---|---|---|
| Repeatability and subtle-error grading | Single run, blatant errors only | M1: commit `benchmark.py` + a labelled set; publish a table of 3 runs with the spread per answer |
| Prompt-injection resistance with the real model | Test timed out | Run `test_prompt_injection…` on an idle machine; add 10 varied injections to the benchmark |
| e2e suites (basics, full-flow, ui-audit, qa-sweep) | Port 3100 in use by another session; harness flaw | Fix M4, then publish the CI or e2e logs |
| Windows / Linux real use | No hardware | Screen recording or log of `start` → interview → `stop` on Windows 11 and Ubuntu 24.04 |
| Cold install time | Warm caches here | Time `./start.sh` on a fresh VM with clean pip/npm caches |
| Groq cloud mode | No API key | `GROQ_API_KEY=… pytest -m integration backend/tests/integration`, then publish the output |
| Microphone / Whisper accuracy | Optional package not installed | `./setup-models.sh --stt` + `node e2e/mic.mjs`; test with a physical microphone and several accents |
| The advertised 18–38 s speed | Machine was swapping | Publish `/api/usage` from a run on an idle 8 GB M2 |
| Accessibility | Not run; no screen reader | Publish `ui-audit` output; one VoiceOver pass |
| Responsiveness to outside contributors | None exist yet | UNKNOWN until there are outside contributors |

---

## 10. Next five actions, in order

1. **M1, grading benchmark.** Committed script plus labelled set, 3 runs, results in `docs/evaluation.md`. Also do S1. This moves "Proof of core claim" most.
2. **M2, first-token timeout.** Removes the most likely real-world failure on the target hardware.
3. **M3, commit, tag 2.0.0, protect `main`, triage Dependabot.** Turns a working tree into something people can pin and trust.
4. **M4, e2e port check.** Then run the e2e suites and attach their logs to the release.
5. **S4, one real Windows and Linux run.** Report it, or switch those rows of the platform table to "verified".
