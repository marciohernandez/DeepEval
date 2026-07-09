"""Unit tests for OpenAIProvider (US4 — Provider-Agnostic LLM Instantiation)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepeval.models.utils import EvaluationCost

from deepeval_platform.config.config_manager import ConfigError
from deepeval_platform.llm.base import LLMProviderError, TokenUsage
from deepeval_platform.llm.openai_provider import OpenAIProvider


@pytest.fixture
def mock_native(mock_config):
    """Patch GPTModel and return the mock native DeepEvalBaseLLM instance."""
    cost = EvaluationCost(0.001, 10, 5)

    mock_instance = MagicMock()
    mock_instance.generate.return_value = ("Hello", cost)
    mock_instance.a_generate = AsyncMock(return_value=("Hello", cost))

    with patch("deepeval_platform.llm.openai_provider.GPTModel", return_value=mock_instance):
        yield mock_instance


class TestOpenAIProviderConfig:
    def test_reads_api_key_from_config_manager(self, mock_native, mock_config):
        OpenAIProvider()
        mock_config.get.assert_any_call("OPENAI_API_KEY")

    def test_reads_default_model_from_config_manager_when_no_arg(self, mock_native, mock_config):
        OpenAIProvider()
        mock_config.get.assert_any_call("openai.default_model")

    def test_model_arg_overrides_config_default(self, mock_config):
        with patch("deepeval_platform.llm.openai_provider.GPTModel") as mock_cls:
            mock_cls.return_value = MagicMock()
            provider = OpenAIProvider(model="gpt-4-turbo")
            assert provider.model_name == "gpt-4-turbo"
            _, kwargs = mock_cls.call_args
            assert kwargs.get("model") == "gpt-4-turbo"

    def test_missing_api_key_raises_llm_provider_error(self, mock_config):
        original = mock_config.get.side_effect

        def raise_for_api_key(key: str) -> str:
            if key == "OPENAI_API_KEY":
                raise ConfigError(key, ".env")
            return original(key)

        mock_config.get.side_effect = raise_for_api_key
        with patch("deepeval_platform.llm.openai_provider.GPTModel"):
            with pytest.raises(LLMProviderError):
                OpenAIProvider()


class TestOpenAIProviderNativeModel:
    def test_wraps_gpt_model_as_native(self, mock_native, mock_config):
        provider = OpenAIProvider()
        assert provider._native is mock_native

    def test_as_deepeval_model_returns_native_instance(self, mock_native, mock_config):
        provider = OpenAIProvider()
        assert provider.as_deepeval_model() is mock_native


class TestOpenAIProviderGenerate:
    def test_generate_returns_str_and_token_usage(self, mock_native, mock_config):
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

    def test_generate_fallback_when_cost_is_none(self, mock_config):
        mock_instance = MagicMock()
        mock_instance.generate.return_value = ("Hi", None)

        with patch("deepeval_platform.llm.openai_provider.GPTModel", return_value=mock_instance):
            provider = OpenAIProvider()
            text, usage = provider.generate("prompt")

        assert text == "Hi"
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0

    async def test_a_generate_returns_str_and_token_usage(self, mock_native, mock_config):
        provider = OpenAIProvider()
        result = await provider.a_generate("Say hello")

        assert isinstance(result, tuple)
        text, usage = result
        assert isinstance(text, str)
        assert isinstance(usage, TokenUsage)

    def test_auth_error_propagates_naturally_without_wrapping(self, mock_config):
        auth_exc = Exception("Authentication failed: invalid API key")
        mock_instance = MagicMock()
        mock_instance.generate.side_effect = auth_exc

        with patch("deepeval_platform.llm.openai_provider.GPTModel", return_value=mock_instance):
            provider = OpenAIProvider()
            with pytest.raises(Exception, match="Authentication failed"):
                provider.generate("test")

        assert not isinstance(auth_exc, LLMProviderError)
