"""RagasLLMAdapter — adapts a DeepEvalBaseLLM judge to Ragas' BaseRagasLLM interface (M3.4, US3,
FR-009).

Never LangChain (Principle III) — wraps the project's already-resolved DeepEvalBaseLLM judge
directly, satisfying only the subset of BaseRagasLLM that AnswerCorrectness/ContextRecall
exercise (research.md §R3). Does not import LLMProviderFactory or any concrete provider.
"""
from __future__ import annotations

from deepeval.models.base_model import DeepEvalBaseLLM
from langchain_core.outputs import Generation, LLMResult
from ragas.llms.base import BaseRagasLLM


class RagasLLMAdapter(BaseRagasLLM):
    def __init__(self, deepeval_model: DeepEvalBaseLLM) -> None:
        super().__init__()
        self._deepeval_model = deepeval_model

    async def agenerate_text(
        self, prompt, n: int = 1, temperature: float = 0.01, stop=None, callbacks=None
    ) -> LLMResult:
        text, _ = await self._deepeval_model.a_generate(prompt.to_string())
        return LLMResult(generations=[[Generation(text=text)]])

    def generate_text(
        self, prompt, n: int = 1, temperature: float = 0.01, stop=None, callbacks=None
    ) -> LLMResult:
        text, _ = self._deepeval_model.generate(prompt.to_string())
        return LLMResult(generations=[[Generation(text=text)]])

    def is_finished(self, response) -> bool:
        return True
