from llm.config import LLMConfig
from llm.base import BaseLLMClient
from llm.openai_client import OpenAIClient
from llm.anthropic_client import AnthropicClient

def create_llm_client(config: LLMConfig | None = None) -> BaseLLMClient:
    """
    Create the appropriate LLM client based on the provided configuration.

    If no config is provided, it will be built from environment variables (or .env file).

    Args:
        config: Optional LLMConfig instance. If None, a default config is created.

    Returns:
        An instance of a concrete client (OpenAIClient or AnthropicClient).
    """
    # Use default config if none provided
    cfg = config or LLMConfig()

    # Check provider type from configuration
    if cfg.provider == "anthropic":
        return AnthropicClient(cfg)

    # Default to OpenAI-compatible client (works with OpenAI, DeepSeek, etc.)
    return OpenAIClient(cfg)