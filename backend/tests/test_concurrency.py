"""Truly concurrent requests against the real worker thread (review round 1: the race tests were all sequential).

The fake model's grading call is held open on a gate, so requests really overlap with an evaluation in progress, and several clients
send at the same instant (a barrier), each from its own thread, through the same app.
"""
from __future__ import annotations

import threading
import time

import httpx
from fastapi.testclient import TestClient

from app.deps import build_container
from app.main import create_app
from app.services.ollama import OllamaClient
from conftest import FakeOllama, add_questions, good_eval, make_settings


def gated_app(tmp_path):
    fake, gate = FakeOllama(), threading.Event()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            assert gate.wait(10), "test gate never opened"
        return fake.handler(request)

    settings = make_settings(tmp_path)
    ollama = OllamaClient(settings, http=httpx.Client(base_url=settings.ollama_host, transport=httpx.MockTransport(handler)))
    container = build_container(settings, ollama=ollama)          # the real single-worker ThreadPoolExecutor
    app = create_app(settings, container)
    return app, fake, gate


def client(app) -> TestClient:
    return TestClient(app, base_url="http://127.0.0.1:3000")


def wait_for(c: TestClient, iid: int, cond, timeout: float = 10.0) -> dict:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        st = c.get(f"/api/interviews/{iid}").json()
        if cond(st):
            return st
        time.sleep(0.05)
    raise AssertionError(f"state never reached: {st['status']}/{st['phase']}")


def start(c: TestClient, n: int = 2) -> dict:
    set_id = c.get("/api/sets").json()[0]["id"]
    add_questions(c, set_id, n)
    r = c.post("/api/interviews", json={"set_id": set_id, "config": {"max_followups": 0, "feedback_mode": "at_end"}})
    assert r.status_code == 201, r.text
    return r.json()


def test_simultaneous_submits_of_one_answer_make_exactly_one_model_call(tmp_path):
    app, fake, gate = gated_app(tmp_path)
    fake.chat_replies = [good_eval()]
    main = client(app)
    st = start(main)
    n, barrier, codes = 8, threading.Barrier(8), []

    def submit() -> None:
        c = client(app)
        barrier.wait()
        codes.append(c.post(f"/api/interviews/{st['id']}/answer", json={"turn_id": st["current_turn_id"], "text": "same answer"}).status_code)

    threads = [threading.Thread(target=submit) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert sorted(codes) == [200] + [409] * (n - 1), codes
    gate.set()
    wait_for(main, st["id"], lambda s: s["phase"] == "awaiting_answer" and s["progress"]["position"] == 2)
    assert len(fake.chat_calls) == 1


def test_pause_end_and_delete_while_grading_runs(tmp_path):
    app, fake, gate = gated_app(tmp_path)
    fake.chat_replies = [good_eval()]
    c = client(app)
    st = start(c)
    iid = st["id"]
    assert c.post(f"/api/interviews/{iid}/answer", json={"turn_id": st["current_turn_id"], "text": "my answer"}).status_code == 200
    assert c.get(f"/api/interviews/{iid}").json()["phase"] == "evaluating"
    assert c.post(f"/api/interviews/{iid}/end").status_code == 409            # cannot end mid-grading
    assert c.delete(f"/api/interviews/{iid}").status_code == 409              # nor delete it
    assert c.post(f"/api/interviews/{iid}/pause").json()["status"] == "paused"   # pausing is allowed and the grade still lands
    gate.set()
    after = wait_for(c, iid, lambda s: s["phase"] != "evaluating")
    assert after["status"] == "paused" and len(fake.chat_calls) == 1
    resumed = c.post(f"/api/interviews/{iid}/resume").json()
    assert resumed["status"] == "in_progress" and resumed["phase"] == "awaiting_answer" and resumed["progress"]["position"] == 2
    answered = [q for q in c.get(f"/api/interviews/{iid}").json()["items"] if q["status"] == "answered"]
    assert len(answered) == 1                                                 # the answer graded while paused was kept and counted


def test_pausing_during_the_last_grading_closes_the_pause_when_the_interview_completes(tmp_path):
    """Review round 2: the grade landed, the interview completed while still 'paused', the pause was never closed (its time
    counted as interview time) and Resume answered with an error."""
    app, fake, gate = gated_app(tmp_path)
    fake.chat_replies = [good_eval()]
    c = client(app)
    st = start(c, n=1)
    iid = st["id"]
    c.post(f"/api/interviews/{iid}/answer", json={"turn_id": st["current_turn_id"], "text": "my answer"})
    assert c.post(f"/api/interviews/{iid}/pause").json()["status"] == "paused"
    time.sleep(1.2)                                                           # a pause long enough to measure
    gate.set()
    done = wait_for(c, iid, lambda s: s["phase"] == "done")
    assert done["status"] == "completed" and done["progress"]["answered"] == 1
    with app.state.c.db.read() as conn:
        row = conn.execute("SELECT paused_at, paused_seconds FROM interviews WHERE id=?", (iid,)).fetchone()
    assert row["paused_at"] is None and row["paused_seconds"] >= 1.0          # the pause is closed and not counted as interview time
    assert c.post(f"/api/interviews/{iid}/resume").status_code == 409          # finished: nothing to resume (clear 409, not a crash)
