"""The grading benchmark's summary (backend/benchmarks/grading/run.py): the numbers it reports must follow from the raw results."""
import importlib.util
import json
from pathlib import Path

RUN = Path(__file__).resolve().parents[1] / "benchmarks" / "grading" / "run.py"
spec = importlib.util.spec_from_file_location("bench_run", RUN)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def row(case, kind, score, rep=1, cls="correct", mis=()):
    return {"case": case, "kind": kind, "repeat": rep, "score": score, "classification": cls, "misconceptions": list(mis),
            "unverified_misconceptions": [], "evidence_verified": 1, "evidence_total": 1, "seconds": 30.0, "model": "m",
            "prompt_version": "p", "profiles_version": "v", "machine": "x", "temperature": 0.2}


def test_labelled_set_is_complete():
    data = json.loads((RUN.parent / "answers.json").read_text())
    assert len(data["questions"]) == 10 and len(data["injections"]) == 6
    for q in data["questions"]:
        assert set(q["answers"]) == set(bench.KINDS)
    assert len(bench.cases(data)) == 56


def test_summary_counts_bands_ranking_spread_and_failures(tmp_path):
    q = "sql-where-having"
    rows = [row(f"{q}/strong", "strong", 8.0), row(f"{q}/strong", "strong", 7.0, rep=2),          # median 7.5, spread 1.0
            row(f"{q}/partial", "partial", 5.0),
            row(f"{q}/subtle", "subtle", 6.0, cls="correct"),                                        # error NOT flagged: outside band
            row(f"{q}/wrong", "wrong", 6.5),                                                         # ranks above subtle: a miss
            row(f"{q}/idk", "idk", 0.5),
            row(f"{q}/injection-1", "injection", 2.0)]
    rows.append({"case": f"{q}/partial", "kind": "partial", "repeat": 2, "error": "timeout", "message": "x"})
    p = tmp_path / "r.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))
    md = bench.summarize(p)
    assert "7 succeeded, 1 failed" in md
    assert "| subtle | 1 | 6.0 | 6.0 | 6.0 | ≤ 6.5 and error flagged | 0/1 |" in md
    assert "| wrong | 1 | 6.5 | 6.5 | 6.5 | ≤ 3.0 | 0/1 |" in md
    # 7 labelled pairs; partial(5.0) > wrong(6.5) fails, subtle(6.0) > wrong(6.5) fails
    assert "**5/7**" in md and "partial 5.0 ≤ wrong 6.5" in md
    assert "max 1.00" in md
    assert "| sql-where-having/partial #2 | failed: timeout | |" in md
