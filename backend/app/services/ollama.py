"""Thin client for the local Ollama HTTP API. Only ever talks to the configured loopback host."""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
from typing import Any, Callable, Iterator, Optional

import httpx

from ..config import Settings, is_loopback_url, setup_cmd

log = logging.getLogger("interviewer.ollama")


# Before the first word the model is still reading the prompt (and maybe loading): on an 8 GB computer that is swapping this alone
# can take minutes, so it gets the whole LLM_TIMEOUT_S budget. Once words flow, a gap longer than LLM_IDLE_TIMEOUT_S means a stall.
SLOW_START_MESSAGE = ("The local model did not start answering in time: it was still reading the question and your answer. This "
                      "usually means the computer is short of memory. Your answer is saved; close other apps and press Retry.")
IDLE_MESSAGE = "The local model stopped responding (idle timeout)."


class LLMError(Exception):
    """code: ollama_unavailable | model_missing | timeout | bad_response | unsupported | failed"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _pull_error(r: httpx.Response) -> str:
    try:
        return str(r.json().get("error") or f"Ollama answered {r.status_code}.")
    except ValueError:
        return f"Ollama answered {r.status_code}."


class OllamaClient:
    def __init__(self, settings: Settings, http: Optional[httpx.Client] = None):
        if not is_loopback_url(settings.ollama_host):
            import os

            if os.environ.get("ALLOW_NON_LOCAL_OLLAMA") != "1":
                raise RuntimeError("Ollama host must be a loopback address.")
        self.settings = settings
        self.http = http or httpx.Client(
            base_url=settings.ollama_host,
            timeout=httpx.Timeout(10.0, read=settings.llm_idle_timeout_s),
            trust_env=False,  # never route local model traffic through an environment proxy
        )
        # Only one generation at a time: a 4B model on 8 GB RAM must not be asked to run in parallel.
        self.llm_lock = threading.Lock()
        self._no_think_models: set[str] = set()
        self._clock: Callable[[], float] = time.monotonic        # replaceable in tests
        self.on_usage: Optional[Callable[[dict[str, Any]], None]] = None   # receives tokens/timings of each reply (see services/usage.py)

    # ------------------------------------------------------------ introspection
    def version(self) -> str:
        try:
            r = self.http.get("/api/version", timeout=3)
            r.raise_for_status()
            return r.json().get("version", "unknown")
        except httpx.HTTPError as e:
            raise LLMError("ollama_unavailable", _unavailable_msg(self.settings)) from e

    def list_models(self) -> list[dict[str, Any]]:
        try:
            r = self.http.get("/api/tags", timeout=5)
            r.raise_for_status()
            return r.json().get("models", [])
        except httpx.HTTPError as e:
            raise LLMError("ollama_unavailable", _unavailable_msg(self.settings)) from e

    def pull_stream(self, model: str):
        """Download a model through the LOCAL Ollama (it talks to its own registry; this app never does). Yields Ollama's progress
        objects ({"status", "total", "completed"}) and raises LLMError on a failure. Close the generator to stop."""
        try:
            with self.http.stream("POST", "/api/pull", json={"model": model, "stream": True}, timeout=httpx.Timeout(10.0, read=None)) as r:
                if r.status_code != 200:
                    r.read()
                    raise LLMError("pull_failed", _pull_error(r))
                for line in r.iter_lines():
                    if not line.strip():
                        continue
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    if ev.get("error"):
                        raise LLMError("pull_failed", str(ev["error"]))
                    yield ev
        except httpx.HTTPError as e:
            raise LLMError("ollama_unavailable", _unavailable_msg(self.settings)) from e

    def running(self) -> list[dict[str, Any]]:
        try:
            r = self.http.get("/api/ps", timeout=3)
            r.raise_for_status()
            return r.json().get("models", [])
        except httpx.HTTPError:
            return []

    def show(self, model: str) -> dict[str, Any]:
        try:
            r = self.http.post("/api/show", json={"model": model}, timeout=10)
        except httpx.HTTPError as e:
            raise LLMError("ollama_unavailable", _unavailable_msg(self.settings)) from e
        if r.status_code == 404:
            raise LLMError("model_missing", f"Model '{model}' is not installed. Run {setup_cmd()}")
        r.raise_for_status()
        return r.json()

    def has_model(self, model: str) -> bool:
        names = {m.get("name") for m in self.list_models()} | {m.get("model") for m in self.list_models()}
        return model in names or (":" not in model and f"{model}:latest" in names)

    # ------------------------------------------------------------ generation
    def chat_json(self, messages: list[dict[str, str]], schema: dict[str, Any], *, model: Optional[str] = None,
                  max_tokens: Optional[int] = None, temperature: Optional[float] = None, purpose: str = "chat") -> str:
        """Stream a schema-constrained chat completion; return the raw JSON text.

        Enforces a total deadline and an idle (no-token) timeout. Holds the global LLM lock.
        """
        model = model or self.settings.llm_model
        with self.llm_lock:
            return self._chat_json_locked(messages, schema, model, max_tokens, temperature, purpose)

    def _runner_options(self) -> dict[str, Any]:
        """Options that decide how the model is LOADED. Ollama loads it with these, so a warm-up must use exactly the same
        values as real requests (a warm-up without them loads a smaller 4096-token context than the app is designed for)."""
        return {"num_ctx": self.settings.llm_num_ctx}

    def _payload(self, messages, schema, model, max_tokens, temperature, think: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "format": schema,
            "keep_alive": self.settings.llm_keep_alive,
            "options": {
                "temperature": self.settings.llm_temperature if temperature is None else temperature,
                **self._runner_options(),
                "num_predict": max_tokens or self.settings.llm_max_tokens,
            },
        }
        if not think and model not in self._no_think_models:
            payload["think"] = False  # reasoning models: we want the JSON answer, not a long hidden monologue
        return payload

    def _chat_json_locked(self, messages, schema, model, max_tokens, temperature, purpose: str = "chat") -> str:
        deadline = time.monotonic() + self.settings.llm_timeout_s
        for attempt in range(2):
            payload = self._payload(messages, schema, model, max_tokens, temperature, think=False)
            # The transport must not give up while the model is still reading the prompt: Ollama sends nothing, not even the
            # response headers, until the first word, so the read timeout here is the time left of the overall budget.
            # The idle limit between words is enforced by consume_chat_stream once words flow.
            wait = max(1.0, deadline - time.monotonic())
            try:
                with self.http.stream("POST", "/api/chat", json=payload, timeout=httpx.Timeout(10.0, read=wait)) as r:
                    if r.status_code != 200:
                        body = r.read().decode("utf-8", "replace")
                        err = _error_text(body)
                        if r.status_code == 404 or "not found" in err.lower():
                            raise LLMError("model_missing", f"Model '{model}' is not installed. Run {setup_cmd()}")
                        if attempt == 0 and "think" in err.lower():
                            self._no_think_models.add(model)  # model doesn't support the think flag
                            continue
                        if "does not support" in err.lower():
                            raise LLMError("unsupported", f"Model '{model}' lacks a required capability: {err}")
                        raise LLMError("failed", f"Ollama returned HTTP {r.status_code}: {err[:300]}")
                    text, final = self._consume(r, deadline)
                    self._report(final, model, purpose)
                    return text
            except LLMError:
                raise
            except httpx.ConnectError as e:
                raise LLMError("ollama_unavailable", _unavailable_msg(self.settings)) from e
            except httpx.TimeoutException as e:      # only before the first word: later stalls are reported by the stream watchdog
                raise LLMError("timeout", SLOW_START_MESSAGE) from e
            except httpx.HTTPError as e:
                raise LLMError("failed", f"Connection to Ollama failed: {type(e).__name__}") from e
        raise LLMError("failed", "Ollama rejected the request.")

    def _report(self, reply: dict[str, Any], model: str, purpose: str) -> None:
        if self.on_usage:
            try:
                from .usage import from_ollama

                self.on_usage(from_ollama(reply, model, purpose))
            except Exception:  # statistics must never break a model call
                log.debug("could not report model usage", exc_info=True)

    def _consume(self, response: httpx.Response, deadline: float) -> tuple[str, dict[str, Any]]:
        return consume_chat_stream(response, deadline, idle_s=self.settings.llm_idle_timeout_s)

    def unload(self, model: str) -> None:
        try:
            self.http.post("/api/generate", json={"model": model, "keep_alive": 0}, timeout=5)
        except httpx.HTTPError:
            pass

    def is_loaded(self, model: str) -> bool:
        return any(m.get("name") in (model, f"{model}:latest") for m in self.running())

    def warm(self, model: str) -> bool:
        """Make sure the model is in memory (and restart its idle timer), without generating any text. Loading it early means the
        slow, memory-hungry load does not land in the middle of an answer; calling it again while an interview is open stops the
        model being unloaded while you think. Same load options as real requests. Returns False on failure; never raises."""
        if not self.llm_lock.acquire(blocking=False):    # a real generation is running: the model is loaded and in use
            return True
        try:
            was_loaded = self.is_loaded(model)
            started = self._clock()
            r = self.http.post("/api/generate", json={"model": model, "keep_alive": self.settings.llm_keep_alive, "stream": False,
                                                      "options": self._runner_options()},
                               timeout=httpx.Timeout(10.0, read=180.0))
            if r.status_code == 200 and not was_loaded:
                # Ollama reports no timing for a load-only request, so the stopwatch is ours. A timer refresh is not a load.
                try:
                    reply = r.json()
                except ValueError:
                    reply = {}
                ns = reply.get("load_duration") or int((self._clock() - started) * 1e9)
                if ns >= 300e6:
                    self._report({**reply, "load_duration": ns, "total_duration": reply.get("total_duration") or ns}, model, "warm")
            return r.status_code == 200
        except httpx.HTTPError:
            return False
        finally:
            self.llm_lock.release()


_END = object()


def _watched_lines(response: httpx.Response, deadline: float, idle_s: float) -> Iterator[str]:
    """The stream's lines, with two limits the transport cannot tell apart: until the first line arrives the whole remaining budget
    (`deadline`) is allowed, because the model may still be reading a long prompt; after that, a gap longer than `idle_s` is a stall.
    A helper thread does the blocking reads, so a limit can be enforced whatever the transport does (and tested with a fake one)."""
    lines: queue.Queue[Any] = queue.Queue()

    def pump() -> None:
        try:
            for line in response.iter_lines():
                lines.put(line)
        except BaseException as e:      # the watchdog closed the response, or the connection broke: hand it to the reader
            lines.put(e)
        else:
            lines.put(_END)

    threading.Thread(target=pump, name="ollama-stream", daemon=True).start()
    started = False
    while True:
        remaining = deadline - time.monotonic()
        wait = min(remaining, idle_s) if started else remaining
        try:
            item = lines.get(timeout=max(0.0, wait))
        except queue.Empty:
            try:
                response.close()            # unblocks the helper thread
            except Exception:
                log.debug("closing a stalled stream failed", exc_info=True)
            if not started:
                raise LLMError("timeout", SLOW_START_MESSAGE) from None
            if remaining <= idle_s:
                raise LLMError("timeout", "The model took too long to answer.") from None
            raise LLMError("timeout", IDLE_MESSAGE) from None
        if item is _END:
            return
        if isinstance(item, BaseException):
            if isinstance(item, httpx.TimeoutException):
                raise LLMError("timeout", IDLE_MESSAGE if started else SLOW_START_MESSAGE) from item
            raise item
        started = True
        yield item


def consume_chat_stream(response: httpx.Response, deadline: float, idle_s: Optional[float] = None) -> tuple[str, dict[str, Any]]:
    """Read an Ollama /api/chat stream (local or cloud): the reply text, and the final chunk that carries the token counts and timings.
    Any 'thinking' text a reasoning model streams is ignored: only the answer is returned (and only the answer must be valid JSON).
    With `idle_s`, a stall after the first line is detected after that many seconds (see _watched_lines)."""
    parts: list[str] = []
    final: dict[str, Any] = {}
    for line in (response.iter_lines() if idle_s is None else _watched_lines(response, deadline, idle_s)):
        if time.monotonic() > deadline:
            raise LLMError("timeout", "The model took too long to answer.")
        if not line:
            continue
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError as e:
            raise LLMError("bad_response", "Ollama sent an unreadable stream chunk.") from e
        if chunk.get("error"):
            msg = str(chunk["error"])
            code = "model_missing" if "not found" in msg.lower() else "failed"
            raise LLMError(code, msg[:300])
        parts.append((chunk.get("message") or {}).get("content", ""))
        if chunk.get("done"):
            final = chunk                      # the last chunk carries the token counts and timings
            break
    text = "".join(parts).strip()
    if not text:
        raise LLMError("bad_response", "The model returned an empty response.")
    return text, final


def _error_text(body: str) -> str:
    try:
        data = json.loads(body)
        err = data.get("error")
        return err.get("message", str(err)) if isinstance(err, dict) else str(err or body)
    except (json.JSONDecodeError, AttributeError):
        return body


def _unavailable_msg(settings: Settings) -> str:
    return (f"Ollama is not reachable at {settings.ollama_host}. Start it with `ollama serve` "
            "(or open the Ollama app), then retry.")
