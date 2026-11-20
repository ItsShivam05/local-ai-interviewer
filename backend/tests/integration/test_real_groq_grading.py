"""Grading quality against the real Groq grader. Opt-in: runs ONLY when GROQ_API_KEY is set, skipped otherwise.

    GROQ_API_KEY=gsk_... backend/.venv/bin/python -m pytest -m integration -s backend/tests/integration/test_real_groq_grading.py

Three grading calls, about 12,000 tokens of your Groq allowance. They check two behaviours found in a real report on 18 Nov 2026
(prompt version eval-2.0) and addressed in eval-2.1:

  * a correct, complete answer to a BASIC question ("What is table?") was scored 7.8 and told it was "missing" the CREATE TABLE
    statement, schema ownership and set semantics;
  * the reference answer to a RESUME question stated facts the candidate never gave ("Latency is ~200-600 ms", validation that
    the candidate had said was not built yet).

A model is not deterministic, so these assert generous bounds; a failure means "look at the printed output", not necessarily a bug.
The key is never printed.
"""
import os
import re

import pytest

from app.config import Settings
from app.schemas import RubricSettings
from app.services import eval_profiles, grounding
from app.services.cloud import CloudClient
from app.services.evaluator import EvalContext, Evaluator, FollowUpDecision
from app.services.ollama import LLMError
from app.services.pricing import GRADER_MODEL

pytestmark = pytest.mark.integration

TABLE_ANSWER = ("A table is the basic storage unit in a relational database. It stores data about one kind of entity, like customers or orders, in rows "
                "and columns, where each column has a defined name and data type and each row is one record. Tables usually have a primary key to "
                "identify each row uniquely, and they relate to other tables through foreign keys.")
PROJECT_QUESTION = ("Can you walk me through the search service you built, describing the architecture, your specific contributions, and how a query "
                    "flows from the request to the results?")
PROJECT_ANSWER = ("I built it on my own. It has three parts: a small web page, a FastAPI service with six endpoints, and an indexing job. A request first "
                  "loads the user's saved filters, then the service builds one query from the text and the filters and runs it against PostgreSQL full-text "
                  "search, and the page shows the matches with the matching words highlighted. I started with a command-line prototype to prove the "
                  "ranking, then wrapped it in the API. I have not added caching or rate limiting yet; those would be my next steps, together with "
                  "logging slow queries.")
CLAIM = {"section": "Projects", "label": "Search service", "excerpt": "Search service: full-text search over product data (FastAPI, PostgreSQL)."}


class _Grader:
    """What the evaluator needs from the gateway: a chat_json that goes to the grader model."""

    def __init__(self, cloud: CloudClient, settings: Settings):
        self.cloud, self.settings = cloud, settings

    def chat_json(self, messages, schema, max_tokens=None, temperature=None, purpose="chat", model=None):
        return self.cloud.chat_json(messages, schema, model=GRADER_MODEL, max_tokens=max_tokens, temperature=temperature, purpose=purpose)


@pytest.fixture(scope="module")
def evaluator(tmp_path_factory):
    key = (os.environ.get("GROQ_API_KEY") or "").strip()
    if not key:
        pytest.skip("set GROQ_API_KEY to run the real Groq grading checks")
    settings = Settings(data_dir=tmp_path_factory.mktemp("groq-grading"))
    return Evaluator(_Grader(CloudClient(settings, key=lambda: key), settings))


def _grade(evaluator, *, question, answer, topic, difficulty, claim=None):
    profile = eval_profiles.detect_category(topic=topic, text=question)
    ctx = EvalContext(question=question, rubric=None, topic=topic, difficulty=difficulty, interview_type="technical", strictness="balanced",
                      current_question=question, current_kind="main", answer=answer, thread=[], followups_remaining=1, claim=claim, profile_key=profile)
    try:
        raw = evaluator.evaluate(ctx, RubricSettings())
    except LLMError as e:
        if e.code == "rate_limited":
            pytest.skip(f"Groq rate limit reached: {e.message}")
        raise
    sources = None if claim is None else [question, claim["excerpt"], claim["label"]]
    final = evaluator.finalize(raw, RubricSettings(), FollowUpDecision(False), difficulty=difficulty, answer=answer, profile_key=profile, resume_sources=sources,
                               question=question)
    print(f"\n{question[:60]!r}: score {final.score} ({final.classification}), profile {final.profile}, level {final.question_level}")
    print("  dimensions:", {k: v for k, v in final.dimension_scores.model_dump().items() if v is not None})
    print("  missing:", final.missing_concepts)
    print("  reference:", final.ideal_answer)
    print("  flags:", [f["code"] for f in final.consistency_flags])
    return final


@pytest.mark.parametrize("run", [1, 2])
def test_a_correct_complete_basic_definition_scores_well_and_is_not_asked_for_trivia(evaluator, run):
    final = _grade(evaluator, question="What is table?", answer=TABLE_ANSWER, topic="SQL", difficulty="easy")
    assert final.question_level == "basic" and final.profile == "sql"
    assert final.classification in ("correct", "correct_incomplete") and not final.misconceptions
    assert final.score >= 8.0, "a correct, complete definition should not be capped below 8"
    trivia = [m for m in final.missing_concepts if re.search(r"create table|schema owner|set semantic|ddl statement", m, re.I)]
    assert not trivia, f"a definition was told it is missing implementation trivia: {trivia}"


def test_a_resume_reference_answer_does_not_invent_facts_about_the_candidates_project(evaluator):
    final = _grade(evaluator, question=PROJECT_QUESTION, answer=PROJECT_ANSWER, topic="Search", difficulty="medium", claim=CLAIM)
    invented = grounding.unsupported_figures(final.ideal_answer, [PROJECT_ANSWER, PROJECT_QUESTION, CLAIM["excerpt"]])
    assert not invented, f"the suggested answer contains figures nobody mentioned: {invented}"
    assert not any(f["code"] == "reference_figures_unverified" for f in final.consistency_flags)
    # the candidate said caching and rate limiting are NOT built: the outline must not present them as done
    assert not re.search(r"\b(i|we) (added|implemented|built|use[ds]?) (a |an |the )?(cache|caching|rate limit)", final.ideal_answer, re.I), final.ideal_answer
