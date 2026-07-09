"""OpenAIProvider — wraps DeepEval's native GPTModel (DeepEvalBaseLLM) (US4).

Uses deepeval.models.GPTModel directly instead of langchain_openai.ChatOpenAI, per
constitution Principle II (DeepEval-First) — GPTModel is DeepEval's own judge-model
implementation for OpenAI, built for exactly this role.
"""
from __future__ import annotations

from deepeval.models import GPTModel

from deepeval_platform.config.config_manager import ConfigError, ConfigManager
from deepeval_platform.llm.base import LLMProviderBase, LLMProviderError, TokenUsage


class OpenAIProvider(LLMProviderBase):
    def __init__(self, model: str | None = None) -> None:
        try:
            api_key = ConfigManager.instance().get("OPENAI_API_KEY")
        except ConfigError as exc:
            raise LLMProviderError(
                f"OPENAI_API_KEY is not configured. {exc}"
            ) from exc

        resolved_model = model or ConfigManager.instance().get("openai.default_model")
        self._model_str = resolved_model
        self._native = GPTModel(model=resolved_model, api_key=api_key)

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model_str

    def generate(self, prompt: str) -> tuple[str, TokenUsage]:
        output, cost = self._native.generate(prompt)
        return output, self._to_token_usage(cost)

    async def a_generate(self, prompt: str) -> tuple[str, TokenUsage]:
        output, cost = await self._native.a_generate(prompt)
        return output, self._to_token_usage(cost)
