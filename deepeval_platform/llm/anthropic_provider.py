"""AnthropicProvider — wraps DeepEval's native AnthropicModel (DeepEvalBaseLLM) (US4).

Uses deepeval.models.AnthropicModel directly instead of langchain_anthropic.ChatAnthropic,
per constitution Principle II (DeepEval-First) — AnthropicModel is DeepEval's own
judge-model implementation for Anthropic, built for exactly this role.
"""
from __future__ import annotations

from deepeval.models import AnthropicModel

from deepeval_platform.config.config_manager import ConfigError, ConfigManager
from deepeval_platform.llm.base import LLMProviderBase, LLMProviderError, TokenUsage


class AnthropicProvider(LLMProviderBase):
    def __init__(self, model: str | None = None) -> None:
        try:
            api_key = ConfigManager.instance().get("ANTHROPIC_API_KEY")
        except ConfigError as exc:
            raise LLMProviderError(
                f"ANTHROPIC_API_KEY is not configured. {exc}"
            ) from exc

        resolved_model = model or ConfigManager.instance().get("anthropic.default_model")
        self._model_str = resolved_model
        self._native = AnthropicModel(model=resolved_model, api_key=api_key)

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model_str

    def generate(self, prompt: str) -> tuple[str, TokenUsage]:
        output, cost = self._native.generate(prompt)
        return output, self._to_token_usage(cost)

    async def a_generate(self, prompt: str) -> tuple[str, TokenUsage]:
        output, cost = await self._native.a_generate(prompt)
        return output, self._to_token_usage(cost)
