"""Local-model timeouts: reading the prompt is not a stall.

Review round 0 (2026-11-19) saw 4 of 6 real-model tests fail on an 8 GB Mac that was swapping: Ollama sends nothing, not even the
response headers, until the model has read the whole prompt, and the single 90 s read timeout treated that as "the model stopped
responding". Now the wait for the first word may use the whole LLM_TIMEOUT_S budget, and the idle limit applies between words.
"""
from __future__ import annotations

import json
import time
from dataclasses import replace

import httpx
import pytest

from app.config import Settings
from app.services.ollama import IDLE_MESSAGE, SLOW_START_MESSAGE, LLMError, OllamaClient

REPLY = '{"ok": true}'


def chunks(delays: list[float]):
    """A fake /api/chat stream: one JSON line per delay, the last one carrying done=true."""
    def gen():
        for i, d in enumerate(delays):
            time.sleep(d)
            last = i == len(delays) - 1
            yield (json.dumps({"message": {"content": REPLY if i == 0 else ""}, "done": last,
                               **({"eval_count": 3, "prompt_eval_count": 5} if last else {})}) + "\n").encode()
    return gen()


def client(delays: list[float], *, total: float, idle: float, seen: dict | None = None) -> OllamaClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen["read_timeout"] = request.extensions["timeout"]["read"]
        return httpx.Response(200, content=chunks(delays))

    s = replace(Settings(), llm_timeout_s=total, llm_idle_timeout_s=idle)
    return OllamaClient(s, http=httpx.Client(base_url=s.ollama_host, transport=httpx.MockTransport(handler)))


def test_transport_may_wait_the_whole_budget_for_the_first_word():
    """The root cause: the read timeout of the request itself was the 90 s idle limit."""
    seen: dict = {}
    client([0, 0], total=240, idle=90, seen=seen).chat_json([{"role": "user", "content": "q"}], {"type": "object"})
    assert seen["read_timeout"] > 200          # the remaining part of the 240 s budget, not 90 s


def test_a_slow_first_word_within_the_budget_is_not_a_stall():
    t0 = time.monotonic()
    text = client([0.6, 0], total=5, idle=0.2).chat_json([{"role": "user", "content": "q"}], {"type": "object"})
    # The first word came after 0.6 s, three times the 0.2 s idle limit, and was still accepted. (Not ">= 0.6": Windows' clock ticks
    # in ~15 ms steps, so a 0.6 s sleep can measure as 0.594 s; CI failed on that, 2026-11-21.)
    assert text == REPLY and time.monotonic() - t0 >= 0.5


def test_a_gap_between_words_longer_than_the_idle_limit_is_a_stall():
    t0 = time.monotonic()
    with pytest.raises(LLMError) as e:
        client([0, 0.8, 0], total=5, idle=0.2).chat_json([{"role": "user", "content": "q"}], {"type": "object"})
    assert e.value.code == "timeout" and e.value.message == IDLE_MESSAGE
    assert time.monotonic() - t0 < 2.0          # detected soon after the 0.2 s idle limit, long before the 5 s budget runs out


def test_no_first_word_within_the_budget_says_the_model_was_still_reading():
    with pytest.raises(LLMError) as e:
        client([1.0, 0], total=0.4, idle=0.2).chat_json([{"role": "user", "content": "q"}], {"type": "object"})
    assert e.value.code == "timeout" and e.value.message == SLOW_START_MESSAGE
    assert "Retry" in SLOW_START_MESSAGE and "memory" in SLOW_START_MESSAGE
