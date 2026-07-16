"""BotInvokerBase — callback strategy contract for bot invocation (M4.1, data-model.md).

Concrete invokers never raise through the simulator callback: failures become
structured [BOT_UNREACHABLE] turns (R6).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from deepeval.test_case import Turn


class BotInvokerBase(ABC):
    @abstractmethod
    def __call__(self, input: str, turns: list[Turn], thread_id: str) -> Turn:
        ...
