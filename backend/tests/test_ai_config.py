"""Settings -> AI models: local by default, cloud only with a key AND consent, and the key is write-only."""
from contextlib import closing
import os
import sqlite3
import sys

import pytest

from conftest import CLOUD_KEY, enable_cloud

SECRET = CLOUD_KEY


def test_defaults_are_local_and_private(cloud_client):
    d = cloud_client.get("/api/ai").json()
    assert d["mode"] == "local" and d["ready"] is True
    cfg = d["config"]
    assert (cfg["grader_model"], cfg["fallback_model"], cfg["conversation_model"]) == ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "openai/gpt-oss-20b")
    assert cfg["cloud_consent_at"] is None and cfg["fallback_to_local"] is False and cfg["use_fallback"] is True
    assert cfg["enforce_budget"] is True and cfg["daily_budget_usd"] == 1.0 and cfg["total_budget_usd"] is None
    assert d["key"] == {"set": False, "source": None, "hint": None}
    assert "Your answers (typed, or the text of what you said)" in d["sent_to_cloud"] and "Your voice recordings and the speech-to-text" in d["stays_local"]
    prov = d["provider"]                                       # who receives the text, where to get a key, and how long it may be kept
    assert prov["name"] == "Groq" and prov["keys_url"] == "https://console.groq.com/keys" and "30 days" in prov["retention"]


def test_the_api_key_is_write_only(cloud_client):
    r = cloud_client.put("/api/ai/key", json={"api_key": SECRET})
    assert r.status_code == 200 and r.json()["key"] == {"set": True, "source": "saved", "hint": "••••abcd"}
    for path in ("/api/ai", "/api/health", "/api/usage"):
        assert SECRET not in cloud_client.get(path).text, path
    assert SECRET not in r.text


@pytest.mark.parametrize("bad", ["", "short", "has a space in it 12345", "line\nbreak123456789", "x" * 600, "\u0007control-char-key-123"])
def test_obviously_wrong_keys_are_rejected(cloud_client, bad):
    r = cloud_client.put("/api/ai/key", json={"api_key": bad})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_key"
    assert cloud_client.get("/api/ai").json()["key"]["set"] is False


def test_a_pasted_bearer_prefix_is_removed(cloud_client):
    cloud_client.put("/api/ai/key", json={"api_key": f"  Bearer {SECRET}  "})
    assert cloud_client.get("/api/ai").json()["key"]["hint"] == "••••abcd"


def test_cloud_cannot_be_switched_on_without_a_key_or_without_consent(cloud_client):
    r = cloud_client.put("/api/ai", json={"mode": "cloud", "acknowledge_cloud": True})
    assert r.status_code == 422 and r.json()["error"]["code"] == "key_required"
    cloud_client.put("/api/ai/key", json={"api_key": SECRET})
    r = cloud_client.put("/api/ai", json={"mode": "cloud"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "consent_required"
    assert cloud_client.get("/api/ai").json()["mode"] == "local"                       # still local after both refusals


def test_consent_is_recorded_once_and_switching_back_to_local_is_always_allowed(cloud_client):
    d = enable_cloud(cloud_client)
    first = d["config"]["cloud_consent_at"]
    assert d["mode"] == "cloud" and first
    assert cloud_client.put("/api/ai", json={"mode": "local"}).json()["mode"] == "local"
    again = cloud_client.put("/api/ai", json={"mode": "cloud"}).json()                 # consent is remembered; no second prompt needed
    assert again["mode"] == "cloud" and again["config"]["cloud_consent_at"] == first


def test_removing_the_key_while_in_cloud_mode_returns_to_local(cloud_client):
    enable_cloud(cloud_client)
    d = cloud_client.delete("/api/ai/key").json()
    assert d["mode"] == "local" and d["key"]["set"] is False                           # never stay in a mode that cannot work


def test_a_key_from_the_environment_wins_and_cannot_be_removed_from_the_page(cloud_client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "env-key-abcdefghij1234")
    d = cloud_client.get("/api/ai").json()
    assert d["key"] == {"set": True, "source": "environment", "hint": "••••1234"}
    assert "env-key-abcdefghij1234" not in cloud_client.get("/api/ai").text
    assert cloud_client.delete("/api/ai/key").json()["key"]["source"] == "environment"
    cloud_client.put("/api/ai", json={"mode": "cloud", "acknowledge_cloud": True})      # the env key alone is enough to enable it
    assert cloud_client.get("/api/ai").json()["mode"] == "cloud"


def test_models_budgets_and_prices_are_validated_and_saved(cloud_client):
    d = cloud_client.put("/api/ai", json={"grader_model": "openai/gpt-oss-20b", "fallback_model": "openai/gpt-oss-120b", "conversation_model": "my-org/custom-model:v2",
                                           "daily_budget_usd": 2.5, "total_budget_usd": 20, "use_fallback": False, "fallback_to_local": True}).json()["config"]
    assert (d["grader_model"], d["fallback_model"], d["daily_budget_usd"], d["total_budget_usd"], d["use_fallback"], d["fallback_to_local"]) == \
           ("openai/gpt-oss-20b", "openai/gpt-oss-120b", 2.5, 20.0, False, True)
    for bad in ({"grader_model": "bad name!"}, {"grader_model": ""}, {"conversation_model": "x" * 100}, {"daily_budget_usd": -1}, {"total_budget_usd": 1e9}):
        r = cloud_client.put("/api/ai", json=bad)
        assert r.status_code == 422, bad
    assert cloud_client.get("/api/ai").json()["config"]["grader_model"] == "openai/gpt-oss-20b"     # rejected updates change nothing
    assert cloud_client.get("/api/ai").json()["config"]["conversation_model"] == "my-org/custom-model:v2"   # custom model ids stay allowed


def test_budgets_can_be_removed(cloud_client):
    cloud_client.put("/api/ai", json={"total_budget_usd": 5})
    d = cloud_client.put("/api/ai", json={"clear_daily_budget": True, "clear_total_budget": True}).json()["config"]
    assert d["daily_budget_usd"] is None and d["total_budget_usd"] is None


def test_prices_can_be_edited_for_models_the_app_does_not_know(cloud_client):
    d = cloud_client.put("/api/ai", json={"prices": {"kimi-k3": {"input_per_m": 0.5, "output_per_m": 2.0}, "openai/gpt-oss-120b": {"input_per_m": 0.2, "output_per_m": 0.7}}}).json()["config"]
    assert d["prices"]["kimi-k3"]["output_per_m"] == 2.0 and d["prices"]["openai/gpt-oss-120b"]["input_per_m"] == 0.2
    assert cloud_client.put("/api/ai", json={"prices": {"bad name!": {"input_per_m": 1, "output_per_m": 1}}}).status_code == 422
    assert cloud_client.put("/api/ai", json={"prices": {"x": {"input_per_m": -1, "output_per_m": 1}}}).status_code == 422


def test_a_damaged_setting_falls_back_to_the_safe_local_default(cloud_client, tmp_path):
    from app.main import create_app  # noqa: F401  (the app is already running; corrupt the stored value directly)
    db = cloud_client.app.state.c.db
    with db.tx() as c:
        c.execute("INSERT INTO settings(key,value) VALUES('ai_config','{not json') ON CONFLICT(key) DO UPDATE SET value=excluded.value")
    d = cloud_client.get("/api/ai").json()
    assert d["mode"] == "local" and d["config"]["grader_model"] == "openai/gpt-oss-120b"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file permissions")
def test_the_data_folder_and_database_are_private_to_this_user(cloud_client):
    s = cloud_client.app.state.c.settings
    assert oct(os.stat(s.data_dir).st_mode & 0o777) == "0o700"
    assert oct(os.stat(s.db_path).st_mode & 0o777) == "0o600"


def test_the_key_lives_only_in_the_settings_table(cloud_client):
    cloud_client.put("/api/ai/key", json={"api_key": SECRET})
    db_path = cloud_client.app.state.c.settings.db_path
    hits = []
    with closing(sqlite3.connect(db_path)) as raw:
        for (table,) in raw.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            for row in raw.execute(f"SELECT * FROM {table}"):
                if SECRET in " ".join(str(v) for v in row):
                    hits.append(table)
    assert hits == ["settings"]


def test_defaults_are_not_stored_so_an_improved_price_list_reaches_existing_installs(cloud_client):
    import json
    store = cloud_client.app.state.c.ai
    from app.services.pricing import DEFAULT_PRICES
    assert set(store.get().prices) == set(DEFAULT_PRICES)                        # every published model is priced out of the box
    cloud_client.put("/api/ai", json={"daily_budget_usd": 2})
    cloud_client.put("/api/ai", json={"prices": {"kimi-k3": {"input_per_m": 1.0, "output_per_m": 5.0}, "acme-1": {"input_per_m": 2.0, "output_per_m": 3.0}}})
    p = store.get().prices
    assert p["kimi-k3"].output_per_m == 5.0 and p["acme-1"].input_per_m == 2.0 and p["openai/gpt-oss-120b"].output_per_m == 0.60
    with store.db.tx() as c:
        stored = json.loads(c.execute("SELECT value FROM settings WHERE key='ai_config'").fetchone()[0])["prices"]
    assert set(stored) == {"kimi-k3", "acme-1"}                                  # only the user's own edits are saved
    with store.db.tx() as c:                                                      # an older install that saved the whole old default list
        old = json.loads(c.execute("SELECT value FROM settings WHERE key='ai_config'").fetchone()[0])
        old["prices"] = {"openai/gpt-oss-120b": {"input_per_m": 0.15, "output_per_m": 0.6, "offpeak_input_per_m": None, "offpeak_output_per_m": None}}
        c.execute("UPDATE settings SET value=? WHERE key='ai_config'", (json.dumps(old),))
    assert store.get().prices["openai/gpt-oss-20b"].input_per_m == 0.075           # defaults missing from an old save appear on read


def test_an_old_ollama_key_in_the_environment_is_ignored(cloud_client, monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "old-ollama-key-abcdefgh1234")
    d = cloud_client.get("/api/ai").json()
    assert d["key"] == {"set": False, "source": None, "hint": None}
    assert cloud_client.put("/api/ai", json={"mode": "cloud", "acknowledge_cloud": True}).status_code == 422       # no Groq key: cloud stays off


# ---------------------------------------------------------------- upgrade from the Ollama-cloud version
OLD_KEY = "ollama-cloud-key-abcdef123456"


def _old_install(tmp_path):
    """A database exactly as the Ollama-cloud version left it: cloud mode on, consent given, key saved, a resume consented."""
    import json
    from app.db import Database
    db = Database(tmp_path / "data" / "interviewer.sqlite3")
    cfg = {"mode": "cloud", "cloud_consent_at": "2026-10-31T19:11:36+00:00", "grader_model": "gpt-oss:120b", "fallback_model": "deepseek-v4.1-flash",
           "use_fallback": False, "conversation_model": "gemma4:31b", "fallback_to_local": True, "enforce_budget": True, "daily_budget_usd": 0.5,
           "total_budget_usd": 7.0, "prices": {"gemma4:31b": {"input_per_m": 9, "output_per_m": 9, "offpeak_input_per_m": None, "offpeak_output_per_m": None}}}
    now = "2026-11-01T10:00:00+00:00"
    with db.tx() as c:
        for k, v in (("ai_config", json.dumps(cfg)), ("ai_cloud_key", OLD_KEY), ("ai_last_test", json.dumps({"ok": True, "models": ["gpt-oss:120b"]}))):
            c.execute("INSERT INTO settings(key,value) VALUES(?,?)", (k, v))
        for i, consent in enumerate((1, 0, None)):
            c.execute("""INSERT INTO resumes(name, original_filename, stored_name, sha256, size_bytes, pages, status, consent_cloud, created_at, updated_at)
                         VALUES (?,?,?,?,?,?,'ready',?,?,?)""", (f"R{i}", "cv.pdf", f"s{i}.pdf", f"h{i}", 10, 1, consent, now, now))
        c.execute("INSERT INTO llm_usage(created_at, model, purpose, provider, cost_usd) VALUES (?, 'gpt-oss:120b', 'evaluation', 'cloud', 0.0004)", (now,))
    return db


def test_upgrading_from_ollama_cloud_returns_to_local_and_forgets_the_old_key_and_every_consent(tmp_path, fake):
    from app.deps import build_container
    from app.main import create_app
    from conftest import InlineExecutor, make_client_for, make_settings
    from fastapi.testclient import TestClient
    _old_install(tmp_path)
    s = make_settings(tmp_path)
    c = build_container(s, ollama=make_client_for(s, fake), executor=InlineExecutor())          # first start after the upgrade
    client = TestClient(create_app(s, c), base_url="http://127.0.0.1:3000")
    d = client.get("/api/ai").json()
    cfg = d["config"]
    assert d["mode"] == "local" and cfg["cloud_consent_at"] is None and d["key"] == {"set": False, "source": None, "hint": None}
    assert (cfg["grader_model"], cfg["fallback_model"], cfg["conversation_model"]) == ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "openai/gpt-oss-20b")
    assert d["last_test"] is None and "gemma4:31b" not in cfg["prices"]
    assert (cfg["daily_budget_usd"], cfg["total_budget_usd"], cfg["use_fallback"], cfg["fallback_to_local"]) == (0.5, 7.0, False, True)   # the user's limits are kept
    with c.db.read() as conn:
        assert OLD_KEY not in " ".join(str(v) for row in conn.execute("SELECT * FROM settings") for v in row)       # the key is gone from the database
        assert [r[0] for r in conn.execute("SELECT consent_cloud FROM resumes ORDER BY id")] == [None, None, None]  # each resume must be agreed to again
        assert conn.execute("SELECT COUNT(*) FROM llm_usage WHERE provider='cloud'").fetchone()[0] == 1              # history is kept
    assert OLD_KEY not in client.get("/api/ai").text and OLD_KEY not in client.get("/api/health").text
    # cloud mode cannot come back without a NEW key and a NEW consent
    assert client.put("/api/ai", json={"mode": "cloud"}).status_code == 422
    assert client.put("/api/ai", json={"mode": "cloud", "acknowledge_cloud": True}).json()["error"]["code"] == "key_required"


def test_the_migration_runs_once_and_never_touches_a_groq_setup(tmp_path, fake):
    from app.deps import build_container
    from app.services.ai_config import AIConfigStore
    from conftest import InlineExecutor, make_client_for, make_settings
    db = _old_install(tmp_path)
    assert AIConfigStore(db).migrate_provider() is False                             # the constructor already migrated; a second run is a no-op
    store = AIConfigStore(db)
    store.set_key("gsk_new_key_abcdefgh12345678")
    from app.services.ai_config import AIConfigUpdate
    store.update(AIConfigUpdate(mode="cloud", acknowledge_cloud=True))
    with db.tx() as c:
        c.execute("UPDATE resumes SET consent_cloud=1 WHERE id=1")
    s = make_settings(tmp_path)
    c2 = build_container(s, ollama=make_client_for(s, fake), executor=InlineExecutor())      # a later restart
    assert c2.ai.get().mode == "cloud" and c2.ai.api_key() == "gsk_new_key_abcdefgh12345678" and c2.ai.get().cloud_consent_at
    with c2.db.read() as conn:
        assert conn.execute("SELECT consent_cloud FROM resumes WHERE id=1").fetchone()[0] == 1


def test_a_fresh_install_and_a_damaged_old_setting_both_migrate_cleanly(tmp_path):
    from app.db import Database
    from app.services.ai_config import AIConfigStore
    fresh = Database(tmp_path / "a.sqlite3")
    assert AIConfigStore(fresh).migrate_provider() is False and AIConfigStore(fresh).get().mode == "local"
    damaged = Database(tmp_path / "b.sqlite3")
    with damaged.tx() as c:
        c.execute("INSERT INTO settings(key,value) VALUES('ai_config','{not json')")
        c.execute("INSERT INTO settings(key,value) VALUES('ai_cloud_key', ?)", (OLD_KEY,))
    store = AIConfigStore(damaged)
    assert store.get().mode == "local" and store.api_key() is None


def test_a_custom_cloud_address_is_named_instead_of_being_presented_as_groq():
    """Security audit, Nov 2026: with GROQ_BASE_URL set, the screen still said the text goes to Groq."""
    from app.config import CLOUD_API_URL
    from app.routers.ai import _custom_host
    assert _custom_host(CLOUD_API_URL) is None and _custom_host(CLOUD_API_URL + "/") is None
    assert _custom_host("https://llm.example.test:8443/v1") == "llm.example.test:8443"
