# bettercode/llm/config_manager.py
import os
import yaml
from pathlib import Path
from typing import Dict, Any
from .config import LLMConfig

class LLMConfigManager:
    def __init__(self):
        # 1. Project-level config path: bettercode/config/config.yaml under current working directory.
        self.local_config_file = Path.cwd() / "bettercode" / "config" / "config.yaml"
        
        # 2. Global config path: ~/.config/bettercode/config.yaml
        self.global_config_file = Path.home() / ".config" / "bettercode" / "config.yaml"
        
        # Choose which config file to use in the current context.
        if (Path.cwd() / "bettercode").exists():
            self.config_file = self.local_config_file
        else:
            self.config_file = self.global_config_file

        self._local_configs: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    # Use safe_load to avoid YAML injection risks.
                    data = yaml.safe_load(f)
                    return data if isinstance(data, dict) else {}
            except Exception as e:
                print(f"Warning: failed to parse YAML config file {self.config_file}: {e}")
                return {}
        return {}

    def save_config(self, config: LLMConfig) -> None:
        """Save config into YAML, keyed by model_id at the top level."""
        # Ensure parent directory exists.
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Use model_id as the top-level YAML key.
        model_key = config.model_id
        self._local_configs[model_key] = {
            "api_key": config.api_key,
            "base_url": config.base_url,
            "provider": config.provider,
            "model_id": config.model_id
        }
        
        # Write YAML.
        with open(self.config_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                self._local_configs, 
                f, 
                allow_unicode=True, 
                sort_keys=False,
                default_flow_style=False
            )

    def get_model_config(self, model_id: str, default_provider: str = "") -> LLMConfig:
        """
        Get config by model_id.
        Prefer exact model_id match from YAML; fall back to environment variables.
        """
        # 1. Prefer persisted YAML config by exact model_id match.
        if model_id in self._local_configs:
            data = self._local_configs[model_id]
            return LLMConfig(
                model_id=data.get("model_id", model_id),
                api_key=data.get("api_key", ""),
                base_url=data.get("base_url"),
                provider=data.get("provider", default_provider or "openai")
            )

        # 2. Fall back to env vars (.env or system environment).
        # Use default_provider to choose env prefix; default to OPENAI when absent.
        prefix = default_provider.upper() if default_provider else "OPENAI"
        
        return LLMConfig(
            model_id=os.getenv(f"{prefix}_MODEL_ID", model_id),
            api_key=os.getenv(f"{prefix}_API_KEY", ""),
            base_url=os.getenv(f"{prefix}_BASE_URL"),
            provider=default_provider or "openai"
        )

# Global singleton manager.
config_manager = LLMConfigManager()
