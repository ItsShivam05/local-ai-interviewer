"""The Groq cloud client against a mock of the documented API: what it sends, how it reads replies, how it reports problems."""
import json

import httpx
import pytest

from app.services.cloud import api_name, consume_sse, humanise, parse_duration, with_schema
from app.services.ollama import LLMError
from conftest import make_settings
from fakecloud import CHAT_PATH, GRADER, KEY, MODELS_PATH, SMALL, FakeCloud, RateLimited, make_cloud

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
MSGS = [{"role": "system", "content": "You are a grader."}, {"role": "user", "content": "grade this"}]
BASE = "https://api.groq.com/openai/v1"


@pytest.fixture
def pair(tmp_path):
    fake = FakeCloud()
    return fake, make_cloud(make_settings(tmp_path), fake)


def chat(client, model=GRADER, **kw):
    return client.chat_json(MSGS, SCHEMA, model=model, **kw)


def raw_stream(client, content: bytes, status: int = 200, headers=None):
    """Point the client at a server that answers every request with exactly these bytes."""
    client.http = httpx.Client(base_url=BASE, transport=httpx.MockTransport(lambda r: httpx.Response(status, content=content, headers=headers or {})))


# ---------------------------------------------------------------- what is sent
def test_request_goes_to_groqs_chat_completions_endpoint_with_a_bearer_key(pair):
    fake, client = pair
    chat(client)
    req = fake.chats[0]
    assert req["method"] == "POST" and req["host"] == "api.groq.com" and req["path"] == CHAT_PATH == "/openai/v1/chat/completions"
    assert req["headers"]["authorization"] == f"Bearer {KEY}"
    assert len(fake.chats) == 1 and fake.model_list_calls == []                  # exactly one request, no hidden extras


def test_the_schema_goes_in_the_prompt_and_native_structured_outputs_are_not_requested(pair):
    fake, client = pair
    chat(client)
    body = fake.chats[0]["json"]
    assert "response_format" not in body and "format" not in body                # Groq's json_schema mode cannot be streamed
    system = body["messages"][0]["content"]
    assert system.startswith("You are a grader.") and "OUTPUT FORMAT" in system and '"required":["ok"]' in system
    assert body["messages"][1] == MSGS[1] and body["stream"] is True and body["stream_options"] == {"include_usage": True}


def test_only_documented_openai_compatible_fields_are_sent(pair):
    fake, client = pair
    chat(client)
    body = fake.chats[0]["json"]
    assert set(body) == {"model", "messages", "stream", "stream_options", "temperature", "max_completion_tokens", "reasoning_effort", "include_reasoning"}
    assert "options" not in body and "think" not in body and "max_tokens" not in body       # nothing left of the Ollama dialect
    assert all(set(m) == {"role", "content"} for m in body["messages"])                       # messages[].name would be a 400 on Groq


def test_the_schema_is_added_even_when_there_is_no_system_message():
    out = with_schema([{"role": "user", "content": "hi"}], SCHEMA)
    assert out[0]["role"] == "system" and "OUTPUT FORMAT" in out[0]["content"] and out[1]["content"] == "hi"


@pytest.mark.parametrize("given, sent", [(GRADER, GRADER), ("gpt-oss-120b", GRADER), ("GPT-OSS-20b", SMALL), ("qwen/qwen3.8-27b", "qwen/qwen3.8-27b"),
                                         ("My-Org/Custom-Model", "My-Org/Custom-Model"), ("llama-3.3-70b-versatile", "llama-3.3-70b-versatile")])
def test_model_ids_are_sent_as_groq_expects(pair, given, sent):
    fake, client = pair
    chat(client, model=given)
    assert fake.chats[0]["json"]["model"] == sent == api_name(given)


def test_reasoning_is_low_and_hidden_for_gpt_oss_and_not_sent_for_other_models(pair):
    fake, client = pair
    chat(client, model=GRADER)
    chat(client, model="llama-3.3-70b-versatile")
    a, b = fake.chats[0]["json"], fake.chats[1]["json"]
    assert a["reasoning_effort"] == "low" and a["include_reasoning"] is False
    assert "reasoning_effort" not in b and "include_reasoning" not in b and "reasoning_format" not in b


@pytest.mark.parametrize("effort", ["low", "medium", "high"])
def test_reasoning_effort_is_configurable(tmp_path, monkeypatch, effort):
    from app.config import Settings
    monkeypatch.setenv("CLOUD_REASONING_EFFORT", effort)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings.from_env()
    fake = FakeCloud()
    chat(make_cloud(settings, fake))
    assert fake.chats[0]["json"]["reasoning_effort"] == effort


def test_an_invalid_reasoning_effort_stops_the_app_with_a_clear_message(monkeypatch):
    from app.config import Settings
    monkeypatch.setenv("CLOUD_REASONING_EFFORT", "extreme")
    with pytest.raises(RuntimeError, match="CLOUD_REASONING_EFFORT"):
        Settings.from_env()


def test_the_output_cap_leaves_room_for_reasoning_but_is_bounded(pair):
    fake, client = pair
    chat(client)                                                                  # no caller cap
    chat(client, max_tokens=300)                                                  # small caller cap (e.g. a follow-up question)
    chat(client, max_tokens=50_000)                                               # absurd caller cap
    assert [r["json"]["max_completion_tokens"] for r in fake.chats] == [1500, 1500, 3000]


def test_a_model_that_rejects_the_reasoning_switches_is_retried_once_without_them_and_remembered(pair):
    fake, client = pair
    model = "gpt-oss-custom"
    fake.replies = [(400, "`reasoning_effort` is not supported with this model")]
    chat(client, model=model)
    assert [("reasoning_effort" in r["json"]) for r in fake.chats] == [True, False]      # one retry, without the switches
    chat(client, model=model)
    assert "reasoning_effort" not in fake.chats[-1]["json"] and len(fake.chats) == 3     # remembered: no more wasted attempts


# ---------------------------------------------------------------- what comes back
def test_the_answer_is_returned_and_reasoning_text_is_ignored(pair):
    fake, client = pair
    fake.replies = [{"ok": True, "n": 1}]
    assert fake.reasoning_in_stream and json.loads(chat(client)) == {"ok": True, "n": 1}


@pytest.mark.parametrize("where", ["usage", "x_groq"])
def test_tokens_and_timings_are_reported_as_a_cloud_call_wherever_the_stream_puts_them(pair, where):
    fake, client = pair
    fake.usage_in = where
    seen = []
    client.on_usage = seen.append
    chat(client, purpose="evaluation")
    assert seen == [{"model": GRADER, "purpose": "evaluation", "provider": "cloud", "prompt_tokens": 900, "output_tokens": 450,
                     "load_ms": 0, "prompt_ms": 300, "output_ms": 9000, "total_ms": 9300}]


def test_a_stream_without_usage_still_returns_the_answer_and_records_unknown_tokens(pair):
    fake, client = pair
    fake.usage_in = None
    seen = []
    client.on_usage = seen.append
    assert json.loads(chat(client)) == {"ok": True}
    assert seen[0]["prompt_tokens"] is None and seen[0]["output_tokens"] is None and seen[0]["provider"] == "cloud"


def test_the_event_stream_parser_handles_comments_keepalives_and_crlf(pair):
    fake, client = pair
    body = (b": keep-alive\r\n\r\n"
            b'event: message\r\ndata: {"choices":[{"delta":{"role":"assistant"}}]}\r\n\r\n'
            b'data: {"choices":[{"delta":{"reasoning":"hmm"}}]}\r\n\r\n'
            b'data:{"choices":[{"delta":{"content":"{\\"ok\\":"}}]}\r\n\r\n'
            b'data: {"choices":[{"delta":{"content":" true}"}}]}\r\n\r\n'
            b'data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":3}}\r\n\r\n'
            b"data: [DONE]\r\n\r\n"
            b'data: {"choices":[{"delta":{"content":"IGNORED AFTER DONE"}}]}\r\n\r\n')
    raw_stream(client, body)
    seen = []
    client.on_usage = seen.append
    assert json.loads(chat(client)) == {"ok": True}
    assert seen[0]["prompt_tokens"] == 5 and seen[0]["output_tokens"] == 3


def test_an_empty_reply_is_an_error_not_a_silent_success(pair):
    fake, client = pair
    fake.replies = [""]
    with pytest.raises(LLMError) as e:
        chat(client)
    assert e.value.code == "bad_response"


def test_an_unreadable_stream_chunk_is_an_error(pair):
    fake, client = pair
    raw_stream(client, b"data: {not json\n\n")
    with pytest.raises(LLMError) as e:
        chat(client)
    assert e.value.code == "bad_response"


def test_a_stream_that_runs_past_the_deadline_times_out():
    class Slow:
        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"x"}}]}'

    with pytest.raises(LLMError) as e:
        consume_sse(Slow(), deadline=0.0)
    assert e.value.code == "timeout"


# ---------------------------------------------------------------- problems become plain, actionable messages
@pytest.mark.parametrize("status, code, words", [
    (401, "auth_failed", "rejected the API key"), (403, "auth_failed", "no access"), (404, "model_missing", "was not found"),
    (413, "too_long", "too long"), (498, "cloud_unavailable", "HTTP 498"), (500, "cloud_unavailable", "HTTP 500"), (503, "cloud_unavailable", "HTTP 503"),
    (418, "failed", "HTTP 418"), (422, "failed", "HTTP 422"),
])
def test_http_errors_are_mapped_to_clear_messages(pair, status, code, words):
    fake, client = pair
    fake.replies = [status]
    with pytest.raises(LLMError) as e:
        chat(client)
    assert e.value.code == code and words in e.value.message and "Ollama" not in e.value.message
    assert KEY not in e.value.message and len(fake.chats) == 1                   # and a failure is never retried behind the user's back


@pytest.mark.parametrize("message", ["Please reduce the length of the messages or completion.", "This model's maximum context length is 131072 tokens",
                                     "Request too large for model in organization"])
def test_a_context_length_400_says_the_text_is_too_long(pair, message):
    fake, client = pair
    fake.replies = [(400, message)]
    with pytest.raises(LLMError) as e:
        chat(client)
    assert e.value.code == "too_long"


def test_groqs_model_does_not_exist_message_is_a_missing_model(pair):
    fake, client = pair
    fake.replies = [(400, "The model `nope` does not exist or you do not have access to it.")]
    with pytest.raises(LLMError) as e:
        chat(client, model="nope")
    assert e.value.code == "model_missing"


# ---------------------------------------------------------------- rate limits (HTTP 429)
def test_a_rate_limit_is_waited_out_once_when_the_reply_can_still_arrive_in_time(pair):
    fake, client = pair
    fake.replies = [RateLimited(retry_after=12)]
    assert json.loads(chat(client)) == {"ok": True}
    assert len(fake.chats) == 2 and len(client.slept) == 1 and 12 <= client.slept[0] <= 13


def test_a_second_rate_limit_is_reported_not_waited_out_again(pair):
    fake, client = pair
    fake.replies = [RateLimited(retry_after=5), RateLimited(retry_after=7)]
    with pytest.raises(LLMError) as e:
        chat(client)
    assert e.value.code == "rate_limited" and "about 7 seconds" in e.value.message
    assert len(fake.chats) == 2 and len(client.slept) == 1                         # exactly one wait


def test_a_wait_longer_than_the_deadline_is_reported_at_once_with_the_reset_time(pair):
    fake, client = pair
    fake.replies = [RateLimited(retry_after=3600)]                                 # e.g. the daily allowance is used up
    with pytest.raises(LLMError) as e:
        chat(client)
    msg = e.value.message
    assert e.value.code == "rate_limited" and "about 60 minutes" in msg and "Groq" in msg and "local model" in msg and KEY not in msg
    assert len(fake.chats) == 1 and client.slept == []


def test_without_a_retry_after_header_the_reset_headers_are_used(pair):
    fake, client = pair
    fake.replies = [RateLimited(reset_tokens="7.66s", reset_requests="2m59.56s")]
    assert json.loads(chat(client)) == {"ok": True}
    assert 7.6 <= client.slept[0] <= 8.5                                           # the sooner of the two resets


def test_a_rate_limit_that_says_nothing_about_when_is_reported_without_waiting(pair):
    fake, client = pair
    fake.replies = [RateLimited()]
    with pytest.raises(LLMError) as e:
        chat(client)
    assert e.value.code == "rate_limited" and "Wait a minute" in e.value.message and client.slept == []


@pytest.mark.parametrize("text, seconds", [("12", 12.0), ("7.66", 7.66), ("7.66s", 7.66), ("2m59.56s", 179.56), ("450ms", 0.45), ("1h2m3s", 3723.0),
                                           ("", None), (None, None), ("soon", None), ("3x", None)])
def test_duration_headers_are_parsed(text, seconds):
    got = parse_duration(text)
    assert got == seconds or (seconds is not None and abs(got - seconds) < 1e-6)


def test_wait_times_are_put_in_plain_words():
    assert humanise(1) == "about 1 second" and humanise(42.4) == "about 42 seconds" and humanise(600) == "about 10 minutes" and humanise(7200) == "about 2 hours"


def test_network_problems_are_reported_not_raised_raw(pair):
    fake, client = pair
    for exc, code in ((httpx.ConnectError("refused"), "cloud_unavailable"), (httpx.ReadTimeout("slow"), "timeout"), (httpx.RemoteProtocolError("bad"), "cloud_unavailable")):
        fake.replies = [exc]
        with pytest.raises(LLMError) as e:
            chat(client)
        assert e.value.code == code and KEY not in e.value.message


def test_an_echoed_key_is_redacted_from_server_messages(pair):
    fake, client = pair
    fake.replies = [(418, f"bad token {KEY} sent")]
    with pytest.raises(LLMError) as e:
        chat(client)
    assert KEY not in e.value.message and "[key]" in e.value.message


def test_no_key_means_no_request_at_all(tmp_path):
    fake = FakeCloud()
    client = make_cloud(make_settings(tmp_path), fake, key=None)
    for call in (lambda: chat(client), client.list_models, lambda: client.tiny_message(GRADER)):
        with pytest.raises(LLMError) as e:
            call()
        assert e.value.code == "auth_missing" and "Groq" in e.value.message
    assert fake.requests == []


def test_a_server_error_inside_the_stream_is_reported(pair):
    fake, client = pair
    raw_stream(client, b'data: {"error": {"message": "The model `x` does not exist", "type": "invalid_request_error"}}\n\n')
    with pytest.raises(LLMError) as e:
        chat(client)
    assert e.value.code == "model_missing"


# ---------------------------------------------------------------- connection test helpers
def test_listing_models_is_one_free_request_and_returns_sorted_active_ids(pair):
    fake, client = pair
    fake.inactive = ["old/retired-model"]
    assert client.list_models() == sorted(fake.models)
    assert len(fake.requests) == 1 and fake.requests[0]["path"] == MODELS_PATH == "/openai/v1/models" and fake.chats == []


def test_listing_models_maps_a_bad_key(pair):
    fake, client = pair
    fake.status_for_models = 401
    with pytest.raises(LLMError) as e:
        client.list_models()
    assert e.value.code == "auth_failed"


def test_an_unreadable_model_list_is_an_error(pair):
    fake, client = pair
    raw_stream(client, b"<html>gateway</html>")
    with pytest.raises(LLMError) as e:
        client.list_models()
    assert e.value.code == "bad_response"


def test_the_tiny_test_message_is_small_and_not_streamed(pair):
    fake, client = pair
    fake.replies = ["ok"]
    seen = []
    client.on_usage = seen.append
    out = client.tiny_message(GRADER)
    body = fake.chats[0]["json"]
    assert body["stream"] is False and body["max_completion_tokens"] <= 200 and "stream_options" not in body and len(fake.chats) == 1
    assert out == {"text": "ok", "prompt_tokens": 900, "output_tokens": 450} and seen[0]["purpose"] == "test" and seen[0]["provider"] == "cloud"
