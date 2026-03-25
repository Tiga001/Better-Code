from .base import BaseLLMClient
from .config_manager import config_manager  # 新增导入

def create_llm_client(model_id: str) -> BaseLLMClient:
    """
    Create the appropriate LLM client based on the model ID.

    The model ID is used to look up the full configuration (api_key, base_url, provider)
    from the config manager (YAML or environment variables).

    Args:
        model_id: The model identifier (e.g., "gpt-4o", "claude-3-sonnet")

    Returns:
        An instance of a concrete client (OpenAIClient or AnthropicClient)
    """
    config = config_manager.get_model_config(model_id)

    if config.provider == "anthropic":
        try:
            from .anthropic_client import AnthropicClient
        except ImportError as exc:
            raise ImportError(
                "Anthropic client dependencies are missing. "
                "Install with: pip install anthropic"
            ) from exc
        return AnthropicClient(config)

    try:
        from .openai_client import OpenAIClient
    except ImportError as exc:
        raise ImportError(
            "OpenAI-compatible client dependencies are missing. "
            "Install with: pip install openai"
        ) from exc

    return OpenAIClient(config)
