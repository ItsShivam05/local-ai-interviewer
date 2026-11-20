"""Grading benchmark: how well do the app's scores track the quality of an answer, with the REAL local model?

Every labelled answer in answers.json is graded exactly as the app grades a typed answer in a fixed interview (Evaluator.evaluate,
then Evaluator.finalize: evidence grounding, the evaluation profile, app-computed score and classification), REPEATS times.

    backend/.venv/bin/python backend/benchmarks/grading/run.py                 # grade everything (resumes an unfinished run)
    backend/.venv/bin/python backend/benchmarks/grading/run.py --repeats 1     # a quicker single pass
    backend/.venv/bin/python backend/benchmarks/grading/run.py --summarize backend/benchmarks/grading/results/<file>.jsonl

Needs Ollama running with the model in LLM_MODEL (default qwen3.5:4b). Contacts only the local Ollama. One grading takes 20-70 s on
an 8 GB Apple Silicon Mac, so the full set (56 answers x 3 repeats) takes 1-3 hours. Results go to results/<date>-<model>.jsonl
(one line per grading, written as it finishes) and a Markdown summary next to it.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))          # backend/ on the path, so `app` imports like in the tests

from app.config import Settings, load_dotenv
from app.schemas import RubricSettings
from app.services import eval_profiles
from app.services.evaluator import EvalContext, Evaluator, FollowUpDecision
from app.services.ollama import LLMError, OllamaClient
from app.services.prompts import PROMPT_VERSION

KINDS = ("strong", "partial", "subtle", "wrong", "idk")


def cases(data: dict[str, Any]) -> list[dict[str, Any]]:
    qs = {q["id"]: q for q in data["questions"]}
    out = [{"case": f"{q['id']}/{k}", "kind": k, "question": q, "answer": q["answers"][k]} for q in data["questions"] for k in KINDS]
    out += [{"case": f"{inj['question']}/injection-{i + 1}", "kind": "injection", "question": qs[inj["question"]], "answer": inj["text"]}
            for i, inj in enumerate(data["injections"])]
    return out


def grade(evaluator: Evaluator, c: dict[str, Any]) -> dict[str, Any]:
    q = c["question"]
    profile = eval_profiles.detect_category(topic=q["topic"], text=q["text"])
    ctx = EvalContext(question=q["text"], rubric=q["rubric"], topic=q["topic"], difficulty=q["difficulty"], interview_type="technical",
                      strictness="balanced", current_question=q["text"], current_kind="main", answer=c["answer"],
                      followups_remaining=0, profile_key=profile)
    t0 = time.monotonic()
    raw = evaluator.evaluate(ctx, RubricSettings())
    final = evaluator.finalize(raw, RubricSettings(), FollowUpDecision(False), difficulty=q["difficulty"], answer=c["answer"], question=q["text"],
                               profile_key=profile)
    ev = final.evidence
    return {"score": final.score, "classification": final.classification, "profile": final.profile, "seconds": round(time.monotonic() - t0, 1),
            "misconceptions": final.misconceptions, "unverified_misconceptions": final.unverified_misconceptions,
            "evidence_verified": sum(1 for e in ev if e.verified), "evidence_total": len(ev)}


def run(out: Path, repeats: int) -> None:
    data = json.loads((HERE / "answers.json").read_text())
    load_dotenv()
    settings = Settings.from_env()
    evaluator = Evaluator(OllamaClient(settings))
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            r = json.loads(line)
            if "score" in r:
                done.add((r["case"], r["repeat"]))
    todo = [(c, i) for i in range(1, repeats + 1) for c in cases(data) if (c["case"], i) not in done]
    print(f"{len(done)} gradings already in {out.name}, {len(todo)} to go (model {settings.llm_model}, prompt {PROMPT_VERSION})", flush=True)
    meta = {"model": settings.llm_model, "prompt_version": PROMPT_VERSION, "profiles_version": eval_profiles.PROFILES_VERSION,
            "machine": f"{platform.system()} {platform.machine()}", "temperature": settings.llm_temperature}
    with out.open("a") as f:
        for n, (c, i) in enumerate(todo, 1):
            row: dict[str, Any] = {"case": c["case"], "kind": c["kind"], "repeat": i, **meta}
            try:
                row.update(grade(evaluator, c))
            except LLMError as e:              # recorded, not hidden: a failed grading is part of the result
                row.update({"error": e.code, "message": e.message})
            f.write(json.dumps(row) + "\n")
            f.flush()
            print(f"[{n}/{len(todo)}] {c['case']} #{i}: {row.get('score', row.get('error'))} ({row.get('seconds', '-')} s)", flush=True)


def summarize(path: Path) -> str:
    data = json.loads((HERE / "answers.json").read_text())
    bands, order = data["bands"], data["order"]
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    ok = [r for r in rows if "score" in r]
    failed = [r for r in rows if "error" in r]
    by_case: dict[str, list[dict[str, Any]]] = {}
    for r in ok:
        by_case.setdefault(r["case"], []).append(r)
    med = {k: statistics.median(x["score"] for x in v) for k, v in by_case.items()}
    meta = ok[0] if ok else {}
    lines = [f"# Grading benchmark: {path.stem}", "",
             f"Model `{meta.get('model')}`, prompt `{meta.get('prompt_version')}`, profiles `{meta.get('profiles_version')}`, "
             f"temperature {meta.get('temperature')}, {meta.get('machine')}. Generated by `run.py --summarize` from `{path.name}`.", "",
             f"Gradings: {len(ok)} succeeded, {len(failed)} failed (model error or timeout, counted as failures below, never dropped).", ""]

    # 1. bands
    lines += ["## Score by answer type (median of repeats per answer)", "", "| Type | Answers | Mean | Min | Max | Expected | Within band |",
              "|---|---|---|---|---|---|---|"]
    for kind in (*KINDS, "injection"):
        ks = [c for c in med if by_case[c][0]["kind"] == kind]
        if not ks:
            continue
        vals = [med[c] for c in ks]
        b = bands[kind]
        def hit(c: str, b: dict = b, kind: str = kind) -> bool:
            s = med[c]
            if "min" in b and s < b["min"]:
                return False
            if "max" in b and s > b["max"]:
                return False
            if b.get("needs_error"):        # the plausible wrong claim must be noticed: a grounded misconception, or not called correct
                last = by_case[c][-1]
                return bool(last["misconceptions"]) or last["classification"] != "correct"
            return True
        hits = sum(hit(c) for c in ks)
        exp = " and ".join(x for x in (f"≥ {b['min']}" if "min" in b else "", f"≤ {b['max']}" if "max" in b else "",
                                       "error flagged" if b.get("needs_error") else "") if x)
        lines.append(f"| {kind} | {len(ks)} | {statistics.mean(vals):.1f} | {min(vals):.1f} | {max(vals):.1f} | {exp} | {hits}/{len(ks)} |")

    # 2. ordering within each question
    qids = sorted({c.split("/")[0] for c in med})
    pairs = total = 0
    misses = []
    for q in qids:
        for hi, lo in order:
            a, b2 = f"{q}/{hi}", f"{q}/{lo}"
            if a in med and b2 in med:
                total += 1
                if med[a] > med[b2]:
                    pairs += 1
                else:
                    misses.append(f"{q}: {hi} {med[a]:.1f} ≤ {lo} {med[b2]:.1f}")
    lines += ["", "## Ranking within each question", "",
              f"Pairs ranked as labelled ({', '.join(f'{h} > {lo}' for h, lo in order)}): **{pairs}/{total}**.", ""]
    lines += [f"- not as labelled: {m}" for m in misses] or ["- every pair ranked as labelled"]

    # 3. repeatability
    spreads = [max(x["score"] for x in v) - min(x["score"] for x in v) for v in by_case.values() if len(v) > 1]
    if spreads:
        lines += ["", "## Repeatability", "",
                  f"Spread (max − min) of one answer's score across repeats: median {statistics.median(spreads):.2f}, "
                  f"90th percentile {sorted(spreads)[int(0.9 * (len(spreads) - 1))]:.2f}, max {max(spreads):.2f} "
                  f"({len(spreads)} answers graded more than once)."]

    # 4. evidence and errors
    ev_ok = sum(r["evidence_verified"] for r in ok)
    ev_all = sum(r["evidence_total"] for r in ok)
    lines += ["", "## Evidence", "", f"Quotes the grader cited that were found in the answer: {ev_ok}/{ev_all}. "
              f"Gradings with at least one unverified (uncounted) misconception: {sum(1 for r in ok if r['unverified_misconceptions'])}/{len(ok)}."]
    if ok:
        secs = [r["seconds"] for r in ok]
        lines += ["", "## Time", "", f"Seconds per grading: median {statistics.median(secs):.0f}, max {max(secs):.0f}."]

    # 5. every answer
    lines += ["", "## Every answer", "", "| Answer | Scores | Classification (last) |", "|---|---|---|"]
    for c in sorted(by_case):
        v = by_case[c]
        scores = ", ".join(format(x["score"], ".1f") for x in v)
        lines.append(f"| {c} | {scores} | {v[-1]['classification']} |")
    for r in failed:
        lines.append(f"| {r['case']} #{r['repeat']} | failed: {r['error']} | |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--out", type=Path, help="results file (.jsonl); default results/<today>-<model>.jsonl")
    ap.add_argument("--summarize", type=Path, help="only write the Markdown summary of an existing results file")
    a = ap.parse_args()
    if a.summarize:
        md = a.summarize.with_suffix(".md")
        md.write_text(summarize(a.summarize))
        print(md.read_text())
        return
    settings = Settings.from_env()
    out = a.out or HERE / "results" / f"{date.today().isoformat()}-{settings.llm_model.replace(':', '-').replace('/', '-')}.jsonl"
    out.parent.mkdir(exist_ok=True)
    run(out, a.repeats)
    md = out.with_suffix(".md")
    md.write_text(summarize(out))
    print(md.read_text())


if __name__ == "__main__":
    main()
