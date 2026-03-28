from __future__ import annotations

import atexit
import asyncio
import threading
from dataclasses import dataclass
from typing import Any

from .factory import create_llm_client
from .schemas import Message, MessageRole


class LLMGatewayError(RuntimeError):
    pass


class _BackgroundEventLoop:
    def __init__(self) -> None:
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread = threading.Thread(target=self._run, daemon=True, name="bettercode-llm-loop")
        self._thread.start()
        self._ready.wait()

    def submit(self, coroutine):
        if self._loop is None:
            raise LLMGatewayError("Background event loop is not available.")
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return future.result()

    def close(self) -> None:
        if self._loop is None:
            return
        if self._loop.is_closed():
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2.0)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()
        pending = asyncio.all_tasks(self._loop)
        for task in pending:
            task.cancel()
        if pending:
            self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self._loop.close()


_BACKGROUND_LOOP = _BackgroundEventLoop()
atexit.register(_BACKGROUND_LOOP.close)


@dataclass(slots=True)
class ChatCompletionResult:
    content: str
    model: str
    latency_ms: int
    usage: dict[str, int]
    reasoning_content: str | None = None


def request_chat_completion(
    *,
    model_id: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.7,
    max_tokens: int | None = None,
    timeout_seconds: float | None = None,
) -> ChatCompletionResult:
    try:
        normalized_messages = _normalize_messages(messages)
        client = create_llm_client(model_id)
        request_kwargs: dict[str, Any] = {}
        if max_tokens is not None:
            request_kwargs["max_tokens"] = max_tokens
        response = _run_async(
            client.achat(
                messages=normalized_messages,
                temperature=temperature,
                **request_kwargs,
            )
        )
    except Exception as error:  # pragma: no cover - exercised via callers
        raise LLMGatewayError(f"LLM gateway request failed: {error}") from error

    return ChatCompletionResult(
        content=response.content,
        model=response.model,
        latency_ms=response.latency_ms,
        usage=response.usage.model_dump(),
        reasoning_content=response.reasoning_content,
    )


def _normalize_messages(messages: list[dict[str, Any]]) -> list[Message]:
    normalized: list[Message] = []
    for index, raw in enumerate(messages):
        if not isinstance(raw, dict):
            raise LLMGatewayError(f"Message at index {index} must be a dict.")
        role_raw = str(raw.get("role", "")).strip().lower()
        content = str(raw.get("content", ""))
        try:
            role = MessageRole(role_raw)
        except ValueError as error:
            raise LLMGatewayError(f"Unsupported message role at index {index}: {role_raw}") from error
        normalized.append(Message(role=role, content=content))
    if not normalized:
        raise LLMGatewayError("At least one message is required.")
    return normalized


def _run_async(coroutine):
    return _BACKGROUND_LOOP.submit(coroutine)
