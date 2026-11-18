"""Cloud mode: the Groq API (OpenAI-compatible chat completions), authenticated with the user's own API key.

Facts from Groq's documentation (console.groq.com/docs, read 2026-11-18):
  * base URL api.groq.com/openai/v1 (the address itself lives only in config.py), `Authorization: Bearer <key>`; the key comes from Settings or GROQ_API_KEY and is never
    logged, returned by an API or put in an error message;
  * replies stream as data-only server-sent events ending with `data: [DONE]`; token usage arrives in a final chunk (`usage`, or
    `x_groq.usage`) when `stream_options.include_usage` is set;
  * native structured outputs cannot be streamed, so the JSON schema goes into the PROMPT (as before) and the reply is validated by us;
  * gpt-oss models reason before answering: `reasoning_effort` (low | medium | high) controls how much, `include_reasoning: false`
    keeps the reasoning text out of the reply. Reasoning tokens still count as output, so the output cap leaves room for them;
  * the output cap is `max_completion_tokens`;
  * a rate limit is HTTP 429 with a `retry-after` header (seconds). Free-plan limits are per model and per minute/day.
Nothing here runs unless the user switched to cloud mode and consented; there is no background polling.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any, Callable, Optional

import httpx

from ..config import Settings
from .ollama import LLMError
from .pricing import normalise

log = logging.getLogger("interviewer.cloud")

PROVIDER_NAME = "Groq"
SCHEMA_NOTE = ("\n\nOUTPUT FORMAT: reply with ONE JSON object and nothing else (no markdown fences, no commentary). "
               "It must match this JSON Schema:\n{schema}")
MIN_OUTPUT_TOKENS = 1500          # headroom so a reasoning model's thinking cannot eat the whole answer
TINY_OUTPUT_TOKENS = 200          # the connection test's one-word reply, with room for a little reasoning
_CONTEXT_WORDS = re.compile(r"context|too long|too large|maximum.*tokens|reduce the length|token limit", re.I)
_DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")


def api_name(model: str) -> str:
    """The id to send to the API: as typed, except that the short spelling 'gpt-oss-120b' becomes 'openai/gpt-oss-120b'."""
    typed = model.strip()
    return normalise(typed) if "/" not in typed and normalise(typed) != typed.lower() else typed


def with_schema(messages: list[dict[str, str]], schema: dict[str, Any]) -> list[dict[str, str]]:
    """Tell the model the schema in words. (Groq's native structured outputs do not support streaming, which this client relies on.)"""
    note = SCHEMA_NOTE.format(schema=json.dumps(schema, separators=(",", ":")))
    out = [dict(m) for m in messages]
    for m in out:
        if m.get("role") == "system":
            m["content"] = m["content"] + note
            return out
    return [{"role": "system", "content": note.strip()}] + out


def error_text(body: str) -> str:
    """The message of a Groq error body: {"error": {"message": "...", "type": "..."}}."""
    try:
        err = json.loads(body).get("error")
        return str(err.get("message") or err) if isinstance(err, dict) else str(err or body)
    except (ValueError, AttributeError):
        return body


def parse_duration(text: Optional[str]) -> Optional[float]:
    """Seconds from a header value: '12' / '7.66' (retry-after) or '2m59.56s' / '450ms' / '1h2m3s' (x-ratelimit-reset-*)."""
    t = (text or "").strip().lower()
    if not t:
        return None
    try:
        return max(0.0, float(t))
    except ValueError:
        pass
    parts = _DURATION_PART.findall(t)
    if not parts or "".join(n + u for n, u in parts) != t:
        return None
    scale = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}
    return sum(float(n) * scale[u] for n, u in parts)


def humanise(seconds: float) -> str:
    if seconds < 90:
        return f"about {max(1, round(seconds))} second{'s' if round(seconds) != 1 else ''}"
    if seconds < 5400:
        return f"about {round(seconds / 60)} minutes"
    return f"about {round(seconds / 3600)} hour{'s' if round(seconds / 3600) != 1 else ''}"


def consume_sse(response: httpx.Response, deadline: float) -> tuple[str, dict[str, Any]]:
    """Read a chat-completions event stream: (the answer text, the usage block). Reasoning text, if a model streams any, is ignored:
    only `delta.content` is the answer (and only the answer must be valid JSON)."""
    parts: list[str] = []
    usage: dict[str, Any] = {}
    for line in response.iter_lines():
        if time.monotonic() > deadline:
            raise LLMError("timeout", "The model took too long to answer.")
        line = line.strip()
        if not line or line.startswith(":") or not line.startswith("data:"):      # blank separators, comments, other SSE fields
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError as e:
            raise LLMError("bad_response", f"{PROVIDER_NAME} sent an unreadable stream chunk.") from e
        if not isinstance(chunk, dict):
            continue
        if chunk.get("error"):
            err = chunk["error"]
            msg = str(err.get("message") if isinstance(err, dict) else err)
            raise LLMError("model_missing" if "not found" in msg.lower() or "does not exist" in msg.lower() else "failed", msg[:300])
        found = chunk.get("usage") or (chunk.get("x_groq") or {}).get("usage")
        if isinstance(found, dict):
            usage = found
        for choice in chunk.get("choices") or []:
            piece = (choice.get("delta") or {}).get("content")
            if isinstance(piece, str):
                parts.append(piece)
    text = "".join(parts).strip()
    if not text:
        raise LLMError("bad_response", "The model returned an empty response.")
    return text, usage


class CloudClient:
    def __init__(self, settings: Settings, key: Callable[[], Optional[str]], http: Optional[httpx.Client] = None):
        self.settings = settings
        self._key = key
        self.http = http or httpx.Client(base_url=settings.cloud_url, timeout=httpx.Timeout(10.0, read=settings.cloud_idle_timeout_s))
        self.lock = threading.Lock()                       # one cloud request at a time (the free plan's per-minute limits are small)
        self.on_usage: Optional[Callable[[dict[str, Any]], None]] = None
        self.sleep: Callable[[float], None] = time.sleep   # replaced in tests
        self._no_reasoning: set[str] = set()               # models that rejected the reasoning switches

    # ------------------------------------------------------------ helpers
    def _headers(self) -> dict[str, str]:
        key = self._key()
        if not key:
            raise LLMError("auth_missing", f"No {PROVIDER_NAME} API key is saved. Add it in Settings → AI models, or switch back to the local model.")
        return {"Authorization": f"Bearer {key}"}

    def _redact(self, text: str) -> str:
        key = self._key()
        return text.replace(key, "[key]") if key else text

    def _rate_limited(self, headers: httpx.Headers, model: str) -> tuple[LLMError, Optional[float]]:
        """The error for a 429, and how long the server says to wait (None when it does not say)."""
        wait = parse_duration(headers.get("retry-after"))
        if wait is None:
            resets = [parse_duration(headers.get(h)) for h in ("x-ratelimit-reset-tokens", "x-ratelimit-reset-requests")]
            known = [r for r in resets if r is not None]
            wait = min(known) if known else None
        when = f"It resets in {humanise(wait)}." if wait is not None else "Wait a minute, then try again."
        err = LLMError("rate_limited", f"You have reached {PROVIDER_NAME}'s rate limit for “{model}” (free-plan limits are per model: a "
                                       f"per-minute and a daily allowance). {when} Your answer is saved; press Retry after that, or switch to "
                                       "the local model in Settings → AI models.")
        return err, wait

    def _raise_for(self, status: int, body: str, model: str, headers: Optional[httpx.Headers] = None) -> None:
        detail = self._redact(error_text(body))[:300]
        if status in (401, 403):
            raise LLMError("auth_failed", f"{PROVIDER_NAME} rejected the API key, or this key has no access to “{model}”. Check the key in Settings → AI models.")
        if status == 404 or "does not exist" in detail.lower() or "not found" in detail.lower():
            raise LLMError("model_missing", f"Cloud model “{model}” was not found. Choose another in Settings → AI models (Test connection lists what is available).")
        if status == 429:
            raise self._rate_limited(headers or httpx.Headers(), model)[0]
        if status == 413 or (status == 400 and _CONTEXT_WORDS.search(detail)):
            raise LLMError("too_long", f"This text is too long for “{model}” in one request. Shorten the answer or the resume section, or use the local model.")
        if status == 498 or status >= 500:
            raise LLMError("cloud_unavailable", f"{PROVIDER_NAME} had a problem (HTTP {status}). Try again in a moment.")
        raise LLMError("failed", f"{PROVIDER_NAME} returned HTTP {status}: {detail}")

    def _transport_error(self, e: Exception) -> LLMError:
        if isinstance(e, httpx.TimeoutException):
            return LLMError("timeout", f"{PROVIDER_NAME} did not answer in time.")
        if isinstance(e, httpx.ConnectError):
            return LLMError("cloud_unavailable", f"Cannot reach {PROVIDER_NAME}. Check your internet connection.")
        return LLMError("cloud_unavailable", f"The connection to {PROVIDER_NAME} failed ({type(e).__name__}).")

    def _reasoning(self, model: str) -> dict[str, Any]:
        """The reasoning switches for a model. Only gpt-oss models are documented to take them; a model that rejects them is remembered."""
        if model in self._no_reasoning or "gpt-oss" not in normalise(model):
            return {}
        return {"reasoning_effort": self.settings.cloud_reasoning_effort, "include_reasoning": False}

    def _payload(self, messages, schema, model, max_tokens, temperature, stream: bool = True) -> dict[str, Any]:
        cap = min(self.settings.cloud_max_tokens, max(max_tokens or 0, MIN_OUTPUT_TOKENS))
        payload: dict[str, Any] = {"model": api_name(model), "messages": with_schema(messages, schema) if schema else messages, "stream": stream,
                                   "temperature": self.settings.llm_temperature if temperature is None else temperature,
                                   "max_completion_tokens": cap, **self._reasoning(model)}
        if stream:
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _report(self, usage: dict[str, Any], model: str, purpose: str) -> None:
        if self.on_usage:
            try:
                from .usage import from_groq

                self.on_usage(from_groq(usage, model, purpose))
            except Exception:
                log.debug("could not report cloud usage", exc_info=True)

    # ------------------------------------------------------------ chat
    def chat_json(self, messages: list[dict[str, str]], schema: dict[str, Any], *, model: str, max_tokens: Optional[int] = None,
                  temperature: Optional[float] = None, purpose: str = "chat") -> str:
        headers = self._headers()
        with self.lock:
            deadline = time.monotonic() + self.settings.cloud_timeout_s
            waited = False
            for _ in range(4):                               # at most: one reasoning-switch retry and one rate-limit wait
                payload = self._payload(messages, schema, model, max_tokens, temperature)
                try:
                    with self.http.stream("POST", "/chat/completions", json=payload, headers=headers) as r:
                        if r.status_code != 200:
                            body = r.read().decode("utf-8", "replace")
                            if r.status_code == 400 and "reasoning" in error_text(body).lower() and model not in self._no_reasoning and self._reasoning(model):
                                self._no_reasoning.add(model)        # this model has no reasoning switch: ask again without it (a 400 costs nothing)
                                continue
                            if r.status_code == 429:
                                err, wait = self._rate_limited(r.headers, model)
                                if not waited and wait is not None and time.monotonic() + wait + 1 < deadline:
                                    waited = True                    # wait ONCE, and only if the reply can still arrive inside the deadline
                                    log.info("cloud rate limit: waiting %.1fs once before retrying", wait)
                                    self.sleep(wait + 0.5)
                                    continue
                                raise err
                            self._raise_for(r.status_code, body, model, r.headers)
                        text, usage = consume_sse(r, deadline)
                        self._report(usage, model, purpose)
                        return text
                except LLMError:
                    raise
                except httpx.HTTPError as e:
                    raise self._transport_error(e) from e
        raise LLMError("failed", f"{PROVIDER_NAME} rejected the request.")

    # ------------------------------------------------------------ connection test (no inference unless asked)
    def list_models(self) -> list[str]:
        """GET /models: which models this key can use. Not a model call (no tokens)."""
        headers = self._headers()
        try:
            r = self.http.get("/models", headers=headers, timeout=20)
        except httpx.HTTPError as e:
            raise self._transport_error(e) from e
        if r.status_code != 200:
            self._raise_for(r.status_code, r.text, "the model list", r.headers)
        try:
            return sorted({str(m["id"]) for m in r.json().get("data", []) if isinstance(m, dict) and m.get("id") and m.get("active", True)})
        except (ValueError, AttributeError, TypeError) as e:
            raise LLMError("bad_response", f"{PROVIDER_NAME} sent a model list we could not read.") from e

    def tiny_message(self, model: str) -> dict[str, Any]:
        """One very small real request (a few dozen tokens) to prove a model answers. Only on explicit request."""
        headers = self._headers()
        with self.lock:
            for attempt in range(2):
                payload = {"model": api_name(model), "messages": [{"role": "user", "content": "Reply with the single word: ok"}], "stream": False,
                           "temperature": 0, "max_completion_tokens": TINY_OUTPUT_TOKENS, **self._reasoning(model)}
                try:
                    r = self.http.post("/chat/completions", json=payload, headers=headers, timeout=60)
                except httpx.HTTPError as e:
                    raise self._transport_error(e) from e
                if r.status_code == 400 and "reasoning" in error_text(r.text).lower() and attempt == 0 and self._reasoning(model):
                    self._no_reasoning.add(model)
                    continue
                if r.status_code != 200:
                    self._raise_for(r.status_code, r.text, model, r.headers)
                break
        try:
            reply = r.json()
            usage = reply.get("usage") or {}
            text = ((reply.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        except (ValueError, AttributeError, IndexError, TypeError) as e:
            raise LLMError("bad_response", f"{PROVIDER_NAME} sent a reply we could not read.") from e
        self._report(usage, model, "test")
        return {"text": text.strip()[:80], "prompt_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens")}
