"""Interview Intelligence 2.0 end to end: profile-aware grading, grounding, provenance, consistency, analytics and privacy."""
from contextlib import closing
import json
import time
import os
import sqlite3

from conftest import answer, start_interview
from intel_fixtures import graded


def add(client, set_id, text, topic=None, difficulty=None):
    r = client.post(f"/api/sets/{set_id}/questions", json={"text": text, "topic": topic, "difficulty": difficulty})
    assert r.status_code == 201


def test_sql_question_is_graded_with_the_sql_profile_and_full_provenance(client, set_id, fake):
    add(client, set_id, "Explain LEFT JOIN semantics.", "SQL", "medium")
    fake.chat_replies = [graded(8, evidence=[{"kind": "correct", "point": "keeps left rows", "quote": "keeps all rows from the left"}])]
    st = start_interview(client, set_id, max_followups=0)
    st = answer(client, st, "It keeps all rows from the left table and NULLs the rest").json()
    req = fake.chat_calls[0]
    schema = req["format"]
    assert "edge_cases" in schema["properties"]["dimension_scores"]["required"]            # the profile's extra dimensions were requested
    assert "EVALUATION PROFILE: SQL" in req["messages"][0]["content"]
    ev = st["current"]["thread"][0]["evaluation"]
    assert ev["profile"] == "sql" and ev["classification"] == "correct" and ev["evidence"][0]["verified"] is True
    assert abs(sum(ev["weights"].values()) - 1) < 0.01
    prov = ev["provenance"]
    assert prov["prompt_version"] == "eval-2.1" and prov["rubric"].startswith("sql-v") and prov["input_hash"] and prov["graded_by"]["model"]
    assert "temperature" in prov


def test_model_supplied_total_is_ignored(client, set_id, fake):
    add(client, set_id, "What is a primary key?", "SQL", "easy")
    fake.chat_replies = [graded(4, extra={"score": 10, "verdict": "Excellent", "classification": "correct"})]
    st = start_interview(client, set_id, max_followups=0)
    ev = answer(client, st, "It identifies rows").json()["current"]["thread"][0]["evaluation"]
    assert ev["score"] == 4.0 and ev["verdict"] == "Weak"


def test_identical_input_gives_identical_hash_and_score(client, set_id, fake):
    add(client, set_id, "What is a primary key?", "SQL", "easy")
    scores, hashes = [], []
    for i in range(2):
        st = start_interview(client, set_id, max_followups=0, replace=bool(i))     # replacing ends the first one (its summary uses a model call)
        fake.chat_replies = [graded(7)]
        ev = answer(client, st, "It uniquely identifies each row").json()["current"]["thread"][0]["evaluation"]
        scores.append(ev["score"])
        hashes.append(ev["provenance"]["input_hash"])
    assert scores[0] == scores[1] and hashes[0] == hashes[1]


def test_repair_retry_then_success(client, set_id, fake):
    add(client, set_id, "What is a primary key?")
    fake.chat_replies = ["{broken", graded(7)]
    st = start_interview(client, set_id, max_followups=0)
    st = answer(client, st, "It identifies rows").json()
    assert st["phase"] == "feedback" and len(fake.chat_calls) == 2


def test_i_dont_know_is_capped_and_gets_no_followup(client, set_id, fake):
    add(client, set_id, "Explain the CAP theorem.")
    fake.chat_replies = [graded(6, correct=[], followup="Which two properties hold under partition?")]
    st = start_interview(client, set_id, max_followups=2)
    st = answer(client, st, "I don't know").json()
    ev = st["current"]["thread"][0]["evaluation"]
    assert ev["classification"] == "no_attempt" and ev["score"] <= 2 and ev["adjustments"] and st["next_action"] != "followup"


def test_unverified_misconception_is_not_counted_as_an_error(client, set_id, fake):
    add(client, set_id, "Explain indexes.", "SQL")
    fake.chat_replies = [graded(5, misconceptions=["Thinks indexes slow down reads"])]
    st = start_interview(client, set_id, max_followups=0)
    ev = answer(client, st, "Indexes speed up lookups on columns").json()["current"]["thread"][0]["evaluation"]
    assert ev["misconceptions"] == [] and ev["unverified_misconceptions"] == ["Thinks indexes slow down reads"]
    assert ev["classification"] != "incorrect"


def test_behavioural_interview_uses_the_behavioural_profile(client, set_id, fake):
    add(client, set_id, "Tell me about a time you handled conflict.")
    fake.chat_replies = [graded(7)]
    st = start_interview(client, set_id, max_followups=0, interview_type="hr")
    assert answer(client, st, "Situation, task, action, result").json()["current"]["thread"][0]["evaluation"]["profile"] == "behavioral"
    req = fake.chat_calls[0]
    assert "Behavioural" in req["messages"][0]["content"] and "edge_cases" not in req["format"]["properties"]["dimension_scores"]["properties"]


def test_report_intelligence_progress_and_learning_plan(client, set_id, fake):
    add(client, set_id, "What is a primary key?", "SQL", "easy")
    add(client, set_id, "How do generators work?", "Python", "hard")
    for i, (a, b) in enumerate([(4, 5), (8, 6)]):
        fake.chat_replies = [graded(a), graded(b)]
        st = start_interview(client, set_id, max_followups=0, replace=bool(i), feedback_mode="at_end")
        st = answer(client, st, "answer one").json()
        st = answer(client, st, "answer two").json()
    rep = client.get(f"/api/interviews/{st['id']}/report").json()
    intel = rep["intelligence"]
    assert {d["difficulty"] for d in intel["difficulty"]} == {"easy", "hard"}
    assert intel["conceptual_vs_practical"]["conceptual"] is not None
    assert {p["key"] for p in intel["profiles"]} == {"sql", "python"}
    sql = next(p for p in rep["progress"] if p["topic"] == "SQL")
    assert sql["previous"] == 4.0 and sql["delta"] == 4.0
    assert intel["learning_plan"] and all(p["action"] for p in intel["learning_plan"])
    md = client.get(f"/api/interviews/{st['id']}/report/export?format=md").text
    assert "## Assessment detail" in md and "Learning plan" in md


def test_redacted_export_removes_answers_quotes_and_usage(client, set_id, fake):
    add(client, set_id, "What is a primary key?")
    fake.chat_replies = [graded(7, evidence=[{"kind": "correct", "point": "x", "quote": "my secret answer text"}])]
    st = start_interview(client, set_id, max_followups=0, feedback_mode="at_end")
    st = answer(client, st, "my secret answer text here").json()
    full = client.get(f"/api/interviews/{st['id']}/report/export?format=json").text
    red = client.get(f"/api/interviews/{st['id']}/report/export?format=json&redact=true").text
    assert "my secret answer text" in full and "my secret answer text" not in red and json.loads(red)["redacted"] is True
    assert "my secret answer text" not in client.get(f"/api/interviews/{st['id']}/report/export?format=md&redact=true").text
    assert client.get(f"/api/interviews/{st['id']}/report/export?format=pdf&redact=true").status_code == 200


def test_the_share_safe_copy_has_a_plain_heading_not_a_repeated_one(client, set_id, fake):
    """Review round 1: the redacted Markdown began "# Interview report: Interview report"."""
    add(client, set_id, "What is a primary key?")
    fake.chat_replies = [graded(7)]
    st = start_interview(client, set_id, max_followups=0, feedback_mode="at_end", title="Acme final round")
    st = answer(client, st, "An identifier for a row.").json()
    md = client.get(f"/api/interviews/{st['id']}/report/export?format=md&redact=true").text
    assert md.startswith("# Interview report (share-safe copy)\n") and "Acme" not in md
    assert client.get(f"/api/interviews/{st['id']}/report/export?format=md").text.startswith("# Interview report: Acme final round\n")


def test_backup_is_a_consistent_sqlite_copy(client, set_id, tmp_path):
    add(client, set_id, "Backup me?")
    r = client.get("/api/backup")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    out = tmp_path / "b.sqlite3"
    out.write_bytes(r.content)
    with closing(sqlite3.connect(out)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM questions WHERE text='Backup me?'").fetchone()[0] == 1
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_backup_is_blocked_cross_site(client):
    assert client.get("/api/backup", headers={"host": "evil.example"}).status_code == 403


def test_profiles_endpoint(client):
    data = client.get("/api/evaluation/profiles").json()
    assert {"sql", "python", "data_engineering", "machine_learning", "system_design", "software_engineering", "behavioral", "general"} <= {p["key"] for p in data["profiles"]}


def test_old_evaluations_without_v6_fields_still_report(client, container, set_id, fake):
    add(client, set_id, "Legacy?")
    fake.chat_replies = [graded(7)]
    st = start_interview(client, set_id, max_followups=0, feedback_mode="at_end")
    st = answer(client, st, "x").json()
    with container.db.tx() as c:                    # strip the v6 fields as if the evaluation had been stored by v5
        row = c.execute("SELECT id, evaluation_json FROM turns").fetchone()
        ev = json.loads(row["evaluation_json"])
        for k in ("profile", "classification", "evidence", "weights", "provenance", "consistency_flags", "adjustments", "unverified_misconceptions"):
            ev.pop(k, None)
        c.execute("UPDATE turns SET evaluation_json=? WHERE id=?", (json.dumps(ev), row["id"]))
        c.execute("DELETE FROM reports")
        from app.services import reports
        reports.store_report(c, st["id"])
    rep = client.get(f"/api/interviews/{st['id']}/report").json()
    assert rep["summary"]["average_score"] == 7.0 and rep["intelligence"]["classifications"] == []


def test_redaction_is_an_allow_list_across_all_formats(client, container, fake):
    """Fable finding: model prose quotes the answer. A sentinel in the answer, the grader's text and the resume must vanish everywhere."""
    from intel_fixtures import ready_resume
    import pypdfium2 as pdfium
    S = "ZEBRASENTINEL"
    rid = ready_resume(container, name=f"{S}_CV")
    with container.db.tx() as c:
        c.execute("UPDATE resumes SET profile_json=replace(profile_json, 'Acme Corp', ?), raw_text=replace(raw_text, 'Acme Corp', ?)", (S, S))
    r = client.post("/api/interviews", json={"set_id": None, "config": {"include_bank": False, "max_followups": 1, "feedback_mode": "at_end"},
                                             "resume_auto": {"resume_id": rid, "count": 2}})
    st = r.json()
    leaky = graded(6, correct=[f"Mentioned {S} pipeline"], missing=[f"{S} detail"], misconceptions=[f"said {S}"],
                   followup=f"What about {S} retries?", extra={"verdict_summary": f"{S} answer", "uncertainty_note": S, "ideal_answer": S})
    fake.chat_replies = [leaky, graded(7), graded(7), {"overall_summary": S, "strengths": [S], "knowledge_gaps": [], "repeated_misconceptions": [],
                                                       "topics_to_revise": [], "recommendations": [S]}]
    for _ in range(3):
        if st["status"] != "in_progress":
            break
        st = answer(client, st, f"I built the {S} pipeline myself").json()
    iid = st["id"]
    full = client.get(f"/api/interviews/{iid}/report/export?format=json").text
    assert S in full
    for fmt in ("json", "md"):
        assert S not in client.get(f"/api/interviews/{iid}/report/export?format={fmt}&redact=true").text, fmt
    pdf = client.get(f"/api/interviews/{iid}/report/export?format=pdf&redact=true").content
    doc = pdfium.PdfDocument(pdf)
    text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert "Interview Report" in text and S not in text


def test_backup_never_uses_the_shared_temp_folder_and_cleans_leftovers(client, container):
    folder = container.settings.data_dir / "tmp"
    folder.mkdir(parents=True, exist_ok=True)
    stale, in_flight = folder / "interviewer-backup-old.sqlite3", folder / "interviewer-backup-now.sqlite3"
    stale.write_bytes(b"x")
    in_flight.write_bytes(b"y")                           # another download that is still being sent
    two_hours_ago = time.time() - 7200
    os.utime(stale, (two_hours_ago, two_hours_ago))
    assert client.get("/api/backup").status_code == 200
    assert not stale.exists() and list(folder.glob("interviewer-backup-*.sqlite3")) == [in_flight]


def test_a_resume_reference_answer_with_invented_figures_is_flagged_and_labelled_as_guidance(client, container, fake):
    """Real case (Groq, 18 Nov 2026): the reference answer to a resume question claimed "Latency is ~200-600 ms", which the candidate
    never said. The grader cannot know the project, so the app checks the figures and says so, in the app, the Markdown and the PDF."""
    import pypdfium2 as pdfium
    from intel_fixtures import ready_resume
    rid = ready_resume(container)
    st = client.post("/api/interviews", json={"set_id": None, "config": {"include_bank": False, "max_followups": 0, "feedback_mode": "at_end"},
                                              "resume_auto": {"resume_id": rid, "count": 2}}).json()
    fake.chat_replies = [graded(7, extra={"ideal_answer": "The pipeline ran on Airflow with latency of ~200-600 ms and 40% less runtime."}),
                         graded(7, extra={"ideal_answer": "A strong answer names your own part, the decision and how the 40% was measured."})]
    for _ in range(2):
        st = answer(client, st, "I owned the Airflow DAGs and cut runtime by 40% through partitioning").json()
    rep = client.get(f"/api/interviews/{st['id']}/report").json()
    flags = [[f["code"] for f in q["turns"][0]["evaluation"]["consistency_flags"]] for q in rep["questions"]]
    assert "reference_figures_unverified" in flags[0] and "reference_figures_unverified" not in flags[1]      # 40% was said; 200-600 was not
    msg = next(f["message"] for f in rep["questions"][0]["turns"][0]["evaluation"]["consistency_flags"] if f["code"] == "reference_figures_unverified")
    assert "200" in msg and "600" in msg and "40" not in msg
    md = client.get(f"/api/interviews/{st['id']}/report/export?format=md").text
    assert "What a strong answer covers" in md and "**Reference answer:**" not in md and "illustrations, not facts about your work" in md
    doc = pdfium.PdfDocument(client.get(f"/api/interviews/{st['id']}/report/export?format=pdf").content)
    text = " ".join(doc[i].get_textpage().get_text_range() for i in range(len(doc))).replace("\r\n", " ").replace("\n", " ")
    assert "What a strong answer covers" in text and "illustrations, not facts" in text


def test_a_bank_question_keeps_the_suggested_answer_heading_and_is_never_flagged_for_figures(client, set_id, fake):
    add(client, set_id, "How many bits are in a byte?")
    fake.chat_replies = [graded(8, extra={"ideal_answer": "A byte has 8 bits; a kibibyte is 1024 bytes."})]
    st = start_interview(client, set_id, max_followups=0, feedback_mode="at_end")
    st = answer(client, st, "eight bits").json()
    rep = client.get(f"/api/interviews/{st['id']}/report").json()
    assert not any(f["code"] == "reference_figures_unverified" for f in rep["questions"][0]["turns"][0]["evaluation"]["consistency_flags"])
    assert "**Suggested answer (written by the AI)" in client.get(f"/api/interviews/{st['id']}/report/export?format=md").text


def test_share_safe_export_hides_resume_topics_the_title_and_exact_times(client, container, set_id, fake):
    """Security audit, Nov 2026: a resume question's topic (often a project or employer name), the interview title and exact
    timestamps survived redaction through `topics`, `progress`, the PDF title and the file name."""
    import pypdfium2 as pdfium
    from intel_fixtures import ready_resume
    TOPIC, TITLE = "ZEBRATOPIC payments ledger", "ZEBRATITLE final round"
    rid = ready_resume(container)
    add(client, set_id, "What is a primary key?", "SQL", "easy")
    rq = {"text": "How did the ledger reconcile payments?", "topic": TOPIC, "difficulty": "medium", "resume_id": rid, "resume_name": "Resume 1",
          "claim": {"section": "Projects", "label": "Ledger", "excerpt": "Built a payments ledger."}}
    for _round in range(2):                                   # twice, so "progress since last attempt" exists for both topics
        fake.chat_replies = [graded(4), graded(8)]
        r = client.post("/api/interviews", json={"set_id": set_id, "config": {"title": TITLE, "max_followups": 0, "feedback_mode": "at_end"},
                                                 "resume_questions": [rq]})
        assert r.status_code == 201, r.text
        st = r.json()
        for _ in range(2):
            st = answer(client, st, "An answer").json()
    iid = st["id"]
    full = client.get(f"/api/interviews/{iid}/report/export?format=json").json()
    assert any(t["topic"] == TOPIC for t in full["topics"]) and any(p["topic"] == TOPIC for p in full["progress"])       # present before redaction
    red = client.get(f"/api/interviews/{iid}/report/export?format=json&redact=true")
    data = red.json()
    assert "ZEBRA" not in red.text
    assert {t["topic"] for t in data["topics"]} == {"SQL", "Resume"} and [p["topic"] for p in data["progress"]] == ["SQL"]
    assert data["interview"]["title"] == "Interview report" and len(data["interview"]["created_at"]) == 10                 # the day only
    assert "ZEBRA" not in client.get(f"/api/interviews/{iid}/report/export?format=md&redact=true").text
    pdf = client.get(f"/api/interviews/{iid}/report/export?format=pdf&redact=true")
    assert "zebra" not in pdf.headers["content-disposition"].lower()
    assert b"ZEBRA" not in pdf.content and b"/CreationDate (D:2026" not in pdf.content                                     # no title, no real creation time
    doc = pdfium.PdfDocument(pdf.content)
    assert "ZEBRA" not in "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
