"""
Public interface contracts for LLMProviderBase and LLMProviderFactory.

This file is a CONTRACT SPECIFICATION, not implementation.

Correction (pós-M2.1, constitution v1.2.0): the original text below described providers as
LangChain chat-model wrappers implementing DeepEvalBaseLLM directly. Neither is accurate to the
shipped implementation as of commit `3455bfd`:
  - OpenAIProvider wraps deepeval.models.GPTModel (NOT ChatOpenAI/langchain-openai)
  - AnthropicProvider wraps deepeval.models.AnthropicModel (NOT ChatAnthropic/langchain-anthropic)
  - OpenRouterProvider wraps deepeval.models.OpenRouterModel (NOT ChatOpenRouter/langchain-openrouter)
  - LLMProviderBase does NOT implement DeepEvalBaseLLM directly (return-type contracts diverge);
    each provider exposes as_deepeval_model() -> DeepEvalBaseLLM for metric judging instead.
See constitution.md Principle II (DeepEval-First) and tech_stack.md §2.8 for the current design.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

# In production code:
# from deepeval.models import DeepEvalBaseLLM, GPTModel, AnthropicModel, OpenRouterModel

SupportedProvider = Literal["openai", "anthropic", "openrouter"]

SUPPORTED_PROVIDERS: tuple[str, ...] = ("openai", "anthropic", "openrouter")


class LLMProviderBaseContract(ABC):
    """
    Abstract base for all LLM providers. Does NOT implement DeepEvalBaseLLM directly
    (see module docstring) — exposes as_deepeval_model() instead.

    Subclasses must:
    1. Source all credentials and config from ConfigManager (FR-011).
    2. Hold an internal _native (DeepEval's own DeepEvalBaseLLM model instance, e.g.
       GPTModel/AnthropicModel/OpenRouterModel) for judge-model use.
    3. Implement generate() and a_generate() by delegating to _native and converting its
       EvaluationCost return value to this project's TokenUsage.
    4. Implement as_deepeval_model() returning _native, for direct use in Metric(model=...).

    ConfigManager keys by provider:
        openai:      OPENAI_API_KEY, OPENAI_DEFAULT_MODEL
        anthropic:   ANTHROPIC_API_KEY, ANTHROPIC_DEFAULT_MODEL
        openrouter:  OPENROUTER_API_KEY, OPENROUTER_DEFAULT_MODEL

    Adding a new provider = new subclass only. No changes to factory or callers (SC-006).
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier string (e.g., 'openai')."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier (e.g., 'gpt-4o-mini')."""
        ...

    @abstractmethod
    def generate(self, prompt: str) -> tuple[str, "TokenUsage"]:  # type: ignore[name-defined]
        """Generate a completion. Required by DeepEvalBaseLLM."""
        ...

    @abstractmethod
    async def a_generate(self, prompt: str) -> tuple[str, "TokenUsage"]:  # type: ignore[name-defined]
        """Async generate. Required by DeepEvalBaseLLM."""
        ...

    def get_model_name(self) -> str:
        """Return model_name. Required by DeepEvalBaseLLM."""
        return self.model_name


class LLMProviderFactoryContract:
    """
    Factory Method. Instantiates the correct LLMProviderBase subclass.

    Providers are registered in _registry: dict[str, type[LLMProviderBase]].
    Adding a new provider requires only registering a new subclass.

    Usage:
        from deepeval_platform.llm import LLMProviderFactory
        provider = LLMProviderFactory.create("openai")
        provider = LLMProviderFactory.create("anthropic", model="claude-sonnet-4-6")
        provider = LLMProviderFactory.create("openrouter")
    """

    @classmethod
    def create(
        cls,
        provider: str,
        model: str | None = None,
    ) -> LLMProviderBaseContract:
        """
        Instantiate and return the provider for `provider`.

        If `model` is None, uses the provider's default from ConfigManager.

        Raises:
            LLMProviderError: if `provider` is unsupported (names supported options).
            LLMProviderError: if required API key is missing from ConfigManager.
        """
        ...

    @classmethod
    def supported_providers(cls) -> tuple[str, ...]:
        """Return tuple of registered provider names."""
        ...


class LLMProviderError(Exception):
    """Raised on unsupported provider or missing credentials."""
