"""Unit tests for AnthropicProvider (US4 — Provider-Agnostic LLM Instantiation)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepeval.config.config_manager import ConfigError
from deepeval.llm.base import LLMProviderError, TokenUsage
from deepeval.llm.anthropic_provider import AnthropicProvider


@pytest.fixture
def mock_lc(mock_config):
    mock_response = MagicMock()
    mock_response.content = "Claude says hello"
    mock_response.usage_metadata = {"input_tokens": 8, "output_tokens": 4}

    mock_lc_instance = MagicMock()
    mock_lc_instance.invoke.return_value = mock_response
    mock_lc_instance.ainvoke = AsyncMock(return_value=mock_response)

    with patch("deepeval.llm.anthropic_provider.ChatAnthropic", return_value=mock_lc_instance):
        yield mock_lc_instance


class TestAnthropicProviderConfig:
    def test_reads_api_key_from_config_manager(self, mock_lc, mock_config):
        AnthropicProvider()
        mock_config.get.assert_any_call("ANTHROPIC_API_KEY")

    def test_reads_default_model_from_config_manager_when_no_arg(self, mock_lc, mock_config):
        AnthropicProvider()
        mock_config.get.assert_any_call("anthropic.default_model")

    def test_missing_api_key_raises_llm_provider_error(self, mock_config):
        original = mock_config.get.side_effect

        def raise_for_api_key(key: str) -> str:
            if key == "ANTHROPIC_API_KEY":
                raise ConfigError(key, ".env")
            return original(key)

        mock_config.get.side_effect = raise_for_api_key
        with patch("deepeval.llm.anthropic_provider.ChatAnthropic"):
            with pytest.raises(LLMProviderError):
                AnthropicProvider()


class TestAnthropicProviderLCModel:
    def test_wraps_chat_anthropic_as_lc_model(self, mock_lc, mock_config):
        provider = AnthropicProvider()
        assert provider._lc_model is mock_lc


class TestAnthropicProviderGenerate:
    def test_generate_returns_str_and_token_usage(self, mock_lc, mock_config):
        provider = AnthropicProvider()
        text, usage = provider.generate("Say hello")

        assert isinstance(text, str)
        assert isinstance(usage, TokenUsage)
        assert text == "Claude says hello"
        assert usage.input_tokens == 8
        assert usage.output_tokens == 4

    async def test_a_generate_returns_str_and_token_usage(self, mock_lc, mock_config):
        provider = AnthropicProvider()
        text, usage = await provider.a_generate("Say hello")

        assert isinstance(text, str)
        assert isinstance(usage, TokenUsage)

    def test_auth_error_propagates_naturally_without_wrapping(self, mock_config):
        auth_exc = Exception("Authentication failed: invalid Anthropic API key")
        mock_lc_instance = MagicMock()
        mock_lc_instance.invoke.side_effect = auth_exc

        with patch("deepeval.llm.anthropic_provider.ChatAnthropic", return_value=mock_lc_instance):
            provider = AnthropicProvider()
            with pytest.raises(Exception, match="Authentication failed"):
                provider.generate("test")

        assert not isinstance(auth_exc, LLMProviderError)
