"""LLMProviderBase ABC and shared types for US4 — Provider-Agnostic LLM Instantiation.

Post-M2.1 note: concrete providers wrap DeepEval's own DeepEvalBaseLLM model classes
(GPTModel, AnthropicModel, OpenRouterModel from `deepeval.models`) instead of LangChain
chat models, per constitution Principle II (DeepEval-First) — these classes already exist
natively for the judge-model role. This ABC's own contract (generate()->tuple[str,
TokenUsage], provider_name/model_name properties) is kept stable so nothing above it needs
to change; only each provider's internals were swapped. Formerly (T036a, pre-rename) this
was impossible because the local `deepeval/` package shadowed the installed library — fixed
by renaming the project's package to `deepeval_platform/`.
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

    def as_deepeval_model(self):
        """Return the underlying DeepEvalBaseLLM instance for direct use as a metric judge
        (e.g. `AnswerRelevancyMetric(model=provider.as_deepeval_model())`)."""
        return self._native

    @staticmethod
    def _to_token_usage(cost) -> TokenUsage:
        """Convert a DeepEval EvaluationCost (or None, when pricing is unknown) to TokenUsage."""
        if cost is None:
            return TokenUsage(input_tokens=0, output_tokens=0)
        return TokenUsage(
            input_tokens=getattr(cost, "input_tokens", None) or 0,
            output_tokens=getattr(cost, "output_tokens", None) or 0,
        )
