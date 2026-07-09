"""Unit tests for LLMProviderFactory (US4 — Provider-Agnostic LLM Instantiation)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from deepeval_platform.llm.base import LLMProviderBase, LLMProviderError, TokenUsage
from deepeval_platform.llm.factory import LLMProviderFactory
from deepeval_platform.llm.openai_provider import OpenAIProvider
from deepeval_platform.llm.anthropic_provider import AnthropicProvider
from deepeval_platform.llm.openrouter_provider import OpenRouterProvider


@pytest.fixture(autouse=True)
def patch_all_native_models(mock_config):
    """Patch all DeepEval native model classes so no real network calls happen."""
    with patch("deepeval_platform.llm.openai_provider.GPTModel", return_value=MagicMock()):
        with patch("deepeval_platform.llm.anthropic_provider.AnthropicModel", return_value=MagicMock()):
            with patch("deepeval_platform.llm.openrouter_provider.OpenRouterModel", return_value=MagicMock()):
                yield


class TestLLMProviderFactoryCreate:
    def test_create_openai_returns_openai_provider(self):
        provider = LLMProviderFactory.create("openai")
        assert isinstance(provider, OpenAIProvider)

    def test_create_anthropic_returns_anthropic_provider(self):
        provider = LLMProviderFactory.create("anthropic")
        assert isinstance(provider, AnthropicProvider)

    def test_create_openrouter_returns_openrouter_provider(self):
        provider = LLMProviderFactory.create("openrouter")
        assert isinstance(provider, OpenRouterProvider)

    def test_create_unsupported_raises_llm_provider_error(self):
        with pytest.raises(LLMProviderError) as exc_info:
            LLMProviderFactory.create("unsupported-provider")
        msg = str(exc_info.value)
        assert "unsupported-provider" in msg
        assert any(p in msg for p in ("openai", "anthropic", "openrouter"))

    def test_create_unsupported_lists_supported_providers(self):
        with pytest.raises(LLMProviderError) as exc_info:
            LLMProviderFactory.create("grok")
        msg = str(exc_info.value)
        for name in ("openai", "anthropic", "openrouter"):
            assert name in msg


class TestLLMProviderFactoryModelOverride:
    def test_model_arg_overrides_config_default_for_openai(self):
        with patch("deepeval_platform.llm.openai_provider.GPTModel") as mock_cls:
            mock_cls.return_value = MagicMock()
            provider = LLMProviderFactory.create("openai", model="gpt-4-turbo")
            assert provider.model_name == "gpt-4-turbo"


class TestLLMProviderFactoryExtensibility:
    def test_register_and_create_new_provider(self):
        """SC-006: zero changes to LLMProviderFactory required for a new provider."""

        class MockProvider(LLMProviderBase):
            def __init__(self, model: str | None = None) -> None:
                self._model = model or "mock-default"

            @property
            def provider_name(self) -> str:
                return "mock"

            @property
            def model_name(self) -> str:
                return self._model

            def generate(self, prompt: str) -> tuple[str, TokenUsage]:
                return ("mock-response", TokenUsage(1, 1))

            async def a_generate(self, prompt: str) -> tuple[str, TokenUsage]:
                return ("mock-response", TokenUsage(1, 1))

        LLMProviderFactory.register("mock", MockProvider)
        try:
            result = LLMProviderFactory.create("mock")
            assert isinstance(result, MockProvider)
        finally:
            LLMProviderFactory._registry.pop("mock", None)

    def test_supported_providers_returns_all_registered(self):
        supported = LLMProviderFactory.supported_providers()
        assert "openai" in supported
        assert "anthropic" in supported
        assert "openrouter" in supported
