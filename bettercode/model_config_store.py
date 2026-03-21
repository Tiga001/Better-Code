from __future__ import annotations

import os

from PySide6.QtCore import QSettings

from bettercode.translation_executor import DEFAULT_MODEL_API_URL, DEFAULT_MODEL_NAME, DEFAULT_TIMEOUT_SECONDS, ModelConfig

_SETTINGS_PREFIX = "translation_model"


def load_model_config() -> ModelConfig:
    settings = QSettings()

    api_url = (
        os.environ.get("BETTERCODE_MODEL_API_URL")
        or _read_setting(settings, "api_url")
        or DEFAULT_MODEL_API_URL
    )
    model_name = (
        os.environ.get("BETTERCODE_MODEL_NAME")
        or _read_setting(settings, "model_name")
        or DEFAULT_MODEL_NAME
    )
    api_token = (
        os.environ.get("BETTERCODE_MODEL_API_TOKEN")
        or os.environ.get("API_TOKEN")
        or _read_setting(settings, "api_token")
        or ""
    )
    timeout_raw = (
        os.environ.get("BETTERCODE_MODEL_TIMEOUT_SECONDS")
        or _read_setting(settings, "timeout_seconds")
        or str(DEFAULT_TIMEOUT_SECONDS)
    )
    timeout_seconds = _parse_timeout(timeout_raw)
    return ModelConfig(
        api_url=api_url.strip(),
        api_token=api_token.strip(),
        model_name=model_name.strip(),
        timeout_seconds=timeout_seconds,
    )


def save_model_config(config: ModelConfig) -> None:
    settings = QSettings()
    settings.setValue(f"{_SETTINGS_PREFIX}/api_url", config.api_url)
    settings.setValue(f"{_SETTINGS_PREFIX}/api_token", config.api_token)
    settings.setValue(f"{_SETTINGS_PREFIX}/model_name", config.model_name)
    settings.setValue(f"{_SETTINGS_PREFIX}/timeout_seconds", str(config.timeout_seconds))
    settings.sync()


def _read_setting(settings: QSettings, name: str) -> str:
    value = settings.value(f"{_SETTINGS_PREFIX}/{name}", "")
    return str(value) if value is not None else ""


def _parse_timeout(raw_value: str) -> float:
    try:
        return float(raw_value)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
