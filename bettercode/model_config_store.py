from __future__ import annotations

import os

from PySide6.QtCore import QSettings

from bettercode.llm.config import LLMConfig
from bettercode.llm.config_manager import config_manager
from bettercode.translation_executor import DEFAULT_MODEL_API_URL, DEFAULT_MODEL_NAME, DEFAULT_TIMEOUT_SECONDS, ModelConfig

_SETTINGS_PREFIX = "translation_model"


def load_model_config() -> ModelConfig:
    settings = QSettings()

    model_name = (
        os.environ.get("BETTERCODE_MODEL_NAME")
        or _read_setting(settings, "model_name")
        or DEFAULT_MODEL_NAME
    )
    timeout_raw = (
        os.environ.get("BETTERCODE_MODEL_TIMEOUT_SECONDS")
        or _read_setting(settings, "timeout_seconds")
        or str(DEFAULT_TIMEOUT_SECONDS)
    )
    timeout_seconds = _parse_timeout(timeout_raw)

    # Prefer the new unified LLM config path (YAML + .env references).
    llm_api_url = ""
    llm_api_key = ""
    try:
        llm_config = config_manager.get_model_config(model_name)
        llm_api_url = (llm_config.base_url or "").strip()
        llm_api_key = llm_config.api_key.strip()
    except Exception:
        llm_api_url = ""
        llm_api_key = ""

    api_url = (
        os.environ.get("BETTERCODE_MODEL_API_URL")
        or _read_setting(settings, "api_url")
        or llm_api_url
        or DEFAULT_MODEL_API_URL
    )
    api_token = (
        os.environ.get("BETTERCODE_MODEL_API_TOKEN")
        or os.environ.get("API_TOKEN")
        or llm_api_key
        or _read_setting(settings, "api_token")
        or ""
    )

    return ModelConfig(
        api_url=api_url.strip(),
        api_token=api_token.strip(),
        model_name=model_name.strip(),
        timeout_seconds=timeout_seconds,
    )


def save_model_config(config: ModelConfig) -> None:
    settings = QSettings()

    model_id = config.model_name.strip()
    api_url = config.api_url.strip() or None
    api_token = config.api_token.strip()

    # Persist UI state for convenience.
    settings.setValue(f"{_SETTINGS_PREFIX}/api_url", config.api_url)
    settings.setValue(f"{_SETTINGS_PREFIX}/model_name", config.model_name)
    settings.setValue(f"{_SETTINGS_PREFIX}/timeout_seconds", str(config.timeout_seconds))
    # Avoid storing plaintext API keys in QSettings.
    settings.setValue(f"{_SETTINGS_PREFIX}/api_token", "")
    settings.sync()

    if not model_id:
        return

    existing_entry = config_manager.get_model_entry(model_id)
    api_key_ref = str(existing_entry.get("api_key", "")).strip()
    if api_token:
        env_name = config_manager.default_api_key_env_name(model_id)
        config_manager.upsert_api_key_env(env_name, api_token, scope="project")
        api_key_ref = f"ENV:{env_name}"
    elif not api_key_ref:
        # Keep legacy behavior when users only save URL/name without entering key.
        api_key_ref = ""

    provider = _infer_provider(api_url=api_url or "", model_id=model_id)
    updated_config = LLMConfig(
        model_id=model_id,
        api_key=api_key_ref,
        base_url=api_url,
        provider=provider,
    )
    config_manager.save_config(updated_config)


def _read_setting(settings: QSettings, name: str) -> str:
    value = settings.value(f"{_SETTINGS_PREFIX}/{name}", "")
    return str(value) if value is not None else ""


def _parse_timeout(raw_value: str) -> float:
    try:
        return float(raw_value)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def _infer_provider(*, api_url: str, model_id: str) -> str:
    lower_url = api_url.lower()
    lower_model = model_id.lower()
    if "anthropic" in lower_url or lower_model.startswith("claude"):
        return "anthropic"
    return "openai"
