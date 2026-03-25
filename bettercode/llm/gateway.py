from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Any

from .factory import create_llm_client
from .schemas import Message, MessageRole


class LLMGatewayError(RuntimeError):
    pass


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
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    result_holder: dict[str, Any] = {}
    error_holder: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result_holder["value"] = asyncio.run(coroutine)
        except BaseException as error:  # pragma: no cover - defensive path
            error_holder["error"] = error

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()

    if "error" in error_holder:
        raise error_holder["error"]
    return result_holder["value"]
