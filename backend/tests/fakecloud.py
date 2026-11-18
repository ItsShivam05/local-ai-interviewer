"""A stand-in for Groq's documented API (POST /openai/v1/chat/completions as server-sent events, GET /openai/v1/models).
No network, no account.

It records every request so tests can prove WHAT was sent (key, model, schema in the prompt, reasoning switches) and HOW MANY calls
were made.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Optional

import httpx

from app.config import Settings
from app.services.cloud import CloudClient

KEY = "gsk_test_key_1234567890abcd"
GRADER, SMALL = "openai/gpt-oss-120b", "openai/gpt-oss-20b"
ALL_MODELS = [GRADER, SMALL, "qwen/qwen3.8-27b", "llama-3.3-70b-versatile"]
CHAT_PATH, MODELS_PATH = "/openai/v1/chat/completions", "/openai/v1/models"


@dataclass
class RateLimited:
    """A 429 reply. `retry_after` (seconds) is the header Groq sets on a 429; the reset headers are durations such as '7.66s'."""
    retry_after: Optional[float] = None
    reset_tokens: Optional[str] = None
    reset_requests: Optional[str] = None


class FakeCloud:
    def __init__(self):
        self.models = list(ALL_MODELS)
        self.inactive: list[str] = []                     # listed by the API with "active": false
        self.requests: list[dict[str, Any]] = []          # every request: method, path, headers, json
        # queue: dict -> JSON answer, str -> raw text, int -> HTTP error, (int, str) -> error with that message, RateLimited -> 429, Exception -> raise
        self.replies: list[Any] = []
        self.default: Optional[Callable[[dict], Any]] = smart_default
        self.prompt_tokens, self.output_tokens = 900, 450
        self.status_for_models = 200
        self.usage_in = "usage"                           # "usage" | "x_groq" | None: where the stream reports token usage
        self.reasoning_in_stream = True                   # stream a reasoning delta first (the client must ignore it)

    # ------------------------------------------------------------ introspection
    @property
    def chats(self) -> list[dict]:
        return [r for r in self.requests if r["path"] == CHAT_PATH]

    @property
    def model_list_calls(self) -> list[dict]:
        return [r for r in self.requests if r["path"] == MODELS_PATH]

    def models_used(self) -> list[str]:
        return [r["json"]["model"] for r in self.chats]

    def usage(self) -> dict[str, Any]:
        return {"queue_time": 0.05, "prompt_tokens": self.prompt_tokens, "prompt_time": 0.3, "completion_tokens": self.output_tokens,
                "completion_time": 9.0, "total_tokens": self.prompt_tokens + self.output_tokens, "total_time": 9.3}

    # ------------------------------------------------------------ the HTTP handler
    @staticmethod
    def _error(status: int, message: str, headers: Optional[dict[str, str]] = None) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": message, "type": "invalid_request_error"}}, headers=headers or {})

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.requests.append({"method": request.method, "path": request.url.path, "headers": dict(request.headers), "json": body, "host": request.url.host})
        if request.url.path == MODELS_PATH:
            if self.status_for_models != 200:
                return self._error(self.status_for_models, "Invalid API Key" if self.status_for_models == 401 else "nope")
            return httpx.Response(200, json={"object": "list", "data": [
                {"id": m, "object": "model", "created": 1, "owned_by": m.split("/")[0], "active": m not in self.inactive, "context_window": 131072}
                for m in [*self.models, *self.inactive]]})
        if request.url.path == CHAT_PATH:
            reply = self.replies.pop(0) if self.replies else (self.default(body) if self.default else {"ok": True})
            if isinstance(reply, RateLimited):
                headers = {k: v for k, v in {"retry-after": None if reply.retry_after is None else str(reply.retry_after),
                                             "x-ratelimit-reset-tokens": reply.reset_tokens, "x-ratelimit-reset-requests": reply.reset_requests}.items() if v}
                return self._error(429, "Rate limit reached for model in organization org_x on tokens per minute (TPM)", headers)
            if isinstance(reply, int):
                return self._error(reply, f"error {reply}")
            if isinstance(reply, tuple):
                return self._error(reply[0], reply[1])
            if isinstance(reply, Exception):
                raise reply
            text = reply if isinstance(reply, str) else json.dumps(reply)
            if body.get("stream") is False:
                return httpx.Response(200, json={"id": "chatcmpl-1", "object": "chat.completion", "model": body["model"],
                                                 "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                                                 "usage": self.usage(), "x_groq": {"id": "req_1"}})

            def chunk(delta: dict, **extra) -> str:
                return "data: " + json.dumps({"id": "chatcmpl-1", "object": "chat.completion.chunk", "model": body["model"],
                                              "choices": [{"index": 0, "delta": delta, "finish_reason": None}], **extra})

            events = [chunk({"role": "assistant", "content": ""})]
            if self.reasoning_in_stream:
                events.append(chunk({"reasoning": "(thinking about the answer)"}))
            events += [chunk({"content": text[:25]}), chunk({"content": text[25:]})]
            last = {"id": "chatcmpl-1", "object": "chat.completion.chunk", "model": body["model"], "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            if self.usage_in == "x_groq":
                last["x_groq"] = {"id": "req_1", "usage": self.usage()}
            events.append("data: " + json.dumps(last))
            if self.usage_in == "usage":                       # OpenAI style: a final chunk with no choices that carries the usage
                events.append("data: " + json.dumps({"id": "chatcmpl-1", "object": "chat.completion.chunk", "choices": [], "usage": self.usage()}))
            events.append("data: [DONE]")
            return httpx.Response(200, content=("\n\n".join(events) + "\n\n").encode(), headers={"content-type": "text/event-stream"})
        return self._error(404, "unknown path")


def smart_default(body: dict) -> Any:
    """Answer each kind of request the app makes, recognised by its system prompt."""
    from conftest import good_eval

    system = body["messages"][0]["content"]
    if "evaluating ONE candidate answer" in system:
        return good_eval(correctness=8)
    if "repair speech-recognition transcripts" in system:
        return {"text": "MySQL is a relational database.", "unclear": []}
    if "Write ONE short follow-up question" in system:
        return {"question": "Which key would you merge on, and why that one?"}
    if "closing assessment" in system:
        return {"overall_summary": "A solid session.", "strengths": ["Clear"], "knowledge_gaps": [], "repeated_misconceptions": [], "topics_to_revise": [], "recommendations": ["Keep going"]}
    return {"ok": True}


def make_cloud(settings: Settings, fake: FakeCloud, key: Optional[str] = KEY, key_provider: Optional[Callable[[], Optional[str]]] = None) -> CloudClient:
    """`key` is a fixed test key; `key_provider` reads it from somewhere live (the real app reads it from its settings or GROQ_API_KEY)."""
    http = httpx.Client(base_url=settings.cloud_url, transport=httpx.MockTransport(fake.handler), timeout=5)
    client = CloudClient(settings, key=key_provider or (lambda: key), http=http)
    client.slept = []                                   # tests never really sleep: waits are recorded instead
    client.sleep = client.slept.append
    return client
