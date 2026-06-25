"""
Public interface contracts for LLMProviderBase and LLMProviderFactory.

This file is a CONTRACT SPECIFICATION, not implementation.

LangChain-first:
  - OpenAIProvider wraps ChatOpenAI (langchain-openai)
  - AnthropicProvider wraps ChatAnthropic (langchain-anthropic)
  - OpenRouterProvider wraps ChatOpenRouter (langchain-openrouter)
  - Each provider implements DeepEvalBaseLLM for metric judging (FR-010)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

# In production code:
# from deepeval.models import DeepEvalBaseLLM
# from langchain_core.language_models import BaseChatModel

SupportedProvider = Literal["openai", "anthropic", "openrouter"]

SUPPORTED_PROVIDERS: tuple[str, ...] = ("openai", "anthropic", "openrouter")


class LLMProviderBaseContract(ABC):
    """
    Abstract base for all LLM providers. Implements DeepEvalBaseLLM.

    Subclasses must:
    1. Source all credentials and config from ConfigManager (FR-011).
    2. Hold an internal _lc_model (LangChain BaseChatModel) for orchestration use.
    3. Implement DeepEvalBaseLLM.generate() and DeepEvalBaseLLM.a_generate()
       by delegating to _lc_model.

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
        from deepeval.llm import LLMProviderFactory
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
