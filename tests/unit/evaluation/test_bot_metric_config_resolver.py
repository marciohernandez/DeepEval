"""Unit tests for BotMetricConfigResolver (M3.3 Foundational, FR-009/FR-010a/FR-011/FR-012/FR-015).

Config-domain only — reads exclusively through a stubbed ConfigManager, never instantiates or
imports any metric class (data-model.md, contracts/evaluation-api.md).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from deepeval_platform.evaluation.bot_metric_config_resolver import BotMetricConfigResolver


class DummySchema(BaseModel):
    """Real importable dummy BaseModel subclass used to exercise json_schema resolution (research.md §R5)."""

    order_id: str


def build_dummy_dag() -> str:
    """Real importable zero-argument dummy callable used to exercise dag_builder's invoke-not-use-as-is
    resolution path (research.md §R2)."""

    return "dag-instance-sentinel"


def _stub_config(values: dict[str, str]) -> MagicMock:
    config = MagicMock()
    config.get_optional.side_effect = lambda key, default="": values.get(key, default)
    return config


@pytest.fixture
def resolver_with():
    def _make(values: dict[str, str]) -> BotMetricConfigResolver:
        return BotMetricConfigResolver(config=_stub_config(values))

    return _make


class TestResolveMetricNames:
    def test_no_opt_in_keys_returns_strategy_metrics_unchanged(self, resolver_with):
        resolver = resolver_with({})
        result = resolver.resolve_metric_names("test_bot", ["bias", "toxicity"])
        assert result == ["bias", "toxicity"]

    @pytest.mark.parametrize("truthy_value", ["true", "TRUE", "True", "1", "yes", "YES"])
    def test_summarization_appended_when_enabled_truthy(self, resolver_with, truthy_value):
        resolver = resolver_with(
            {"bots.test_bot.metrics.summarization.enabled": truthy_value}
        )
        result = resolver.resolve_metric_names("test_bot", ["bias"])
        assert result == ["bias", "summarization"]

    def test_summarization_omitted_when_false(self, resolver_with):
        resolver = resolver_with({"bots.test_bot.metrics.summarization.enabled": "false"})
        result = resolver.resolve_metric_names("test_bot", ["bias"])
        assert result == ["bias"]

    def test_summarization_omitted_when_absent(self, resolver_with):
        resolver = resolver_with({})
        result = resolver.resolve_metric_names("test_bot", ["bias"])
        assert "summarization" not in result

    def test_json_correctness_appended_only_when_json_schema_set(self, resolver_with):
        resolver = resolver_with({"bots.test_bot.json_schema": "some.module.Schema"})
        result = resolver.resolve_metric_names("test_bot", [])
        assert result == ["json_correctness"]

    def test_json_correctness_omitted_when_absent(self, resolver_with):
        resolver = resolver_with({})
        result = resolver.resolve_metric_names("test_bot", [])
        assert "json_correctness" not in result

    def test_prompt_alignment_appended_only_when_first_instruction_set(self, resolver_with):
        resolver = resolver_with({"bots.test_bot.prompt_instructions.0": "Be concise"})
        result = resolver.resolve_metric_names("test_bot", [])
        assert result == ["prompt_alignment"]

    def test_prompt_alignment_omitted_when_absent(self, resolver_with):
        resolver = resolver_with({})
        result = resolver.resolve_metric_names("test_bot", [])
        assert "prompt_alignment" not in result

    def test_conversational_g_eval_appended_only_when_criteria_set(self, resolver_with):
        resolver = resolver_with(
            {"bots.test_bot.conversational_geval_criteria": "Stays on-topic"}
        )
        result = resolver.resolve_metric_names("test_bot", [])
        assert result == ["conversational_g_eval"]

    def test_conversational_g_eval_omitted_when_absent(self, resolver_with):
        resolver = resolver_with({})
        result = resolver.resolve_metric_names("test_bot", [])
        assert "conversational_g_eval" not in result

    def test_g_eval_appended_only_when_geval_criteria_set(self, resolver_with):
        resolver = resolver_with(
            {"bots.test_bot.geval_criteria": "Stays formal"}
        )
        result = resolver.resolve_metric_names("test_bot", [])
        assert result == ["g_eval"]

    def test_g_eval_omitted_when_geval_criteria_absent(self, resolver_with):
        resolver = resolver_with({})
        result = resolver.resolve_metric_names("test_bot", [])
        assert "g_eval" not in result

    def test_dag_appended_only_when_dag_builder_set(self, resolver_with):
        resolver = resolver_with(
            {"bots.test_bot.dag_builder": f"{__name__}.build_dummy_dag"}
        )
        result = resolver.resolve_metric_names("test_bot", [])
        assert result == ["dag"]

    def test_dag_omitted_when_dag_builder_absent(self, resolver_with):
        resolver = resolver_with({})
        result = resolver.resolve_metric_names("test_bot", [])
        assert "dag" not in result

    @pytest.mark.parametrize("truthy_value", ["true", "TRUE", "True", "1", "yes", "YES"])
    def test_ragas_answer_correctness_appended_when_enabled_truthy(
        self, resolver_with, truthy_value
    ):
        resolver = resolver_with(
            {"bots.test_bot.metrics.ragas_answer_correctness.enabled": truthy_value}
        )
        result = resolver.resolve_metric_names("test_bot", [])
        assert result == ["ragas_answer_correctness"]

    def test_ragas_answer_correctness_omitted_when_false_or_absent(self, resolver_with):
        resolver = resolver_with(
            {"bots.test_bot.metrics.ragas_answer_correctness.enabled": "false"}
        )
        assert "ragas_answer_correctness" not in resolver.resolve_metric_names("test_bot", [])
        resolver = resolver_with({})
        assert "ragas_answer_correctness" not in resolver.resolve_metric_names("test_bot", [])

    @pytest.mark.parametrize("truthy_value", ["true", "TRUE", "True", "1", "yes", "YES"])
    def test_ragas_context_recall_appended_when_enabled_truthy(
        self, resolver_with, truthy_value
    ):
        resolver = resolver_with(
            {"bots.test_bot.metrics.ragas_context_recall.enabled": truthy_value}
        )
        result = resolver.resolve_metric_names("test_bot", [])
        assert result == ["ragas_context_recall"]

    def test_ragas_context_recall_omitted_when_false_or_absent(self, resolver_with):
        resolver = resolver_with(
            {"bots.test_bot.metrics.ragas_context_recall.enabled": "false"}
        )
        assert "ragas_context_recall" not in resolver.resolve_metric_names("test_bot", [])
        resolver = resolver_with({})
        assert "ragas_context_recall" not in resolver.resolve_metric_names("test_bot", [])

    def test_ragas_metrics_independent_opt_in(self, resolver_with):
        resolver = resolver_with(
            {"bots.test_bot.metrics.ragas_answer_correctness.enabled": "true"}
        )
        result = resolver.resolve_metric_names("test_bot", [])
        assert result == ["ragas_answer_correctness"]

        resolver = resolver_with(
            {"bots.test_bot.metrics.ragas_context_recall.enabled": "true"}
        )
        result = resolver.resolve_metric_names("test_bot", [])
        assert result == ["ragas_context_recall"]

    def test_fixed_append_order_and_strategy_metrics_untouched(self, resolver_with):
        resolver = resolver_with(
            {
                "bots.test_bot.metrics.summarization.enabled": "true",
                "bots.test_bot.json_schema": "some.module.Schema",
                "bots.test_bot.prompt_instructions.0": "Be concise",
                "bots.test_bot.conversational_geval_criteria": "Stays on-topic",
                "bots.test_bot.geval_criteria": "Stays formal",
                "bots.test_bot.dag_builder": f"{__name__}.build_dummy_dag",
                "bots.test_bot.metrics.ragas_answer_correctness.enabled": "true",
                "bots.test_bot.metrics.ragas_context_recall.enabled": "true",
            }
        )
        result = resolver.resolve_metric_names(
            "test_bot", ["conversation_completeness", "turn_relevancy"]
        )
        assert result == [
            "conversation_completeness",
            "turn_relevancy",
            "summarization",
            "json_correctness",
            "prompt_alignment",
            "conversational_g_eval",
            "g_eval",
            "dag",
            "ragas_answer_correctness",
            "ragas_context_recall",
        ]


class TestResolveOptions:
    def test_names_needing_no_extra_kwargs_map_to_empty_dict(self, resolver_with):
        resolver = resolver_with({})
        result = resolver.resolve_options("test_bot", ["bias", "toxicity", "summarization"])
        assert result == {"bias": {}, "toxicity": {}, "summarization": {}}

    def test_json_correctness_resolves_expected_schema_via_dotted_path(self, resolver_with):
        module_path = f"{__name__}.DummySchema"
        resolver = resolver_with({"bots.test_bot.json_schema": module_path})
        result = resolver.resolve_options("test_bot", ["json_correctness"])
        assert result == {"json_correctness": {"expected_schema": DummySchema}}

    def test_json_correctness_bad_module_path_propagates_import_error(self, resolver_with):
        resolver = resolver_with(
            {"bots.test_bot.json_schema": "nonexistent.module.path.Schema"}
        )
        with pytest.raises(ImportError):
            resolver.resolve_options("test_bot", ["json_correctness"])

    def test_json_correctness_bad_attribute_propagates_attribute_error(self, resolver_with):
        resolver = resolver_with(
            {"bots.test_bot.json_schema": f"{__name__}.NoSuchClass"}
        )
        with pytest.raises(AttributeError):
            resolver.resolve_options("test_bot", ["json_correctness"])

    def test_prompt_alignment_resolves_indexed_list(self, resolver_with):
        resolver = resolver_with(
            {
                "bots.test_bot.prompt_instructions.0": "Always respond in JSON",
                "bots.test_bot.prompt_instructions.1": "Never mention competitors",
            }
        )
        result = resolver.resolve_options("test_bot", ["prompt_alignment"])
        assert result == {
            "prompt_alignment": {
                "prompt_instructions": ["Always respond in JSON", "Never mention competitors"]
            }
        }

    def test_conversational_g_eval_resolves_criteria(self, resolver_with):
        resolver = resolver_with(
            {"bots.test_bot.conversational_geval_criteria": "Stays on-topic"}
        )
        result = resolver.resolve_options("test_bot", ["conversational_g_eval"])
        assert result == {"conversational_g_eval": {"criteria": "Stays on-topic"}}

    def test_g_eval_resolves_criteria(self, resolver_with):
        resolver = resolver_with({"bots.test_bot.geval_criteria": "Stays formal"})
        result = resolver.resolve_options("test_bot", ["g_eval"])
        assert result == {"g_eval": {"criteria": "Stays formal"}}

    def test_resolve_options_dag_invokes_resolved_callable_with_zero_args(self, resolver_with):
        module_path = f"{__name__}.build_dummy_dag"
        resolver = resolver_with({"bots.test_bot.dag_builder": module_path})
        result = resolver.resolve_options("test_bot", ["dag"])
        assert result == {"dag": {"dag": "dag-instance-sentinel"}}

    def test_dag_bad_module_path_propagates_import_error(self, resolver_with):
        resolver = resolver_with(
            {"bots.test_bot.dag_builder": "nonexistent.module.path.build_dag"}
        )
        with pytest.raises(ImportError):
            resolver.resolve_options("test_bot", ["dag"])

    def test_dag_bad_attribute_propagates_attribute_error(self, resolver_with):
        resolver = resolver_with(
            {"bots.test_bot.dag_builder": f"{__name__}.no_such_builder"}
        )
        with pytest.raises(AttributeError):
            resolver.resolve_options("test_bot", ["dag"])

    def test_resolve_options_ragas_names_return_empty_dict(self, resolver_with):
        resolver = resolver_with({})
        result = resolver.resolve_options(
            "test_bot", ["ragas_answer_correctness", "ragas_context_recall"]
        )
        assert result == {"ragas_answer_correctness": {}, "ragas_context_recall": {}}

    def test_role_adherence_resolves_chatbot_role_when_present(self, resolver_with):
        resolver = resolver_with(
            {"bots.test_bot.chatbot_role": "A polite banking assistant"}
        )
        result = resolver.resolve_options("test_bot", ["role_adherence"])
        assert result == {"role_adherence": {"chatbot_role": "A polite banking assistant"}}

    def test_role_adherence_resolves_none_when_chatbot_role_absent(self, resolver_with):
        resolver = resolver_with({})
        result = resolver.resolve_options("test_bot", ["role_adherence"])
        assert result == {"role_adherence": {"chatbot_role": None}}


class TestNoMetricLogicImported:
    def test_source_contains_no_metrics_package_import(self):
        source = Path(
            "deepeval_platform/evaluation/bot_metric_config_resolver.py"
        ).read_text()
        assert "from deepeval_platform.evaluation.metrics" not in source
