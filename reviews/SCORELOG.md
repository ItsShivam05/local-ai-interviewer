# Score log

Each round is an independent review run with [REVIEW_PROMPT.md](../REVIEW_PROMPT.md). Reports are kept unedited in this folder.
A score counts as moved only when the report gives evidence for it.

| Round | Overall | Idea | Works | Code | Testing | Security | Docs | Adoption | Health | Core claim | Report |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 6 | 6 | 7 | 8 | 7 | 8 | 8 | 6 | 3 | 5 | [round-0.md](round-0.md) |
| 1 | 6.5 | 6 | 8 | 7 | 7.5 | 8 | 7 | 6 | 3 | 6 | [round-1.md](round-1.md) |
| 2 | 6.5 | 6 | 8 | 8 | 8 | 8 | 7 | 6 | 3 | 6 | [round-2.md](round-2.md) |
| 3 | 6.5 | 6 | 8 | 7 | 8 | 7 | 7 | 6 | 2 | 5 | [round-3.md](round-3.md) |
| 4 | 6.5 | 6 | 8 | 8 | 8 | 7 | 8 | 5 | 3 | 6 | [round-4.md](round-4.md) |

## Round 0 (baseline, 2026-11-19)

Reviewed commit `f756a87` plus the then-uncommitted working tree.

Findings that lowered the score:
- **Proof of core claim (5).** No grading benchmark. The real-model integration tests score with the v1 `compute_score`, not the
  app's `eval_profiles.score_answer`.
- **Does it work (7).** 4 of 6 real-model tests hit the 90 s idle timeout under memory pressure: time to first token counts as idle.
- **Testing (7).** The e2e harness silently reuses whatever already listens on :3100. Frontend coverage cannot be measured.
- **Security (8).** No branch protection. Python dependencies are not hash-locked. 7 moderate dev-only npm advisories.
- **Docs (8).** README §12 omits the `uv` / no-pip step.
- **Adoption (6).** Windows and Linux only covered by CI.
- **Health (3).** No release or tag, 10 untriaged Dependabot PRs, large uncommitted tree, one author, 2 stars.

## Round 1 (2026-11-20)

Reviewed the uncommitted working tree after the round-1 fixes. Overall 6 → 6.5.

Moved, with evidence in the report:
- **Does it work 7 → 8.** Reviewer installed in 18 s, ran a real-model interview, saw no timeouts, and saw 1 of 3 parallel duplicate submits succeed.
- **Testing 7 → 7.5.** Reviewer got 722 backend tests at 94 %, 152 frontend tests at 41 %, the benchmark, and `basics` and `qa-sweep` in Chrome.
- **Proof of core claim 5 → 6.** Reviewer regenerated the benchmark summary from the raw data (70/70 pairs, 55/56 in band). Their own 12-answer held-out check ranked sensibly.

Fell:
- **Code 8 → 7.** Long services, plus the latent `except AppError: return` in the grading worker.
- **Docs 8 → 7.** README is 64 KB. Wi-Fi-off claim in §10 contradicts §11. README overstates CI launcher coverage.

Did not move:
- Idea 6, Security 8, Adoption 6, Health 3.

New findings:
- CI only runs the launcher's read-only `check`, never `start`/`stop`.
- A bare keyword list scored 4.8–4.9 on 2 of 4 questions.
- Leaked SQLite connection (`ResourceWarning`).
- pytest advisory in the dev lock, which CI does not audit.
- Race tests are sequential only.
- Chrome e2e never runs in CI.
- Redacted report heading reads "Interview report: Interview report".
- `HEAD /` is not accepted.
- The reviewed tree has never run in CI, because it is uncommitted (owner).

## Round 2 (2026-11-20)

Overall 6.5 → 6.5: no gain. The reviewer's weighted mean was about 6.9, capped at 6.5 because the core claim is "only partly proven".
An earlier round-2 attempt was lost when the machine slept; this is the complete rerun.

Moved, with evidence in the report:
- **Code 7 → 8.** Every step is one guarded transaction. The stuck-worker issue is gone.
- **Testing 7.5 → 8.** Truly concurrent tests. 744 backend tests at 94 %.

Did not move:
- Idea 6, Works 8, Security 8, Docs 7, Adoption 6, Health 3, Core claim 6.

New findings:
- The written report summary is generated without the question text. A real run described a LEFT JOIN answer as a "full outer join".
- README "claimed mistakes it cannot quote are never counted" is overstated: the score still uses the model's correctness rating.
- README states that CI runs start/stop on Windows/Linux. That step exists only in the uncommitted workflow.
- Pausing during the last grading completes a paused interview. Its pause time is not subtracted, and Resume errors.
- `guide.md` has no platform caveat.
- A strong answer in the reviewer's own set was misgraded at 5.9 (model limitation; 9/10 in band, all pairs ranked).
- Unchanged and owner-only: no branch protection, Dependabot PRs untouched, work uncommitted, no release.

## Round 3 (2026-11-20)

Overall 6.5 → 6.5: no gain, the second round in a row, so the loop stops here (stop condition).

The round-2 findings fixed in round 3 were not raised again:
- summary hallucination;
- pause bug;
- "never counted" wording;
- CI claim;
- `guide.md` caveat.

Lower than round 2, with the reviewer's reasons:
- **Code 8 → 7.** Long functions. The same code was 8 in round 2: reviewer variance.
- **Security 8 → 7.** The hash locks are not committed, so the public repo does not have them (owner).
- **Health 3 → 2.** Unchanged facts (owner).
- **Core claim 6 → 5.** Its own real run reproduced the benchmark's known miss: a wrong claim about tuples graded as a correct point, with a false reference answer.

New findings:
- Model-written reference answers can be wrong and are shown as fact when there is no rubric. The reviewer suggests labelling them unchecked or hiding them.
- `logs/backend.log` stays empty (warning log level), while README §9 says it holds ids and timings.

What the three reviews agree on: the remaining gap is not code.
- One maintainer, no release, no branch protection, untriaged Dependabot PRs.
- The reviewed work is uncommitted, so it has never run in CI.
- Grading quality rests on the project's own labels and one small model.

## Round 4 (2026-11-20)

Run at the owner's request after the loop had stopped. Overall 6.5 → 6.5: the third round in a row without gain.

The reviewer's weighted mean was about 6.9, capped at 6.5 for two reasons:
- the grading claim rests on the author's own labels;
- GitHub does not contain the reviewed tree.

Moved:
- **Docs 7 → 8.** Honest about what is unverified.
- **Code 7 → 8.** No bug found in the traced paths.

Fell:
- **Adoption 6 → 5.** Prerequisites and memory; only macOS used by a person.

The round-3 findings fixed in round 4 were not raised again:
- suggested answers labelled unchecked;
- `backend.log` now records activity.

New findings:
- The README's "18–38 s per grading" was optimistic against the benchmark's 44 s median. Corrected after this review.
- `assert` used as a runtime guard (`interviews.py`).
- A textbook CAP-theorem error scored 5.9 with no misconception flagged (model limitation).
- In 7 of 10 benchmark questions the subtle-error answer scored above the thin-but-correct one. The labelled order never claimed otherwise; it is still a fair observation about how the grader weighs a confident wrong claim.
