# Things only the maintainer can do

Prepared on branch `review-improvements`. Nothing has been committed, pushed, tagged, merged or changed on GitHub: you make every
commit. The working tree is left uncommitted; the commands below group it into small commits, one concern each.

## 0. Commit the working tree

Eight commits; every changed file is in exactly one of them (checked on 2026-11-20: 104 files, none missing, none twice). Run from
the repository root on branch `review-improvements`. The intermediate commits are not each tested on their own; the final state
is (751 backend and 153 frontend tests, all green).

```bash
git add backend/requirements.lock backend/requirements-dev.lock backend/requirements-dev.txt scripts/manage.py \
  backend/tests/test_launcher.py backend/tests/test_repository.py frontend/package.json frontend/package-lock.json
git commit -m "Dependencies: hash-locked Python installs for launcher and CI, pytest 9.0.3+, typescript-eslint 8.73; launcher reaps its children"

git add backend/app/services/cloud.py backend/app/services/usage.py backend/app/services/gateway.py backend/app/services/ai_config.py \
  backend/app/services/resumes.py backend/app/services/resume_extract.py backend/app/routers/ai.py backend/app/routers/system.py \
  backend/app/main.py backend/app/parsing.py backend/app/schemas.py frontend/src/components/CloudDisclosure.tsx \
  frontend/src/components/AIModels.tsx frontend/src/pages/ResumeDetail.tsx frontend/src/resumeHelpers.ts \
  backend/tests/test_ai_config.py backend/tests/test_local_only.py backend/tests/test_resumes.py backend/tests/test_static_serving.py \
  backend/tests/test_audit_regressions.py frontend/src/__tests__/cloudDisclosure.test.tsx frontend/src/__tests__/resumeHelpers.test.ts SECURITY.md
git commit -m "Security and cloud mode: per-resume consent at the gateway, same-app Origin check, input limits, PDF bomb check, truncated streams, spend ledger, HEAD on UI routes"

git add backend/app/services/ollama.py backend/app/services/evaluator.py backend/app/services/eval_profiles.py \
  backend/app/services/grounding.py backend/app/services/prompts.py backend/app/services/adaptive.py backend/app/services/interviews.py \
  backend/app/services/reports.py backend/app/services/report_pdf.py .env.example backend/pytest.ini backend/tests/conftest.py \
  backend/tests/test_llm_timeouts.py backend/tests/test_eval_profiles.py backend/tests/test_grounding.py backend/tests/test_intelligence_flow.py \
  backend/tests/test_interview_flow.py backend/tests/test_state_machine_guards.py backend/tests/test_concurrency.py backend/tests/test_reports.py \
  backend/tests/test_report_pdf.py backend/tests/test_usage.py backend/tests/integration/test_real_models.py backend/tests/integration/test_real_groq_grading.py
git commit -m "Grading and interviews: eval-2.1, first-token timeout, term-list cap, unchecked suggested answers, summary sees the questions, no stuck or paused-open interviews, logging"

git add backend/benchmarks backend/tests/test_benchmark_summary.py scripts/offline_check.py
git commit -m "Grading benchmark, term-list and summary checks with the real model; offline check in a no-network sandbox"

git add frontend/src/components/Feedback.tsx frontend/src/components/ReportIntel.tsx frontend/src/pages/Interview.tsx frontend/src/pages/Report.tsx \
  frontend/src/types.ts frontend/vite.config.ts frontend/src/__tests__/feedback.test.tsx frontend/src/__tests__/setup.ts \
  frontend/src/__tests__/interviewPage.test.tsx frontend/src/__tests__/reportPage.test.tsx frontend/src/__tests__/setupPage.test.tsx \
  frontend/src/__tests__/fixtures backend/tests/test_report_fixture.py
git commit -m "Frontend: Setup, Interview and Report page tests on backend-made fixtures; coverage; stale-tab message kept"

git add frontend/e2e/lib.mjs frontend/e2e/harness-selftest.mjs .github/workflows/ci.yml .github/workflows/release.yml .github/workflows/security.yml
git commit -m "CI and e2e: launcher start/stop on three systems, Chrome page checks on Linux, dev-lock audit; harness refuses a busy port"

git add CHANGELOG.md CONTRIBUTING.md README.md ROADMAP.md guide.md docs
git commit -m "Docs: measured evidence, verification log, honest CI and platform wording"

git add REVIEW_PROMPT.md reviews
git commit -m "Reviews: prompt, rounds 0-4, score log, owner checklist"

git status          # should say: nothing to commit, working tree clean
```

## 1. Push the branch and open a pull request

```bash
git push -u origin review-improvements
gh pr create --base main --head review-improvements --title "Review-driven fixes" --fill
```

Then confirm CI is green on all three operating systems. The run's URL is the evidence the platform table in the README points to.

## 2. Evidence from real Windows and Linux machines

The README says Windows and Linux "have not been run on a real machine". A green GitHub Actions run is CI evidence, not real-machine
evidence: GitHub's hosted runners are virtual machines, not your friends' laptops.

If friends have run the app on real hardware, collect for each machine:
- the OS and version, CPU, RAM;
- the output of `check.bat` / `./check.sh`;
- `start` → one short interview → `stop`, with the log files `logs/backend.log` and the printed output;
- which voice path was used (system voices) and whether it spoke.

Commit those logs under `docs/platform-reports/` and then update README §2 and §11 to say what was verified, on what, and when.
Until then the README statements stay as they are.

## 3. Protect `main`

GitHub → Settings → Branches → Add rule for `main`: require a pull request, require the CI and Security checks to pass, block force pushes.
Or with the CLI:

```bash
gh api -X PUT repos/Yuvakunaal/local-ai-interviewer/branches/main/protection \
  -f required_status_checks.strict=true \
  -F 'required_status_checks.contexts[]=Lint, docs and repository checks' \
  -F enforce_admins=false -F required_pull_request_reviews=null -F restrictions=null \
  -F allow_force_pushes=false -F allow_deletions=false
```

## 4. Triage the Dependabot pull requests

Ten are open since 2026-11-15. Merge or close each after CI. Major-version bumps (TypeScript 7, ESLint 10, jsdom 31, jest-dom 7,
reportlab 5) need a look at their release notes first.

## 5. Tag the first release

After the PR is merged and CI is green on `main`, follow `docs/maintainers/releasing.md`.

## 6. Things that need hardware or an account

- **Groq:** `GROQ_API_KEY=… backend/.venv/bin/python -m pytest -m integration -s backend/tests/integration` and commit the output.
- **Microphone:** `./setup-models.sh --stt`, then a real interview with a physical microphone; note the accent and Whisper size.
