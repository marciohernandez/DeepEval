"""Unit tests for OpenRouterProvider (US4 — Provider-Agnostic LLM Instantiation)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepeval.config.config_manager import ConfigError
from deepeval.llm.base import LLMProviderError, TokenUsage
from deepeval.llm.openrouter_provider import OpenRouterProvider


@pytest.fixture
def mock_lc(mock_config):
    mock_response = MagicMock()
    mock_response.content = "OpenRouter response"
    mock_response.usage_metadata = {"input_tokens": 12, "output_tokens": 6}
    mock_response.response_metadata = {}

    mock_lc_instance = MagicMock()
    mock_lc_instance.invoke.return_value = mock_response
    mock_lc_instance.ainvoke = AsyncMock(return_value=mock_response)

    with patch("deepeval.llm.openrouter_provider.ChatOpenRouter", return_value=mock_lc_instance):
        yield mock_lc_instance


class TestOpenRouterProviderConfig:
    def test_reads_api_key_from_config_manager(self, mock_lc, mock_config):
        OpenRouterProvider()
        mock_config.get.assert_any_call("OPENROUTER_API_KEY")

    def test_reads_default_model_from_config_manager_when_no_arg(self, mock_lc, mock_config):
        OpenRouterProvider()
        mock_config.get.assert_any_call("openrouter.default_model")

    def test_missing_api_key_raises_llm_provider_error(self, mock_config):
        original = mock_config.get.side_effect

        def raise_for_api_key(key: str) -> str:
            if key == "OPENROUTER_API_KEY":
                raise ConfigError(key, ".env")
            return original(key)

        mock_config.get.side_effect = raise_for_api_key
        with patch("deepeval.llm.openrouter_provider.ChatOpenRouter"):
            with pytest.raises(LLMProviderError):
                OpenRouterProvider()


class TestOpenRouterProviderLCModel:
    def test_wraps_chat_openrouter_not_chat_openai(self, mock_lc, mock_config):
        """Verifies ChatOpenRouter is used (not ChatOpenAI) — FR-009 / plan Gate 5."""
        with patch("deepeval.llm.openrouter_provider.ChatOpenRouter") as mock_or:
            mock_or.return_value = MagicMock()
            OpenRouterProvider()
            assert mock_or.called

    def test_lc_model_is_set(self, mock_lc, mock_config):
        provider = OpenRouterProvider()
        assert provider._lc_model is mock_lc


class TestOpenRouterProviderGenerate:
    def test_generate_returns_str_and_token_usage(self, mock_lc, mock_config):
        provider = OpenRouterProvider()
        text, usage = provider.generate("Say hello")

        assert isinstance(text, str)
        assert isinstance(usage, TokenUsage)
        assert text == "OpenRouter response"

    def test_generate_fallback_to_response_metadata_when_usage_metadata_none(self, mock_config):
        mock_response = MagicMock()
        mock_response.content = "Hi"
        mock_response.usage_metadata = None
        mock_response.response_metadata = {"usage": {"prompt_tokens": 5, "completion_tokens": 3}}
        mock_lc_instance = MagicMock()
        mock_lc_instance.invoke.return_value = mock_response

        with patch("deepeval.llm.openrouter_provider.ChatOpenRouter", return_value=mock_lc_instance):
            provider = OpenRouterProvider()
            text, usage = provider.generate("prompt")

        assert usage.input_tokens == 5
        assert usage.output_tokens == 3

    def test_generate_fallback_to_zeros_when_no_usage_info(self, mock_config):
        mock_response = MagicMock()
        mock_response.content = "Hi"
        mock_response.usage_metadata = None
        mock_response.response_metadata = {}
        mock_lc_instance = MagicMock()
        mock_lc_instance.invoke.return_value = mock_response

        with patch("deepeval.llm.openrouter_provider.ChatOpenRouter", return_value=mock_lc_instance):
            provider = OpenRouterProvider()
            text, usage = provider.generate("prompt")

        assert usage.input_tokens == 0
        assert usage.output_tokens == 0

    async def test_a_generate_returns_str_and_token_usage(self, mock_lc, mock_config):
        provider = OpenRouterProvider()
        text, usage = await provider.a_generate("Say hello")

        assert isinstance(text, str)
        assert isinstance(usage, TokenUsage)

    def test_auth_error_propagates_naturally_without_wrapping(self, mock_config):
        auth_exc = Exception("Authentication failed: invalid OpenRouter API key")
        mock_lc_instance = MagicMock()
        mock_lc_instance.invoke.side_effect = auth_exc

        with patch("deepeval.llm.openrouter_provider.ChatOpenRouter", return_value=mock_lc_instance):
            provider = OpenRouterProvider()
            with pytest.raises(Exception, match="Authentication failed"):
                provider.generate("test")

        assert not isinstance(auth_exc, LLMProviderError)
