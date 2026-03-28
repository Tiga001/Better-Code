from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

if "anthropic" not in sys.modules:
    anthropic_module = types.ModuleType("anthropic")

    class AsyncAnthropic:  # pragma: no cover - simple import stub
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    anthropic_module.AsyncAnthropic = AsyncAnthropic
    sys.modules["anthropic"] = anthropic_module

if "openai" not in sys.modules:
    openai_module = types.ModuleType("openai")

    class AsyncOpenAI:  # pragma: no cover - simple import stub
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    openai_module.AsyncOpenAI = AsyncOpenAI
    sys.modules["openai"] = openai_module

from bettercode.llm import factory
from bettercode.llm.anthropic_client import AnthropicClient
from bettercode.llm.config_manager import LLMConfigManager
from bettercode.llm.openai_client import OpenAIClient


@contextmanager
def working_directory(path: Path):
    previous_cwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous_cwd)


class LLMFactoryTests(unittest.TestCase):
    def _build_config_manager(self, yaml_text: str) -> LLMConfigManager:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)

        root = Path(temporary_directory.name)
        config_file = root / "bettercode" / "config" / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(textwrap.dedent(yaml_text).strip() + "\n", encoding="utf-8")

        with working_directory(root):
            return LLMConfigManager()

    def test_create_llm_client_reads_yaml_and_instantiates_anthropic_client(self) -> None:
        manager = self._build_config_manager(
            """
            claude-3-5-sonnet:
              model_id: claude-3-5-sonnet
              provider: anthropic
              api_key: test-anthropic-key
              base_url: https://api.anthropic.example
            """
        )

        with patch.object(factory, "config_manager", manager):
            client = factory.create_llm_client("claude-3-5-sonnet")

        self.assertIsInstance(client, AnthropicClient)
        self.assertEqual(client.config.model_id, "claude-3-5-sonnet")
        self.assertEqual(client.config.provider, "anthropic")
        self.assertEqual(client.config.api_key, "test-anthropic-key")
        self.assertEqual(client.config.base_url, "https://api.anthropic.example")

    def test_create_llm_client_reads_yaml_and_instantiates_openai_client(self) -> None:
        manager = self._build_config_manager(
            """
            gpt-4o-mini:
              model_id: gpt-4o-mini
              provider: openai
              api_key: test-openai-key
              base_url: https://api.openai.example/v1
            """
        )

        with patch.object(factory, "config_manager", manager):
            client = factory.create_llm_client("gpt-4o-mini")

        self.assertIsInstance(client, OpenAIClient)
        self.assertEqual(client.config.model_id, "gpt-4o-mini")
        self.assertEqual(client.config.provider, "openai")
        self.assertEqual(client.config.api_key, "test-openai-key")
        self.assertEqual(client.config.base_url, "https://api.openai.example/v1")

    def test_config_manager_does_not_mutate_os_environ_on_init_but_can_resolve_env_reference(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)

        root = Path(temporary_directory.name)
        (root / "bettercode" / "config").mkdir(parents=True, exist_ok=True)
        (root / "bettercode" / "config" / "config.yaml").write_text(
            textwrap.dedent(
                """
                gpt-4o-mini:
                  model_id: gpt-4o-mini
                  provider: openai
                  api_key: ENV:BETTERCODE_API_KEY_GPT_4O_MINI
                  base_url: https://api.openai.example/v1
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        (root / ".env").write_text("BETTERCODE_API_KEY_GPT_4O_MINI=from-dot-env\n", encoding="utf-8")

        original = os.environ.pop("BETTERCODE_API_KEY_GPT_4O_MINI", None)
        self.addCleanup(
            lambda: (
                os.environ.pop("BETTERCODE_API_KEY_GPT_4O_MINI", None)
                if original is None
                else os.environ.__setitem__("BETTERCODE_API_KEY_GPT_4O_MINI", original)
            )
        )

        with working_directory(root):
            manager = LLMConfigManager()
            self.assertNotIn("BETTERCODE_API_KEY_GPT_4O_MINI", os.environ)
            config = manager.get_model_config("gpt-4o-mini")

        self.assertEqual(config.api_key, "from-dot-env")
