from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Any
from llm.schemas import Message, LLMResponse, StreamChunk
from llm.config import LLMConfig

class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, config: LLMConfig):
        """Initialize the client with configuration."""
        self.config = config

    def _is_thinking_model(self) -> bool:
        """
        Heuristically check if the current model is a reasoning model
        (e.g., OpenAI o1, DeepSeek Reasoner) based on model ID keywords.
        """
        model_lower = self.config.model_id.lower()
        return any(k in model_lower for k in ["reasoner", "o1", "o3", "thinking"])

    @abstractmethod
    async def achat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        **kwargs: Any
    ) -> LLMResponse:
        """
        Asynchronous non-streaming chat.

        Args:
            messages: List of conversation messages.
            temperature: Sampling temperature (0.0 to 1.0).
            **kwargs: Additional provider-specific parameters.

        Returns:
            Unified LLMResponse containing generated content and metadata.
        """
        pass

    @abstractmethod
    async def astream_chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        **kwargs: Any
    ) -> AsyncIterator[StreamChunk]:
        """
        Asynchronous streaming chat.

        Args:
            messages: List of conversation messages.
            temperature: Sampling temperature (0.0 to 1.0).
            **kwargs: Additional provider-specific parameters.

        Yields:
            StreamChunk objects for incremental output.
        """
        pass