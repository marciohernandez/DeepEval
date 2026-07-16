"""Real importable fixture chain for LangChainBotInvoker._resolve_chain coverage."""
from __future__ import annotations


class _FakeChain:
    def invoke(self, input: str) -> str:
        return f"resolved chain answer for: {input}"


chain = _FakeChain()
