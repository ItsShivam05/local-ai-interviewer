"""The fixtures the frontend tests render (frontend/src/__tests__/fixtures/) must keep the real API's shape.

It is produced by this backend: a two-question interview, one answered and graded (fake model), one skipped, then GET /report.
If the report gains or loses a field, this test fails; regenerate the fixture with

    WRITE_REPORT_FIXTURE=1 backend/.venv/bin/python -m pytest backend/tests/test_report_fixture.py
"""
import json
import os
from pathlib import Path

from conftest import act, add_questions, answer, good_eval, start_interview, state

FIXTURES = Path(__file__).resolve().parents[2] / "frontend" / "src" / "__tests__" / "fixtures"
FIXTURE = FIXTURES / "report.json"


def build_report(client, set_id, fake) -> dict:
    add_questions(client, set_id, 2)
    fake.chat_replies = [good_eval(correctness=8, missing=["Mention partition overwrite"])]
    st = start_interview(client, set_id, max_followups=0, feedback_mode="at_end", title="Fixture interview")
    st = answer(client, st, "Reruns give the same final state; I upsert with MERGE.").json()
    act(client, st, "skip")
    rep = client.get(f"/api/interviews/{st['id']}/report").json()
    for k in ("report_created_at",):              # volatile values do not belong in a committed fixture
        rep.pop(k, None)
    return rep


def keys(x, depth=3):
    """The nested key structure (dicts only, first list element), to compare shapes rather than values."""
    if depth == 0:
        return None
    if isinstance(x, dict):
        return {k: keys(v, depth - 1) for k, v in sorted(x.items())}
    if isinstance(x, list) and x:
        return [keys(x[0], depth - 1)]
    return None


def test_the_frontend_report_fixture_matches_the_api(client, set_id, fake):
    rep = build_report(client, set_id, fake)
    if os.environ.get("WRITE_REPORT_FIXTURE") == "1":
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(rep, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert keys(fixture) == keys(rep), "the report API changed shape: regenerate the fixture (see this file's docstring)"


def interview_states(client, set_id, fake) -> dict:
    """GET /api/interviews/{id} at three moments: waiting for an answer, after a failed evaluation, after a successful retry."""
    add_questions(client, set_id, 2)
    st = start_interview(client, set_id, max_followups=0, feedback_mode="at_end", title="Fixture interview", question_audio="manual")
    out = {"awaiting": state(client, st["id"])}
    fake.chat_error = (500, "model crashed")
    out["failed"] = answer(client, st, "Reruns give the same final state.").json()
    fake.chat_error = None
    fake.chat_replies = [good_eval(correctness=7)]
    out["next"] = act(client, out["failed"], "retry").json()
    for v in out.values():
        for k in ("created_at", "started_at", "completed_at"):
            v.pop(k, None)
        v.get("time", {}).pop("elapsed_s", None)
    return out


def test_the_frontend_interview_fixtures_match_the_api(client, set_id, fake):
    states = interview_states(client, set_id, fake)
    assert states["awaiting"]["phase"] == "awaiting_answer" and states["failed"]["phase"] == "evaluation_failed"
    assert states["next"]["phase"] == "awaiting_answer" and states["next"]["progress"]["position"] == 2
    path = FIXTURES / "interview-states.json"
    if os.environ.get("WRITE_REPORT_FIXTURE") == "1":
        path.write_text(json.dumps(states, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    fixture = json.loads(path.read_text(encoding="utf-8"))
    assert {k: keys(v) for k, v in fixture.items()} == {k: keys(v) for k, v in states.items()}, "regenerate the fixtures (see docstring)"


SETUP_GETS = ("/api/health", "/api/ai", "/api/voices", "/api/sets", "/api/interviews", "/api/resumes")


def setup_responses(client, set_id) -> dict:
    """What the interview Setup page loads, before and while an interview is active (GET path -> JSON)."""
    add_questions(client, set_id, 3)
    out = {"idle": {p: client.get(p).json() for p in (*SETUP_GETS, f"/api/sets/{set_id}/questions")}}
    st = start_interview(client, set_id, max_followups=0, title="Fixture interview", question_audio="manual")
    out["active"] = {"/api/interviews": client.get("/api/interviews").json()}
    out["created"] = st
    out["idle"]["/api/health"].pop("memory", None)              # this machine's free RAM
    return _without_times(out)


def _without_times(x):
    """Timestamps change on every run and mean nothing to the frontend tests."""
    if isinstance(x, dict):
        return {k: _without_times(v) for k, v in x.items() if k not in ("created_at", "started_at", "updated_at", "completed_at")}
    if isinstance(x, list):
        return [_without_times(v) for v in x]
    return x


def test_the_frontend_setup_fixtures_match_the_api(client, set_id):
    got = setup_responses(client, set_id)
    path = FIXTURES / "setup-api.json"
    if os.environ.get("WRITE_REPORT_FIXTURE") == "1":
        path.write_text(json.dumps(got, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    fixture = json.loads(path.read_text(encoding="utf-8"))
    assert keys(fixture, 4) == keys(got, 4), "regenerate the fixtures (see docstring)"
