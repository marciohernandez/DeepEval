"""Unit tests for RagasLLMAdapter (M3.4, US3, FR-009).

Adapts a DeepEvalBaseLLM judge to Ragas' BaseRagasLLM interface — never LangChain
(Principle III; FR-009).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from deepeval.models.base_model import DeepEvalBaseLLM

from deepeval_platform.llm.ragas_adapter import RagasLLMAdapter


def _mock_prompt(text: str) -> MagicMock:
    prompt = MagicMock()
    prompt.to_string.return_value = text
    return prompt


class TestRagasLLMAdapter:
    async def test_agenerate_text_delegates_to_deepeval_model_a_generate(self):
        deepeval_model = MagicMock(spec=DeepEvalBaseLLM)
        deepeval_model.a_generate = AsyncMock(return_value=("generated text", object()))
        adapter = RagasLLMAdapter(deepeval_model)

        result = await adapter.agenerate_text(prompt=_mock_prompt("the prompt"))

        deepeval_model.a_generate.assert_awaited_once_with("the prompt")
        assert result.generations[0][0].text == "generated text"

    def test_generate_text_sync_wrapper_delegates_to_a_generate(self):
        deepeval_model = MagicMock(spec=DeepEvalBaseLLM)
        deepeval_model.generate = MagicMock(return_value=("generated text", object()))
        adapter = RagasLLMAdapter(deepeval_model)

        result = adapter.generate_text(prompt=_mock_prompt("the prompt"))

        deepeval_model.generate.assert_called_once_with("the prompt")
        assert result.generations[0][0].text == "generated text"

    def test_is_finished_always_returns_true(self):
        adapter = RagasLLMAdapter(MagicMock(spec=DeepEvalBaseLLM))
        assert adapter.is_finished(response=MagicMock()) is True

    def test_source_does_not_import_llm_provider_factory_or_provider_classes(self):
        source = Path("deepeval_platform/llm/ragas_adapter.py").read_text()
        assert "from deepeval_platform.llm.factory import" not in source
        assert "from deepeval_platform.llm.anthropic_provider import" not in source
        assert "from deepeval_platform.llm.openai_provider import" not in source
        assert "from deepeval_platform.llm.openrouter_provider import" not in source
