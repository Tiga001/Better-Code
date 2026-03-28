from __future__ import annotations

import unittest
from unittest.mock import patch

from bettercode.llm.gateway import LLMGatewayError, request_chat_completion
from bettercode.llm.schemas import LLMResponse, TokenUsage


class _FakeClient:
    async def achat(self, messages, temperature=0.7, **kwargs):
        return LLMResponse(
            content="ok",
            model="fake-model",
            usage=TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
            latency_ms=12,
        )


class LLMGatewayTests(unittest.TestCase):
    def test_request_chat_completion_uses_timeout_seconds(self) -> None:
        captured_timeout: list[float] = []

        async def _fake_wait_for(coroutine, timeout):
            captured_timeout.append(float(timeout))
            return await coroutine

        with (
            patch("bettercode.llm.gateway.create_llm_client", return_value=_FakeClient()),
            patch("bettercode.llm.gateway.asyncio.wait_for", side_effect=_fake_wait_for),
        ):
            result = request_chat_completion(
                model_id="fake-model",
                messages=[{"role": "user", "content": "hello"}],
                timeout_seconds=3.5,
            )

        self.assertEqual(captured_timeout, [3.5])
        self.assertEqual(result.content, "ok")
        self.assertEqual(result.usage["total_tokens"], 3)

    def test_request_chat_completion_rejects_non_positive_timeout(self) -> None:
        with self.assertRaises(LLMGatewayError):
            request_chat_completion(
                model_id="fake-model",
                messages=[{"role": "user", "content": "hello"}],
                timeout_seconds=0,
            )


if __name__ == "__main__":
    unittest.main()
