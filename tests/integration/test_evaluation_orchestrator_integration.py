"""Integration test for EvaluationOrchestrator (M3.1).

Exercises the real MetricFactory registry (native wrappers self-registered via package import),
real threshold/timeout resolution through a real ConfigManager instance, real concurrent
asyncio.gather execution, and real AND aggregation. The judge is a minimal DeepEvalBaseLLM stub
that returns a structurally valid Pydantic schema instance for every native-metric prompt step —
no network access, no real API key required (quickstart.md).
"""
from __future__ import annotations

import typing

import pytest
from pydantic import BaseModel

from deepeval.models.base_model import DeepEvalBaseLLM

from deepeval_platform.config.config_manager import ConfigEntry, ConfigManager
from deepeval_platform.evaluation import metrics  # noqa: F401 — triggers native wrapper self-registration
from deepeval_platform.evaluation.evaluation_orchestrator import EvaluationOrchestrator
from deepeval_platform.normalization.models import NormalizedTrace


def _dummy_value_for_annotation(annotation):
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        return _dummy_value_for_annotation(non_none[0]) if non_none else None
    if origin is list:
        item_type = args[0] if args else str
        return [_dummy_value_for_annotation(item_type)]
    if origin is typing.Literal:
        return args[0]
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _build_dummy_schema(annotation)
    if annotation is float:
        return 1.0
    if annotation is int:
        return 1
    if annotation is bool:
        return True
    return "stub"


def _build_dummy_schema(schema_cls: type[BaseModel]) -> BaseModel:
    kwargs = {
        name: _dummy_value_for_annotation(field.annotation)
        for name, field in schema_cls.model_fields.items()
    }
    return schema_cls(**kwargs)


class _FakeJudgeModel(DeepEvalBaseLLM):
    """Minimal DeepEvalBaseLLM stub — returns a structurally valid schema instance for every
    structured-output call, so every native metric's multi-step protocol completes without any
    real LLM round-trip."""

    def load_model(self):
        return self

    def get_model_name(self) -> str:
        return "fake-judge"

    def generate(self, *args, **kwargs) -> str:
        return "{}"

    async def a_generate(self, *args, **kwargs) -> str:
        return "{}"

    async def a_generate_with_schema(self, *args, schema=None, **kwargs):
        assert schema is not None
        return _build_dummy_schema(schema)


def _make_test_config_manager() -> ConfigManager:
    """A real ConfigManager instance, populated directly (bypasses `_load()`/filesystem)."""
    config = ConfigManager()
    raw = {
        "bots.test_rag_bot.metrics.faithfulness.threshold": "0.8",
        "evaluation.metric_timeout_seconds": "30",
        "evaluation.llm_judge.provider": "openai",
        "evaluation.llm_judge.model": "gpt-4o",
    }
    config._store = {
        key: ConfigEntry(
            key=key, value=value, source="yaml", source_file="test", is_sensitive=False
        )
        for key, value in raw.items()
    }
    return config


class TestEvaluationOrchestratorIntegration:
    async def test_full_flow_real_registry_real_config_real_aggregation(self, mocker):
        config = _make_test_config_manager()
        orchestrator = EvaluationOrchestrator(config=config)

        judge = _FakeJudgeModel()
        provider = mocker.MagicMock()
        provider.as_deepeval_model.return_value = judge
        mocker.patch(
            "deepeval_platform.llm.factory.LLMProviderFactory.create",
            return_value=provider,
        )

        trace = NormalizedTrace(
            input="What is the refund policy?",
            output="Refunds are available within 30 days of purchase.",
            context=["Our refund policy allows returns within 30 days of purchase."],
            expected_output="Refunds within 30 days.",
        )

        result = await orchestrator.evaluate(
            trace=trace,
            bot_id="test_rag_bot",
            metric_names=["answer_relevancy", "faithfulness"],
        )

        assert set(result.metrics.keys()) == {"answer_relevancy", "faithfulness"}
        for name, metric_result in result.metrics.items():
            assert metric_result.error is None, f"{name} failed: {metric_result.error}"
            assert metric_result.score is not None

        # faithfulness threshold comes from bots.yaml-style config (0.8), not the native default
        assert result.metrics["faithfulness"].threshold == 0.8
        assert result.passed is True
