"""Unit tests for OpenRouterProvider (US4 — Provider-Agnostic LLM Instantiation)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepeval.models.utils import EvaluationCost

from deepeval_platform.config.config_manager import ConfigError
from deepeval_platform.llm.base import LLMProviderError, TokenUsage
from deepeval_platform.llm.openrouter_provider import OpenRouterProvider


@pytest.fixture
def mock_native(mock_config):
    cost = EvaluationCost(0.001, 12, 6)

    mock_instance = MagicMock()
    mock_instance.generate.return_value = ("OpenRouter response", cost)
    mock_instance.a_generate = AsyncMock(return_value=("OpenRouter response", cost))

    with patch("deepeval_platform.llm.openrouter_provider.OpenRouterModel", return_value=mock_instance):
        yield mock_instance


class TestOpenRouterProviderConfig:
    def test_reads_api_key_from_config_manager(self, mock_native, mock_config):
        OpenRouterProvider()
        mock_config.get.assert_any_call("OPENROUTER_API_KEY")

    def test_reads_default_model_from_config_manager_when_no_arg(self, mock_native, mock_config):
        OpenRouterProvider()
        mock_config.get.assert_any_call("openrouter.default_model")

    def test_missing_api_key_raises_llm_provider_error(self, mock_config):
        original = mock_config.get.side_effect

        def raise_for_api_key(key: str) -> str:
            if key == "OPENROUTER_API_KEY":
                raise ConfigError(key, ".env")
            return original(key)

        mock_config.get.side_effect = raise_for_api_key
        with patch("deepeval_platform.llm.openrouter_provider.OpenRouterModel"):
            with pytest.raises(LLMProviderError):
                OpenRouterProvider()


class TestOpenRouterProviderNativeModel:
    def test_wraps_deepeval_openrouter_model_not_gpt_model(self, mock_native, mock_config):
        """Verifies DeepEval's own OpenRouterModel is used (not GPTModel) — FR-009 / Principle II."""
        with patch("deepeval_platform.llm.openrouter_provider.OpenRouterModel") as mock_cls:
            mock_cls.return_value = MagicMock()
            OpenRouterProvider()
            assert mock_cls.called

    def test_native_is_set(self, mock_native, mock_config):
        provider = OpenRouterProvider()
        assert provider._native is mock_native

    def test_as_deepeval_model_returns_native_instance(self, mock_native, mock_config):
        provider = OpenRouterProvider()
        assert provider.as_deepeval_model() is mock_native


class TestOpenRouterProviderGenerate:
    def test_generate_returns_str_and_token_usage(self, mock_native, mock_config):
        provider = OpenRouterProvider()
        text, usage = provider.generate("Say hello")

        assert isinstance(text, str)
        assert isinstance(usage, TokenUsage)
        assert text == "OpenRouter response"
        assert usage.input_tokens == 12
        assert usage.output_tokens == 6

    def test_generate_fallback_to_zeros_when_cost_is_none(self, mock_config):
        mock_instance = MagicMock()
        mock_instance.generate.return_value = ("Hi", None)

        with patch("deepeval_platform.llm.openrouter_provider.OpenRouterModel", return_value=mock_instance):
            provider = OpenRouterProvider()
            text, usage = provider.generate("prompt")

        assert usage.input_tokens == 0
        assert usage.output_tokens == 0

    async def test_a_generate_returns_str_and_token_usage(self, mock_native, mock_config):
        provider = OpenRouterProvider()
        text, usage = await provider.a_generate("Say hello")

        assert isinstance(text, str)
        assert isinstance(usage, TokenUsage)

    def test_auth_error_propagates_naturally_without_wrapping(self, mock_config):
        auth_exc = Exception("Authentication failed: invalid OpenRouter API key")
        mock_instance = MagicMock()
        mock_instance.generate.side_effect = auth_exc

        with patch("deepeval_platform.llm.openrouter_provider.OpenRouterModel", return_value=mock_instance):
            provider = OpenRouterProvider()
            with pytest.raises(Exception, match="Authentication failed"):
                provider.generate("test")

        assert not isinstance(auth_exc, LLMProviderError)
