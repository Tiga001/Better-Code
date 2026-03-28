# bettercode/llm/config_manager.py
import os
import re
import yaml
from pathlib import Path
from typing import Dict, Any
from .config import LLMConfig


class LLMConfigManager:
    def __init__(self):
        self.project_root = Path.cwd()

        # 1. Project-level config path: bettercode/config/config.yaml under current working directory.
        self.local_config_file = self.project_root / "bettercode" / "config" / "config.yaml"

        # 2. Global config path: ~/.config/bettercode/config.yaml
        self.global_config_file = Path.home() / ".config" / "bettercode" / "config.yaml"

        # Choose which config file to use in the current context.
        if (self.project_root / "bettercode").exists():
            self.config_file = self.local_config_file
        else:
            self.config_file = self.global_config_file

        # Environment files (project root is the default location).
        self.local_env_file = self.project_root / ".env"
        self.legacy_env_file = self.project_root / "bettercode" / ".env"
        self.global_env_file = Path.home() / ".config" / "bettercode" / ".env"

        self._local_configs: Dict[str, Dict[str, Any]] = self._load()
        self._env_entries_cache: Dict[str, str] | None = None

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

    def _env_sources(self) -> list[Path]:
        # Priority: project root .env > legacy bettercode/.env > global .env
        return [self.local_env_file, self.legacy_env_file, self.global_env_file]

    def _env_entries(self) -> Dict[str, str]:
        if self._env_entries_cache is not None:
            return self._env_entries_cache
        merged: Dict[str, str] = {}
        for env_file in self._env_sources():
            for key, value in self._read_env_entries(env_file).items():
                # Keep the first value found according to source priority.
                if key not in merged:
                    merged[key] = value
        self._env_entries_cache = merged
        return merged

    def _lookup_env_var(self, key: str) -> str:
        value = os.getenv(key)
        if value is not None:
            return value
        return self._env_entries().get(key, "")

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

    def get_model_entry(self, model_id: str) -> Dict[str, Any]:
        data = self._local_configs.get(model_id, {})
        return dict(data) if isinstance(data, dict) else {}

    def default_api_key_env_name(self, model_id: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", model_id).strip("_").upper()
        return f"BETTERCODE_API_KEY_{slug or 'MODEL'}"

    def upsert_api_key_env(self, env_name: str, api_key: str, scope: str = "project") -> Path:
        if scope not in {"project", "global"}:
            raise ValueError("scope must be 'project' or 'global'.")
        env_file = self.local_env_file if scope == "project" else self.global_env_file
        env_file.parent.mkdir(parents=True, exist_ok=True)
        entries = self._read_env_entries(env_file)
        entries[env_name] = api_key
        self._write_env_entries(env_file, entries)
        self._env_entries_cache = None
        os.environ[env_name] = api_key
        return env_file

    def _read_env_entries(self, path: Path) -> Dict[str, str]:
        if not path.is_file():
            return {}
        entries: Dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("export "):
                stripped = stripped[len("export "):].strip()
            if "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            if key:
                entries[key] = value
        return entries

    def _write_env_entries(self, path: Path, entries: Dict[str, str]) -> None:
        lines = [f"{key}={value}" for key, value in sorted(entries.items())]
        content = "\n".join(lines).strip()
        path.write_text(f"{content}\n" if content else "", encoding="utf-8")

    def _resolve_api_key(self, stored_value: Any) -> str:
        raw_value = str(stored_value or "").strip()
        if raw_value.startswith("ENV:"):
            env_name = raw_value.split("ENV:", 1)[1].strip()
            if not env_name:
                raise ValueError("api_key reference is invalid. Expected format: ENV:VAR_NAME")
            resolved = self._lookup_env_var(env_name).strip()
            if not resolved:
                raise ValueError(f"Missing API key environment variable: {env_name}")
            return resolved
        return raw_value

    def get_model_config(self, model_id: str, default_provider: str = "") -> LLMConfig:
        """
        Get config by model_id.
        Prefer exact model_id match from YAML; fall back to environment variables.
        """
        # 1. Prefer persisted YAML config by exact model_id match.
        if model_id in self._local_configs:
            data = self._local_configs[model_id]
            try:
                resolved_api_key = self._resolve_api_key(data.get("api_key", ""))
            except ValueError as error:
                raise RuntimeError(
                    f"Failed to resolve API key for model '{model_id}': {error}"
                ) from error
            return LLMConfig(
                model_id=data.get("model_id", model_id),
                api_key=resolved_api_key,
                base_url=data.get("base_url"),
                provider=data.get("provider", default_provider or "openai")
            )

        # 2. Fall back to env vars (.env or system environment).
        # Use default_provider to choose env prefix; default to OPENAI when absent.
        prefix = default_provider.upper() if default_provider else "OPENAI"
        
        return LLMConfig(
            model_id=self._lookup_env_var(f"{prefix}_MODEL_ID") or model_id,
            api_key=self._lookup_env_var(f"{prefix}_API_KEY"),
            base_url=self._lookup_env_var(f"{prefix}_BASE_URL") or None,
            provider=default_provider or "openai"
        )

# Global singleton manager.
config_manager = LLMConfigManager()
