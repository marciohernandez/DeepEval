"""Real local LangChain-style chain fixture for LangChainBotInvoker integration
coverage (M4.1, T032). No network access; `.invoke()` is a plain function.
"""
from __future__ import annotations


class _FakeChain:
    def invoke(self, input: str) -> str:
        return f"Here is help regarding: {input}"


chain = _FakeChain()
