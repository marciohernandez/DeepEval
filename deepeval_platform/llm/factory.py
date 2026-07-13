"""LLMProviderFactory — creates LLM provider instances by name (US4)."""
from __future__ import annotations

from typing import ClassVar

from deepeval_platform.llm.base import LLMProviderBase, LLMProviderError
from deepeval_platform.llm.anthropic_provider import AnthropicProvider
from deepeval_platform.llm.openai_provider import OpenAIProvider
from deepeval_platform.llm.openrouter_provider import OpenRouterProvider


class LLMProviderFactory:
    _registry: ClassVar[dict[str, type[LLMProviderBase]]] = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "openrouter": OpenRouterProvider,
    }

    @classmethod
    def create(cls, provider: str, model: str | None = None) -> LLMProviderBase:
        if provider not in cls._registry:
            supported = ", ".join(sorted(cls._registry))
            raise LLMProviderError(
                f"Unsupported provider '{provider}'. Supported: {supported}."
            )
        return cls._registry[provider](model=model)

    @classmethod
    def supported_providers(cls) -> tuple[str, ...]:
        return tuple(cls._registry)

    @classmethod
    def register(cls, name: str, provider_cls: type[LLMProviderBase]) -> None:
        cls._registry[name] = provider_cls
