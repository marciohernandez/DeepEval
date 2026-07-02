"""LLMProviderBase ABC and shared types for US4 — Provider-Agnostic LLM Instantiation.

T036a findings (deepeval 4.0.7):
- DeepEvalBaseLLM.generate() returns str with no native TokenUsage type.
- The installed 'deepeval' package is shadowed by the local 'deepeval/' directory,
  making formal inheritance from DeepEvalBaseLLM impossible without path manipulation.
- LLMProviderBase independently implements the same interface contract.
  TokenUsage is defined here as a project-local dataclass.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int


class LLMProviderError(Exception):
    pass


class LLMProviderBase(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def generate(self, prompt: str) -> tuple[str, TokenUsage]: ...

    @abstractmethod
    async def a_generate(self, prompt: str) -> tuple[str, TokenUsage]: ...

    def get_model_name(self) -> str:
        return self.model_name

    def _extract_usage(self, response) -> TokenUsage:
        usage = response.usage_metadata
        if usage is None:
            return TokenUsage(input_tokens=0, output_tokens=0)
        return TokenUsage(
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
        )
