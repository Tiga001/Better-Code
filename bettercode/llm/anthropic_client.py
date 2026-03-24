# bettercode/llm/anthropic_client.py
import time
from typing import AsyncIterator, List, Tuple, Any
from anthropic import AsyncAnthropic
from llm.base import BaseLLMClient
from llm.schemas import Message, MessageRole, LLMResponse, StreamChunk, TokenUsage


class AnthropicClient(BaseLLMClient):
    """Anthropic API client implementation."""

    def __init__(
            self, 
            config
    ):
        """Initialize with config and create AsyncAnthropic client."""
        super().__init__(config)
        self._client = AsyncAnthropic(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout
        )

    def _extract_system_prompt(
            self, 
            messages: List[Message]
    ) -> Tuple[str, list[dict]]:
        """
        Extract system prompts from message list.
        Anthropic requires system prompt to be passed separately, not inside the messages array.
        Returns: (system_prompt, list of converted non-system messages)
        """
        system_prompt = ""
        converted = []
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system_prompt += msg.content + "\n"
            else:
                converted.append({"role": msg.role.value, "content": msg.content})
        return system_prompt.strip(), converted

    async def achat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        **kwargs: Any
    ) -> LLMResponse:
        """Non-streaming asynchronous chat call."""
        start_time = time.time()
        system, converted_msgs = self._extract_system_prompt(messages)

        # Anthropic API requires max_tokens to be set
        max_tokens = kwargs.pop("max_tokens", 4096)

        response = await self._client.messages.create(
            model=self.config.model_id,
            system=system if system else None,
            messages=converted_msgs,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

        latency_ms = int((time.time() - start_time) * 1000)

        # Extract text from all content blocks (may be multiple)
        content = "".join(block.text for block in response.content if hasattr(block, 'text'))

        # Build token usage
        usage = TokenUsage()
        if response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens
            )

        return LLMResponse(
            content=content,
            model=self.config.model_id,
            usage=usage,
            latency_ms=latency_ms
        )

    async def astream_chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        **kwargs: Any
    ) -> AsyncIterator[StreamChunk]:
        """Streaming asynchronous chat call, yielding chunks."""
        system, converted_msgs = self._extract_system_prompt(messages)
        max_tokens = kwargs.pop("max_tokens", 4096)

        # Use the streaming context manager
        async with self._client.messages.stream(
            model=self.config.model_id,
            system=system if system else None,
            messages=converted_msgs,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        ) as stream:
            # Yield each text fragment as it arrives
            async for text in stream.text_stream:
                yield StreamChunk(content=text, is_finished=False)

            # After stream ends, retrieve final message for usage stats
            final_msg = await stream.get_final_message()
            if final_msg.usage:
                yield StreamChunk(
                    is_finished=True,
                    usage=TokenUsage(
                        prompt_tokens=final_msg.usage.input_tokens,
                        completion_tokens=final_msg.usage.output_tokens,
                        total_tokens=final_msg.usage.input_tokens + final_msg.usage.output_tokens
                    )
                )