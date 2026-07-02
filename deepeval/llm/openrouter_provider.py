"""OpenRouterProvider — wraps langchain_openrouter.ChatOpenRouter (US4).

Uses the dedicated langchain-openrouter integration (NOT ChatOpenAI + base_url),
per constitution Gate 5 / plan.md.
"""
from __future__ import annotations

from langchain_openrouter import ChatOpenRouter

from deepeval.config.config_manager import ConfigError, ConfigManager
from deepeval.llm.base import LLMProviderBase, LLMProviderError, TokenUsage


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
        self._lc_model = ChatOpenRouter(openrouter_api_key=api_key, model=resolved_model)

    @property
    def provider_name(self) -> str:
        return "openrouter"

    @property
    def model_name(self) -> str:
        return self._model_str

    def generate(self, prompt: str) -> tuple[str, TokenUsage]:
        response = self._lc_model.invoke(prompt)
        return response.content, self._extract_usage(response)

    async def a_generate(self, prompt: str) -> tuple[str, TokenUsage]:
        response = await self._lc_model.ainvoke(prompt)
        return response.content, self._extract_usage(response)

    def _extract_usage(self, response) -> TokenUsage:
        usage = response.usage_metadata
        if usage is not None:
            return TokenUsage(
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
            )
        meta = getattr(response, "response_metadata", {}) or {}
        raw = meta.get("usage", {})
        if raw:
            return TokenUsage(
                input_tokens=raw.get("prompt_tokens", 0),
                output_tokens=raw.get("completion_tokens", 0),
            )
        return TokenUsage(input_tokens=0, output_tokens=0)
