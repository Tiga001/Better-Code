import time
from typing import AsyncIterator, List, Any
from openai import AsyncOpenAI
from llm.base import BaseLLMClient
from llm.schemas import Message, LLMResponse, StreamChunk, TokenUsage


class OpenAIClient(BaseLLMClient):
    """OpenAI-compatible client for LLM interactions."""

    def __init__(self, config):
        """Initialize the client with configuration and create an AsyncOpenAI instance."""
        super().__init__(config)
        self._client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout
        )

    def _format_messages(self, messages: List[Message]) -> list[dict]:
        """Convert custom Message objects to the OpenAI API's expected dict format."""
        return [{"role": msg.role.value, "content": msg.content} for msg in messages]

    async def achat(
            self,
            messages: List[Message],
            temperature: float = 0.7,
            **kwargs: Any
    ) -> LLMResponse:
        """Non-streaming asynchronous chat call."""
        start_time = time.time()

        # Make the API request
        response = await self._client.chat.completions.create(
            model=self.config.model_id,
            messages=self._format_messages(messages),
            temperature=temperature,
            **kwargs
        )

        # Calculate latency
        latency_ms = int((time.time() - start_time) * 1000)

        # Extract the first completion choice
        choice = response.choices[0]

        # Safely extract reasoning content (for models like DeepSeek-R1, o1)
        reasoning = getattr(choice.message, 'reasoning_content', None) or getattr(choice, 'reasoning_content', None)

        # Parse token usage if available
        usage = TokenUsage()
        if response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens
            )

        # Return unified response
        return LLMResponse(
            content=choice.message.content or "",
            model=self.config.model_id,
            usage=usage,
            latency_ms=latency_ms,
            reasoning_content=reasoning
        )

    async def astream_chat(
            self,
            messages: List[Message],
            temperature: float = 0.7,
            **kwargs: Any
    ) -> AsyncIterator[StreamChunk]:
        """Streaming asynchronous chat call, yielding chunks."""
        # Ensure usage is included in the final chunk
        stream_options = kwargs.pop("stream_options", {})
        stream_options["include_usage"] = True

        # Start streaming request
        response = await self._client.chat.completions.create(
            model=self.config.model_id,
            messages=self._format_messages(messages),
            temperature=temperature,
            stream=True,
            stream_options=stream_options,
            **kwargs
        )

        # Process each chunk from the stream
        async for chunk in response:
            # Case: chunk with usage only (no choices)
            if not chunk.choices:
                if chunk.usage:
                    yield StreamChunk(
                        is_finished=True,
                        usage=TokenUsage(
                            prompt_tokens=chunk.usage.prompt_tokens,
                            completion_tokens=chunk.usage.completion_tokens,
                            total_tokens=chunk.usage.total_tokens
                        )
                    )
                continue

            # Case: normal content chunk
            delta = chunk.choices[0].delta
            content = delta.content or ""
            reasoning = getattr(delta, 'reasoning_content', "") or ""

            # Skip empty chunks
            if not content and not reasoning:
                continue

            yield StreamChunk(
                content=content,
                reasoning_content=reasoning,
                is_finished=False
            )