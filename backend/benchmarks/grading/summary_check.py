"""Report summary check: with the real local model, does the written summary describe the questions that were really asked?

Review round 2 saw a LEFT JOIN answer summarised as "full outer join" (the summary model never saw the questions). Three runs.

    backend/.venv/bin/python backend/benchmarks/grading/summary_check.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.config import Settings
from app.services.evaluator import Evaluator
from app.services.ollama import OllamaClient
from app.services.reports import narrative_digest
def q(pos, text, topic, correct, missing):
    return {"position": pos, "text": text, "topic": topic, "score": 6.5, "source": "bank", "resume_id": None,
            "turns": [{"evaluation": {"correct_points": correct, "missing_concepts": missing, "misconceptions": []}}]}
data = {"interview": {"title": "SQL practice"}, "topics": [{"topic": "SQL", "average_score": 6.5}],
        "summary": {"total_questions": 2, "answered": 2, "skipped": 0, "unanswered": 0, "average_score": 6.5},
        "questions": [q(1, "What does a LEFT JOIN return, and how is it different from an INNER JOIN?", "SQL",
                        ["keeps every row from the left table", "fills NULLs for unmatched right-side columns"], ["filtering in WHERE vs ON"]),
                      q(2, "When would you add an index to a column?", "SQL", ["columns used in WHERE and JOIN"], ["write cost of indexes"])]}
digest = narrative_digest(data)
ev = Evaluator(OllamaClient(Settings.from_env()))
for i in range(3):
    n = ev.narrative(digest)
    text = " ".join([n.overall_summary, *n.strengths, *n.knowledge_gaps, *n.recommendations]).lower()
    print(i, "LEFT JOIN" if "left join" in text else "-", "| outer:", "full outer" in text or "outer join" in text, "|", n.overall_summary[:160])
