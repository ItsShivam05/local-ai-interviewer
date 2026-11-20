"""Term-list check: does an answer that only lists terms, explaining nothing, stay at 3 or below with the REAL local model?

Review round 1 (2026-11-20) found such lists scored up to 4.9. The app now caps them (grounding.is_term_list). The first four lists
below were written by that independent review and the rule was built from them, so they are not held out; the last four were written
afterwards for other benchmark questions. Each is graded once on the app's path (benchmarks/grading/run.py: evaluate + finalize).

    backend/.venv/bin/python backend/benchmarks/grading/term_lists.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bench_run", HERE / "run.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

from app.config import Settings, load_dotenv  # run.py put backend/ on the path
from app.services.evaluator import Evaluator
from app.services.grounding import is_term_list
from app.services.ollama import OllamaClient

LISTS = [
    ("review", "What is the difference between a list and a tuple in Python?",
     "Mutable, immutable, hashable, dictionary keys, memory, performance, sequence, indexing, slicing, append, CPython, garbage collection, iteration."),
    ("review", "What happens during a TCP three-way handshake?",
     "SYN, SYN-ACK, ACK, sequence numbers, reliability, connection, TCP, packets, ports, sockets, latency."),
    ("review", "What is the difference between INNER JOIN and LEFT JOIN?",
     "INNER JOIN, LEFT JOIN, OUTER JOIN, NULL, matching rows, keys, foreign key, performance, indexes, query planner."),
    ("review", "What is a deadlock and how can you prevent it?",
     "Mutual exclusion, hold and wait, circular wait, no preemption, lock ordering, timeouts, mutex, semaphore, threads, starvation, livelock."),
    ("new", "What is idempotency in an ETL pipeline and how do you achieve it?",
     "Upserts, MERGE, business keys, partitions, watermarks, dedupe, batch ids, retries, checkpoints."),
    ("new", "What is overfitting in machine learning and how can you reduce it?",
     "Variance, noise, regularisation, dropout, early stopping, cross-validation, more data, L1, L2."),
    ("new", "What is a cache, what is cache invalidation, and what is one strategy for it?",
     "Redis, TTL, write-through, cache-aside, stale data, eviction, LRU, hit rate."),
    ("new", "What does a Python generator do, and why would you use one?",
     "yield, lazy evaluation, iterators, memory, next(), StopIteration, pipelines, generator expressions."),
]


def main() -> None:
    load_dotenv()
    evaluator = Evaluator(OllamaClient(Settings.from_env()))
    for source, question, answer in LISTS:
        r = bench.grade(evaluator, {"case": "term-list", "kind": "term_list", "answer": answer,
                                    "question": {"text": question, "topic": None, "difficulty": None, "rubric": None}})
        print(json.dumps({"source": source, "question": question, "detected": is_term_list(answer), "score": r["score"],
                          "classification": r["classification"]}), flush=True)


if __name__ == "__main__":
    main()
