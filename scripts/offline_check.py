"""Offline check (macOS): does a whole interview work with NO network except this computer's own loopback?

The backend is started inside a macOS sandbox that refuses every outbound connection that is not to localhost, then a short interview
runs through the HTTP API with the real local model: questions, an answer, the grading, a follow-up when the model asks one, spoken
question audio, the report and its PDF. While it runs, the backend's open network connections are sampled every second.

    python3 scripts/offline_check.py            # needs backend/.venv (./start.sh once), Ollama running, qwen3.5:4b installed

It never touches your data: the backend gets a throw-away data folder and a free port. Linux/Windows: not supported (no equivalent
sandbox without root); the test suite's loopback-only checks (backend/tests/test_local_only.py) run everywhere.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PY = ROOT / "backend" / ".venv" / "bin" / "python"
# Everything allowed except outbound network; then outbound to loopback (Ollama, our own port) and local Unix sockets allowed again.
PROFILE = ('(version 1)(allow default)(deny network-outbound)'
           '(allow network-outbound (remote ip "localhost:*"))(allow network-outbound (remote unix-socket))')


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    if sys.platform != "darwin":
        print("This check uses the macOS sandbox (sandbox-exec); it does not run on this system.")
        return 2
    if not VENV_PY.exists():
        print("backend/.venv is missing: run ./start.sh once first.")
        return 2
    port, data = free_port(), tempfile.mkdtemp(prefix="lai-offline-")
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "DATA_DIR": data, "APP_PORT": str(port), "HF_HUB_OFFLINE": "1", "LLM_UNLOAD_WHEN_IDLE": "0"}
    env.pop("GROQ_API_KEY", None)
    proc = subprocess.Popen(["sandbox-exec", "-p", PROFILE, str(VENV_PY), "-m", "uvicorn", "app.main:app_factory", "--factory",
                             "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                            cwd=ROOT / "backend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    remotes: set[str] = set()
    stop = threading.Event()

    def sample() -> None:                 # every remote address the backend process has a connection to
        while not stop.is_set():
            out = subprocess.run(["lsof", "-nP", "-a", "-p", str(proc.pid), "-i"], capture_output=True, text=True).stdout
            for line in out.splitlines()[1:]:
                if "->" in line:
                    remotes.add(line.split("->", 1)[1].split()[0].rsplit(":", 1)[0])
            stop.wait(1.0)

    def call(method: str, path: str, body=None, raw: bool = False):
        req = urllib.request.Request(base + path, method=method, headers={"Content-Type": "application/json"},
                                     data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req, timeout=600) as r:
            data_ = r.read()
            return data_ if raw else json.loads(data_ or b"null")

    results: list[tuple[bool, str]] = []
    check = lambda ok, what: (results.append((bool(ok), what)), print(f"{'PASS' if ok else 'FAIL'}  {what}", flush=True))
    try:
        for _ in range(60):
            try:
                health = call("GET", "/api/health")
                break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.5)
        else:
            print("backend did not start:\n" + proc.stderr.read().decode(errors="replace") if proc.poll() is not None else "backend did not start")
            return 1
        threading.Thread(target=sample, daemon=True).start()
        check(health["local_only"] and health["ollama"]["ok"] and health["llm"]["installed"], "backend up inside the no-network sandbox; Ollama reachable on loopback")
        check(subprocess.run(["sandbox-exec", "-p", PROFILE, "/usr/bin/curl", "-s", "-m", "5", "-o", "/dev/null", "https://pypi.org/"]).returncode != 0,
              "the sandbox really blocks the internet (curl to pypi.org inside it fails)")

        st = call("POST", "/api/sets", {"name": "Offline check"})
        for q in ("What is idempotency in an ETL pipeline and how do you achieve it?", "What is the difference between a process and a thread?"):
            call("POST", f"/api/sets/{st['id']}/questions", {"text": q, "topic": "Offline"})
        iv = call("POST", "/api/interviews", {"set_id": st["id"], "config": {"title": "Offline check", "max_followups": 1, "feedback_mode": "at_end", "question_audio": "manual"}})
        iid, answers = iv["id"], ["It means rerunning the job does not create duplicates. I upsert rows on the business key.",
                                  "A process has its own memory; threads in a process share it, so they are cheaper but need locks."]
        wav = call("POST", "/api/speech/synthesize", {"text": iv["current"]["turn"]["question_text"], "voice": "default"}, raw=True)
        check(wav[:4] == b"RIFF" and len(wav) > 10_000, f"question read aloud by the local voice ({len(wav) // 1024} KB of audio)")
        graded = followups = 0
        while iv["phase"] != "done":
            turn = iv["current"]["turn"]
            text = answers.pop(0) if turn["kind"] == "main" else "With MERGE on the key and a watermark of processed batches."
            followups += turn["kind"] == "followup"
            iv = call("POST", f"/api/interviews/{iid}/answer", {"turn_id": iv["current_turn_id"], "text": text})
            while iv["phase"] == "evaluating":
                time.sleep(2)
                iv = call("GET", f"/api/interviews/{iid}")
            if iv["phase"] == "evaluation_failed":
                check(False, f"grading failed: {iv['error']}")
                return 1
            graded += 1
        check(graded >= 2, f"{graded} answers graded by the local model ({followups} follow-up)")
        for _ in range(150):
            rep = call("GET", f"/api/interviews/{iid}/report")
            if rep.get("narrative_status") != "pending":
                break
            time.sleep(2)
        check(rep["summary"]["scored"] == 2 and rep["narrative_status"] == "ready", f"report with scores and a written summary (average {rep['summary']['average_score']})")
        pdf = call("GET", f"/api/interviews/{iid}/report/export?format=pdf", raw=True)
        check(pdf[:5] == b"%PDF-", f"PDF export ({len(pdf) // 1024} KB)")
    finally:
        stop.set()
        proc.terminate()
        proc.wait(10)
    outside = sorted(r for r in remotes if r not in ("127.0.0.1", "[::1]", "localhost"))
    check(not outside, f"connections seen from the backend: {sorted(remotes) or 'none'}" + (f"; NOT loopback: {outside}" if outside else " (loopback only)"))
    failed = sum(not ok for ok, _ in results)
    print(f"{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
