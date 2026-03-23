from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class LLMConfig(BaseSettings):
    """
    Configuration settings for a Language Model (LLM) client.

    Loads values from environment variables with the prefix "LLM_".
    For example: LLM_MODEL_ID, LLM_API_KEY, LLM_BASE_URL, LLM_TIMEOUT.
    Also reads from a .env file if present.
    """

    # Required: The model identifier (e.g., "gpt-4", "claude-3-opus")
    model_id: str

    # Required: API key for authentication with the LLM provider
    api_key: str

    # Optional: Base URL for custom API endpoints (e.g., proxy or self-hosted)
    # If not provided, the default URL for the provider is used.
    base_url: Optional[str] = None

    # Timeout in seconds for API requests (default: 60.0)
    timeout: float = 60.0

    @property
    def provider(self) -> str:
        """
        Auto-detect the provider based on the base_url.
        If base_url contains 'anthropic.com', returns 'anthropic'.
        Otherwise returns 'openai'.
        """
        if self.base_url and "anthropic.com" in self.base_url:
            return "anthropic"
        return "openai"

    # Pydantic settings configuration
    model_config = SettingsConfigDict(
        env_file=".env",           # Load from .env file
        env_file_encoding="utf-8", # File encoding
        extra="ignore",            # Ignore extra environment variables
        env_prefix="LLM_"          # Prefix for all environment variables
    )

