"""LangChainBotInvoker — native `.invoke()` against a configured bot chain/graph,
normalizing str/BaseMessage/dict results to a Turn (M4.1, R6). Never raises
through the simulator callback.
"""
from __future__ import annotations

import importlib
from typing import Any

from deepeval.test_case import Turn
from langchain_core.messages import BaseMessage

from deepeval_platform.synthetic.bot_invoker_base import BotInvokerBase

_DICT_CONTENT_KEYS = ("output", "text", "answer")


class LangChainBotInvoker(BotInvokerBase):
    def __init__(self, bot_id: str, chain_target: str) -> None:
        self._bot_id = bot_id
        self._chain_target = chain_target

    def __call__(self, input: str, turns: list[Turn], thread_id: str) -> Turn:
        try:
            chain = self._resolve_chain(self._chain_target)
        except Exception as exc:
            return self._unreachable(
                code="resolution_error", error_type=type(exc).__name__, message=str(exc)
            )

        try:
            result = chain.invoke(input)
        except Exception as exc:
            return self._unreachable(
                code="invocation_error", error_type=type(exc).__name__, message=str(exc)
            )

        content = self._normalize(result)
        if not content:
            return self._unreachable(
                code="malformed_response",
                error_type="ResponseNormalizationError",
                message=f"Unsupported or empty chain result: {result!r}",
            )

        return Turn(
            role="assistant",
            content=content,
            metadata={"bot_id": self._bot_id, "thread_id": thread_id},
        )

    @staticmethod
    def _normalize(result: Any) -> str | None:
        if isinstance(result, str):
            return result or None
        if isinstance(result, BaseMessage):
            content = result.content
            return content if isinstance(content, str) and content else None
        if isinstance(result, dict):
            for key in _DICT_CONTENT_KEYS:
                value = result.get(key)
                if isinstance(value, str) and value:
                    return value
            return None
        return None

    @staticmethod
    def _resolve_chain(chain_target: str) -> Any:
        module_path, _, attr_name = chain_target.rpartition(".")
        module = importlib.import_module(module_path)
        return getattr(module, attr_name)

    def _unreachable(self, *, code: str, error_type: str, message: str) -> Turn:
        return Turn(
            role="assistant",
            content="[BOT_UNREACHABLE]",
            metadata={
                "error": {
                    "code": code,
                    "type": error_type,
                    "message": message,
                    "bot_id": self._bot_id,
                }
            },
        )
