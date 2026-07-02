"""Integration tests for LLMProviderFactory (US4 — Provider-Agnostic LLM Instantiation).

Requires real API keys in .env:
- OPENAI_API_KEY
- ANTHROPIC_API_KEY
- OPENROUTER_API_KEY

Run with: uv run pytest tests/integration/test_llm_factory_integration.py -v
"""
from __future__ import annotations

import pytest

from deepeval.llm.base import LLMProviderError, TokenUsage
from deepeval.llm.factory import LLMProviderFactory


@pytest.mark.integration
class TestLLMFactoryIntegration:
    def test_openai_provider_executes_real_completion(self):
        provider = LLMProviderFactory.create("openai")
        text, usage = provider.generate("Reply with the single word: PASS")

        assert isinstance(text, str)
        assert len(text) > 0
        assert isinstance(usage, TokenUsage)
        assert usage.input_tokens >= 0
        assert usage.output_tokens >= 0

    def test_anthropic_provider_executes_real_completion(self):
        provider = LLMProviderFactory.create("anthropic")
        text, usage = provider.generate("Reply with the single word: PASS")

        assert isinstance(text, str)
        assert len(text) > 0
        assert isinstance(usage, TokenUsage)

    def test_openrouter_provider_executes_real_completion(self):
        provider = LLMProviderFactory.create("openrouter")
        text, usage = provider.generate("Reply with the single word: PASS")

        assert isinstance(text, str)
        assert len(text) > 0
        assert isinstance(usage, TokenUsage)

    def test_unsupported_provider_error_message_includes_supported_names(self):
        with pytest.raises(LLMProviderError) as exc_info:
            LLMProviderFactory.create("nonexistent")
        msg = str(exc_info.value)
        assert "nonexistent" in msg
        assert "openai" in msg
        assert "anthropic" in msg
        assert "openrouter" in msg
