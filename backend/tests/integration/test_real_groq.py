"""Real Groq API checks. Opt-in: they run ONLY when GROQ_API_KEY is set in the environment, and are skipped otherwise.

    GROQ_API_KEY=gsk_... backend/.venv/bin/python -m pytest -m integration -s backend/tests/integration/test_real_groq.py

They use your key and a few hundred tokens of your Groq allowance (four small requests). They verify the things the mocked tests
cannot: that the documented streaming format, the usage block and the reasoning switches really behave as the client assumes.
The key is never printed.
"""
import json
import os

import pytest

from app.config import Settings
from app.services.cloud import CloudClient
from app.services.ollama import LLMError
from app.services.pricing import GRADER_MODEL, SMALL_MODEL

pytestmark = pytest.mark.integration
SCHEMA = {"type": "object", "properties": {"capital": {"type": "string"}, "country": {"type": "string"}}, "required": ["capital", "country"]}
MESSAGES = [{"role": "system", "content": "You answer geography questions."}, {"role": "user", "content": "Which city is the capital of France?"}]


@pytest.fixture(scope="module")
def groq(tmp_path_factory):
    key = (os.environ.get("GROQ_API_KEY") or "").strip()
    if not key:
        pytest.skip("set GROQ_API_KEY to run the real Groq tests")
    client = CloudClient(Settings(data_dir=tmp_path_factory.mktemp("groq")), key=lambda: key)
    client.seen = []
    client.on_usage = client.seen.append
    return client


def _skip_if_limited(e: LLMError) -> None:
    if e.code == "rate_limited":               # the free plan's allowance is used up right now: not a failure of the code
        pytest.skip(f"Groq rate limit reached: {e.message}")
    raise e


def test_the_key_works_and_both_default_models_are_listed(groq):
    try:
        models = groq.list_models()
    except LLMError as e:
        _skip_if_limited(e)
    assert GRADER_MODEL in models and SMALL_MODEL in models, f"default models missing from this key's list: {models}"


@pytest.mark.parametrize("model", [GRADER_MODEL, SMALL_MODEL])
def test_a_streamed_reply_is_valid_json_with_usage_and_no_reasoning_text(groq, model):
    groq.seen.clear()
    try:
        text = groq.chat_json(MESSAGES, SCHEMA, model=model, max_tokens=300, purpose="integration")
    except LLMError as e:
        _skip_if_limited(e)
    data = json.loads(text)                                         # only the answer came back: no reasoning text, no markdown fence
    assert "paris" in data["capital"].lower() and data["country"]
    assert len(groq.seen) == 1, "exactly one usage record per reply"
    u = groq.seen[0]
    assert u["provider"] == "cloud" and u["model"] == model
    assert isinstance(u["prompt_tokens"], int) and u["prompt_tokens"] > 20, "the stream did not report prompt tokens (usage location changed?)"
    assert isinstance(u["output_tokens"], int) and u["output_tokens"] > 0
    assert u["total_ms"] > 0, "the stream did not report timings"
    assert not groq._no_reasoning, "Groq rejected the reasoning switches (reasoning_effort / include_reasoning)"


def test_the_tiny_test_message_answers(groq):
    try:
        out = groq.tiny_message(GRADER_MODEL)
    except LLMError as e:
        _skip_if_limited(e)
    assert "ok" in out["text"].lower() and out["prompt_tokens"] and out["output_tokens"]


def test_a_wrong_key_is_reported_as_a_key_problem(tmp_path):
    if not (os.environ.get("GROQ_API_KEY") or "").strip():
        pytest.skip("set GROQ_API_KEY to run the real Groq tests")
    bad = CloudClient(Settings(data_dir=tmp_path), key=lambda: "gsk_this_key_is_deliberately_invalid_0000")
    with pytest.raises(LLMError) as e:
        bad.list_models()
    assert e.value.code == "auth_failed" and "gsk_this_key" not in e.value.message
