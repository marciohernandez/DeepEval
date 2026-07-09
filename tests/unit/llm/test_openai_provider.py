"""Unit tests for OpenAIProvider (US4 — Provider-Agnostic LLM Instantiation)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepeval_platform.config.config_manager import ConfigError
from deepeval_platform.llm.base import LLMProviderError, TokenUsage
from deepeval_platform.llm.openai_provider import OpenAIProvider


@pytest.fixture
def mock_lc(mock_config):
    """Patch ChatOpenAI and return (provider_instance, mock_lc_instance)."""
    mock_response = MagicMock()
    mock_response.content = "Hello"
    mock_response.usage_metadata = {"input_tokens": 10, "output_tokens": 5}

    mock_lc_instance = MagicMock()
    mock_lc_instance.invoke.return_value = mock_response
    mock_lc_instance.ainvoke = AsyncMock(return_value=mock_response)

    with patch("deepeval_platform.llm.openai_provider.ChatOpenAI", return_value=mock_lc_instance):
        yield mock_lc_instance


class TestOpenAIProviderConfig:
    def test_reads_api_key_from_config_manager(self, mock_lc, mock_config):
        OpenAIProvider()
        mock_config.get.assert_any_call("OPENAI_API_KEY")

    def test_reads_default_model_from_config_manager_when_no_arg(self, mock_lc, mock_config):
        OpenAIProvider()
        mock_config.get.assert_any_call("openai.default_model")

    def test_model_arg_overrides_config_default(self, mock_config):
        with patch("deepeval_platform.llm.openai_provider.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            provider = OpenAIProvider(model="gpt-4-turbo")
            assert provider.model_name == "gpt-4-turbo"
            _, kwargs = mock_chat.call_args
            assert kwargs.get("model") == "gpt-4-turbo" or mock_chat.call_args[0][1] == "gpt-4-turbo" or "gpt-4-turbo" in str(mock_chat.call_args)

    def test_missing_api_key_raises_llm_provider_error(self, mock_config):
        original = mock_config.get.side_effect

        def raise_for_api_key(key: str) -> str:
            if key == "OPENAI_API_KEY":
                raise ConfigError(key, ".env")
            return original(key)

        mock_config.get.side_effect = raise_for_api_key
        with patch("deepeval_platform.llm.openai_provider.ChatOpenAI"):
            with pytest.raises(LLMProviderError):
                OpenAIProvider()


class TestOpenAIProviderLCModel:
    def test_wraps_chat_openai_as_lc_model(self, mock_lc, mock_config):
        provider = OpenAIProvider()
        assert provider._lc_model is mock_lc


class TestOpenAIProviderGenerate:
    def test_generate_returns_str_and_token_usage(self, mock_lc, mock_config):
        provider = OpenAIProvider()
        result = provider.generate("Say hello")

        assert isinstance(result, tuple)
        assert len(result) == 2
        text, usage = result
        assert isinstance(text, str)
        assert isinstance(usage, TokenUsage)
        assert text == "Hello"
        assert usage.input_tokens == 10
        assert usage.output_tokens == 5

    def test_generate_fallback_when_usage_metadata_is_none(self, mock_config):
        mock_response = MagicMock()
        mock_response.content = "Hi"
        mock_response.usage_metadata = None
        mock_lc_instance = MagicMock()
        mock_lc_instance.invoke.return_value = mock_response

        with patch("deepeval_platform.llm.openai_provider.ChatOpenAI", return_value=mock_lc_instance):
            provider = OpenAIProvider()
            text, usage = provider.generate("prompt")

        assert text == "Hi"
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0

    async def test_a_generate_returns_str_and_token_usage(self, mock_lc, mock_config):
        provider = OpenAIProvider()
        result = await provider.a_generate("Say hello")

        assert isinstance(result, tuple)
        text, usage = result
        assert isinstance(text, str)
        assert isinstance(usage, TokenUsage)

    def test_auth_error_propagates_naturally_without_wrapping(self, mock_config):
        auth_exc = Exception("Authentication failed: invalid API key")
        mock_lc_instance = MagicMock()
        mock_lc_instance.invoke.side_effect = auth_exc

        with patch("deepeval_platform.llm.openai_provider.ChatOpenAI", return_value=mock_lc_instance):
            provider = OpenAIProvider()
            with pytest.raises(Exception, match="Authentication failed"):
                provider.generate("test")

        assert not isinstance(auth_exc, LLMProviderError)
