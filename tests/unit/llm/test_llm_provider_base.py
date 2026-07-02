"""Unit tests for LLMProviderBase ABC (US4 — Provider-Agnostic LLM Instantiation)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from deepeval.llm.base import LLMProviderBase, LLMProviderError, TokenUsage


class TestLLMProviderBaseIsABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            LLMProviderBase()  # type: ignore[abstract]

    def test_abstract_provider_name_enforced(self):
        class MissingProviderName(LLMProviderBase):
            @property
            def model_name(self) -> str:
                return "x"

            def generate(self, prompt: str) -> tuple[str, TokenUsage]:
                return ("", TokenUsage(0, 0))

            async def a_generate(self, prompt: str) -> tuple[str, TokenUsage]:
                return ("", TokenUsage(0, 0))

        with pytest.raises(TypeError):
            MissingProviderName()

    def test_abstract_model_name_enforced(self):
        class MissingModelName(LLMProviderBase):
            @property
            def provider_name(self) -> str:
                return "x"

            def generate(self, prompt: str) -> tuple[str, TokenUsage]:
                return ("", TokenUsage(0, 0))

            async def a_generate(self, prompt: str) -> tuple[str, TokenUsage]:
                return ("", TokenUsage(0, 0))

        with pytest.raises(TypeError):
            MissingModelName()


class TestGetModelName:
    def test_delegates_to_model_name_property(self):
        class StubProvider(LLMProviderBase):
            @property
            def provider_name(self) -> str:
                return "stub"

            @property
            def model_name(self) -> str:
                return "stub-model-v1"

            def generate(self, prompt: str) -> tuple[str, TokenUsage]:
                return ("ok", TokenUsage(1, 1))

            async def a_generate(self, prompt: str) -> tuple[str, TokenUsage]:
                return ("ok", TokenUsage(1, 1))

        inst = StubProvider()
        assert inst.get_model_name() == "stub-model-v1"
