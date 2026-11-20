# How answers are evaluated (Interview Intelligence 2.0)

This document describes exactly what happens between "Submit answer" and the score you see. Every step below is implemented in
`backend/app/services/` and covered by tests in `backend/tests/`.

## Pipeline

```
answer saved (before any model call)
  │
  ├─ voice answer? → transcript repair (one small model call; falls back to the original text on any problem)
  │
  ├─ evaluation profile chosen by rules        eval_profiles.detect_category()
  ├─ ONE grading call, schema-constrained       prompts.eval_schema_for(profile)
  ├─ validation (Pydantic), one repair retry    evaluator._call_validated()
  ├─ grounding + consistency checks             grounding.ground()
  ├─ deterministic weighted score               eval_profiles.score_answer()
  ├─ follow-up decision (code, not the model)   evaluator.decide_followup() / adaptive.choose_followup()
  └─ stored with provenance                     Evaluation.provenance
```

No step adds a model call compared with v1: the profile, evidence and stretch question are part of the single grading call. One
answer therefore costs one call, or up to three when it was spoken (transcript repair) and a follow-up is asked (follow-up polish);
in cloud mode each of those counts against your rate limit.

## 1. Evaluation profiles

Each question is graded with a profile picked **deterministically** (never by the model) from the interview type, the question's
topic and its text:

| Profile | Extra dimensions scored | Emphasis |
|---|---|---|
| General technical | — | identical to v1 weights (correctness 30, completeness 20, depth 15, practical 15, clarity 10, production 10) |
| SQL | conceptual understanding, problem-solving, edge cases | set semantics, NULLs, join/aggregation correctness |
| Python | conceptual understanding, problem-solving, edge cases | language semantics, idioms, error handling |
| Data engineering | problem-solving, edge cases, trade-offs | idempotency, incremental loads, late/duplicate data, cost |
| Machine learning | conceptual understanding, trade-offs | statistics, evaluation methodology, leakage |
| System design | problem-solving, edge cases, trade-offs (20 %) | requirements, architecture, scaling, failure handling |
| Software engineering | problem-solving, trade-offs | design, testing, maintainability |
| Behavioural | — (core dimensions re-defined) | relevance/credibility, STAR completeness, reflection, concreteness, structure |

Detection order: an HR interview → behavioural; an explicit topic alias (e.g. topic "SQL") → that profile; keyword rules on the topic,
then on the question text — every rule is scored by its number of distinct keyword hits and the best wins only when unambiguous (a tie
falls back to *general*, since a wrong profile is worse than a neutral one); otherwise *general*. In a technical interview, behavioural keywords in the question text are ignored.

The five core dimensions are always scored. Extra dimensions are requested only by the profiles above. If the model omits a requested
dimension it is **left out of the weighting** (and flagged), never treated as zero. `GET /api/evaluation/profiles` lists every profile
with its weights and meanings.

### Weights you control

The rubric editor in *Settings* still works for every profile: each of the six original dimensions is multiplied by
`your weight / default weight`. Doubling *correctness* doubles it everywhere; a weight of 0 removes that dimension everywhere.
Weights are re-normalised over the dimensions actually scored, and the normalised weights are stored with every evaluation.

### Difficulty awareness

- **Basic** questions (definitions; or difficulty *easy*): depth, practical application, problem-solving, edge cases and trade-offs
  count at 35 % (the v1 rule for depth and practical application, extended to the newer dimensions a definition does not ask for).
  The grader is also told not to mark an extra dimension down when the question does not call for it, and not to list syntax,
  internals or related features as "missing" from a correct definition.
- **Advanced** questions (difficulty *hard*, or the model's classification when you set none): in the category profiles, depth, edge
  cases, trade-offs and production awareness count 125 %. The general profile has no advanced adjustment.

The general profile reproduces v1 scores exactly at every level (tested in `test_eval_profiles.py`). **Questions that fall into a
category profile (SQL, Python, …) are scored with that profile's weights, so their scores can differ from v1** — this applies to fixed
and adaptive interviews alike, and the profile used is shown with every answer.

## 2. Evidence and grounding

The grader must back its analysis with **short verbatim quotes** from the answer (`evidence`). The app then checks them:

- A quote is **verified** only if it occurs in the answer after normalising case, punctuation and spacing (elided quotes with `...`
  must match fragment by fragment, in order; 1-word quotes prove nothing). For voice answers both the raw transcript and the repaired
  text are searched.
- A misconception counts as an **error** only if it is grounded: a verified "incorrect" quote supports it, or text it quotes is in the
  answer (content words, boilerplate such as "the candidate said" ignored). Ungrounded ones are kept and shown as *"possible errors (not found in your answer, not counted as mistakes)"*. They never make an
  answer "incorrect" and are not listed as mistakes. They are not removed from the score: the score is computed from the grader's
  dimension ratings, and a grader that believed an unquotable error may have rated correctness lower because of it. The app does not
  try to undo that, because it cannot tell which part of a rating came from which claim.

## 3. Consistency rules (deterministic)

| Situation | What the app does |
|---|---|
| short "I don't know"-style answer that the grader also found nothing of value in (no correct points, or correctness ≤ 4), scored above 2 | caps every dimension at 2; classified *no attempt*; no follow-up. A short real answer that merely contains "don't know" is not capped |
| Correctness ≤ 3 but ≥ 2 correct points, **no** claimed error of any kind, grader not unsure | raises correctness to 5 and says why: an incomplete answer is scored under completeness, not correctness |
| Correctness ≥ 8 with a verified error | confidence lowered to medium, flagged |
| Correctness ≥ 7 with nothing correct cited | confidence lowered to medium, flagged |
| Quoted evidence not found in the answer | quote marked unverified, flagged |
| Resume question: the suggested answer contains figures (10 or more, or decimals) that appear in neither your answers, the questions nor the resume excerpt | flagged and shown under the suggested answer: "illustrations, not facts about your work" |

Every adjustment is written in plain words into the evaluation (`adjustments`, `consistency_flags`) and shown under *How this was graded*.

### Reference answers on resume questions

The grader cannot know the facts of your own project. For a resume question it is told to outline what a strong answer covers, using
only what you and the resume said, and never to invent numbers, tools or results, or to present as done something you said is not
built. The app labels it **"What a strong answer covers"** (instead of "Suggested answer") and checks its figures as in the table above.
This check catches invented numbers; it cannot catch an invented statement that contains no number.

## 4. Classification

`correct` · `correct_incomplete` · `partially_correct` · `incorrect` · `no_attempt` · `uncertain` — computed by
`grounding.classify()` from the (adjusted) scores, grounded errors, correct points and confidence. An answer is only *incorrect* when
a grounded error exists (or nothing correct was said and correctness ≤ 2). A valid alternative approach with no grounded error cannot
be classified incorrect. Low grader confidence yields *uncertain* rather than a confident label.

## 5. Score and verdict

`score = Σ wᵢ·dᵢ / Σ wᵢ` over the scored dimensions, rounded to 0.1. Any total, verdict or classification the model volunteers is
ignored (tested). Verdicts: ≥9 Excellent, ≥7 Good, ≥5 Partial, ≥3 Weak, else Incorrect. Question and interview aggregation rules are
unchanged from v1 and printed in every report.

## 6. Reproducibility and provenance

Each stored evaluation records: `prompt_version` (currently `eval-2.1`), `profiles_version`, a `rubric` fingerprint
(`<profile>-v<version>-<hash of profile weights + your rubric>`), the question level, the model route (`graded_by`), the generation
temperature, and an `input_hash` (SHA-256 prefix of the exact grading messages — the hash, not the text). Identical input therefore
has an identical hash, so differing grades for the same input can be identified. Generation settings are the ones you configured
(`LLM_TEMPERATURE`, default 0.2); this release does not change them.

**Limits.** Grounding verifies that evidence *exists* in the answer, not that the grader's judgement about it is right; a small local
model can still be wrong on facts, especially without a reference answer. Treat scores as study feedback.

## 7. Report analytics

All computed in code from stored evaluations (`reports.intelligence()`): classification breakdown, difficulty-wise averages,
conceptual (correctness, conceptual understanding, depth) vs practical (practical application, problem-solving, edge cases, relevant
production awareness) averages, profile usage, evidence verification counts, consistency flags, a learning plan from the three
weakest skills, progress per topic versus the most recent earlier report covering it, the adaptive decision timeline and resume
coverage. Older reports without these fields still open.

## 8. Measured grading quality (benchmark)

`backend/benchmarks/grading/` grades a fixed set of labelled answers with the real local model, exactly as the app grades a typed
answer in a fixed interview (`Evaluator.evaluate`, then `Evaluator.finalize`), and summarises how the app's scores track the labels.

```bash
backend/.venv/bin/python backend/benchmarks/grading/run.py            # 56 answers x 3 repeats; resumes an unfinished run
backend/.venv/bin/python backend/benchmarks/grading/run.py --summarize backend/benchmarks/grading/results/<file>.jsonl
```

**The set** (`answers.json`): 10 technical questions (SQL, Python, ETL, ML, networking, operating systems, concurrency, system
design), 3 with a rubric and 7 without. Each question has five answers: *strong*, *partial* (correct but thin), *subtle* (mostly right
with one plausible but wrong claim), *wrong* and *I don't know*. There are also 6 prompt-injection attempts. The expected score band for
each kind was written down before the first run and has not been changed since.

**Result, 2026-11-19** (`qwen3.5:4b`, prompt `eval-2.1`, temperature 0.2, MacBook Air M2 8 GB; raw data and summary in
[`results/2026-11-19-qwen3.5-4b.md`](../backend/benchmarks/grading/results/2026-11-19-qwen3.5-4b.md)):

| Measure | Result |
|---|---|
| Ranking within each question (strong > partial > wrong, strong > subtle > wrong, strong/partial > I don't know) | 70 / 70 pairs |
| Answers inside their expected band | 55 / 56 |
| Mean score: strong / partial / subtle / wrong / I don't know / injection | 7.8 / 4.0 / 4.4 / 0.9 / 0.6 / 1.1 |
| Same answer graded 3 times: spread of its score | median 0.2, max 2.0 points |
| Quotes the grader cited that are in the answer | 273 / 279 |
| Gradings that failed | 2 of 170, both timeouts while the computer was heavily loaded (kept in the results) |

**What it shows and what it does not.**
- The miss: the subtle error "a tuple that contains lists can be a dictionary key" was graded correct (about 7.7) in all three runs.
  A small model can miss a plausible wrong claim, especially without a rubric.
- A strong answer tops out around 8.3, so the scale is compressed at the top.
- The labels were written for the project, not by independent graders, and there is one rater-free notion of "right" per answer.
  This is evidence that scores *rank* answers sensibly, not that a 7.8 equals what a human interviewer would give.
- One machine, one model, typed answers only. Voice answers, cloud grading, resume questions and adaptive follow-ups are not covered.
- The prompt was not tuned on this set. Changing the prompt to fix the miss above would make the set a training set; a new,
  separate set would then be needed to measure it.

### Lists of terms with nothing explained

An answer that is only a run of terms ("Mutable, immutable, hashable, memory, slicing, …") is capped at 3 in every dimension, with
the reason in the feedback (`grounding.is_term_list`): at least six comma- or line-separated parts, none longer than four words, and
no part that explains anything. A question that asks for a list ("List the…", "Name three…", "What are the…") is never capped.
The rule is deliberately narrow: a terse answer that says what to do ("Use upserts, overwrite partitions, …") is left to the grader,
and a list that happens to contain a word like "write-through" is not detected.

`backend/benchmarks/grading/term_lists.py` grades eight such lists with the real model. 2026-11-20
([results](../backend/benchmarks/grading/results/2026-11-20-term-lists.jsonl)): the seven detected lists scored 1.2–2.9 (an
independent review had measured up to 4.9 before the rule); the eighth was not detected and scored 0.7 here but 3.8 in another
run. The first four lists came from that review and shaped the rule, so they are not held out. None of the 50 labelled benchmark
answers is a term list; the one injection made of a JSON blob is, and the cap can only lower its scores (all already ≤ 2.0).
