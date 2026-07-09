"""OpenRouterProvider — wraps DeepEval's native OpenRouterModel (DeepEvalBaseLLM) (US4).

Uses deepeval.models.OpenRouterModel directly instead of langchain_openrouter.ChatOpenRouter,
per constitution Principle II (DeepEval-First) — OpenRouterModel is DeepEval's own
judge-model implementation for the OpenRouter gateway, built for exactly this role.
"""
from __future__ import annotations

from deepeval.models import OpenRouterModel

from deepeval_platform.config.config_manager import ConfigError, ConfigManager
from deepeval_platform.llm.base import LLMProviderBase, LLMProviderError, TokenUsage


class OpenRouterProvider(LLMProviderBase):
    def __init__(self, model: str | None = None) -> None:
        try:
            api_key = ConfigManager.instance().get("OPENROUTER_API_KEY")
        except ConfigError as exc:
            raise LLMProviderError(
                f"OPENROUTER_API_KEY is not configured. {exc}"
            ) from exc

        resolved_model = model or ConfigManager.instance().get("openrouter.default_model")
        self._model_str = resolved_model
        # OpenRouterModel.calculate_cost() returns None (discarding real token counts
        # along with the cost) unless cost_per_input_token/cost_per_output_token are set —
        # OpenRouter serves hundreds of models with no single static price, so we pass 0.0
        # deliberately: this project never reads or reports EvaluationCost's dollar value
        # (TokenUsage has no cost field), but doing so unlocks accurate input/output token
        # counts on every call instead of silently losing them.
        self._native = OpenRouterModel(
            model=resolved_model,
            api_key=api_key,
            cost_per_input_token=0.0,
            cost_per_output_token=0.0,
        )

    @property
    def provider_name(self) -> str:
        return "openrouter"

    @property
    def model_name(self) -> str:
        return self._model_str

    def generate(self, prompt: str) -> tuple[str, TokenUsage]:
        output, cost = self._native.generate(prompt)
        return output, self._to_token_usage(cost)

    async def a_generate(self, prompt: str) -> tuple[str, TokenUsage]:
        output, cost = await self._native.a_generate(prompt)
        return output, self._to_token_usage(cost)
