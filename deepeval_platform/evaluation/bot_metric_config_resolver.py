"""BotMetricConfigResolver — merges a strategy's metric list with per-bot opt-in metrics and
resolves per-metric constructor options, reading exclusively through ConfigManager (M3.3, FR-015).

Configuration-domain only: no metric instantiation or evaluation logic, no import of
MetricFactory or any metric class (data-model.md, contracts/evaluation-api.md).
"""
from __future__ import annotations

import importlib

from deepeval_platform.config.config_manager import ConfigManager

_TRUTHY_VALUES = frozenset({"true", "1", "yes"})


class BotMetricConfigResolver:
    def __init__(self, config: ConfigManager | None = None) -> None:
        self._config = config if config is not None else ConfigManager.instance()

    def resolve_metric_names(self, bot_id: str, strategy_metrics: list[str]) -> list[str]:
        metric_names = list(strategy_metrics)

        enabled = self._config.get_optional(
            f"bots.{bot_id}.metrics.summarization.enabled", default=""
        )
        if enabled.strip().lower() in _TRUTHY_VALUES:
            metric_names.append("summarization")

        if self._config.get_optional(f"bots.{bot_id}.json_schema", default=""):
            metric_names.append("json_correctness")

        if self._config.get_optional(f"bots.{bot_id}.prompt_instructions.0", default=""):
            metric_names.append("prompt_alignment")

        if self._config.get_optional(
            f"bots.{bot_id}.conversational_geval_criteria", default=""
        ):
            metric_names.append("conversational_g_eval")

        return metric_names

    def resolve_options(
        self, bot_id: str, metric_names: list[str]
    ) -> dict[str, dict[str, object]]:
        options: dict[str, dict[str, object]] = {}
        for name in metric_names:
            if name == "json_correctness":
                options[name] = self._resolve_json_correctness_options(bot_id)
            elif name == "prompt_alignment":
                options[name] = self._resolve_prompt_alignment_options(bot_id)
            elif name == "conversational_g_eval":
                options[name] = self._resolve_conversational_g_eval_options(bot_id)
            elif name == "role_adherence":
                options[name] = self._resolve_role_adherence_options(bot_id)
            else:
                options[name] = {}
        return options

    def _resolve_json_correctness_options(self, bot_id: str) -> dict[str, object]:
        dotted_path = self._config.get_optional(f"bots.{bot_id}.json_schema", default="")
        module_path, _, class_name = dotted_path.rpartition(".")
        module = importlib.import_module(module_path)
        expected_schema = getattr(module, class_name)
        return {"expected_schema": expected_schema}

    def _resolve_prompt_alignment_options(self, bot_id: str) -> dict[str, object]:
        instructions: list[str] = []
        index = 0
        while True:
            value = self._config.get_optional(
                f"bots.{bot_id}.prompt_instructions.{index}", default=""
            )
            if value == "":
                break
            instructions.append(value)
            index += 1
        return {"prompt_instructions": instructions}

    def _resolve_conversational_g_eval_options(self, bot_id: str) -> dict[str, object]:
        criteria = self._config.get_optional(
            f"bots.{bot_id}.conversational_geval_criteria", default=""
        )
        return {"criteria": criteria}

    def _resolve_role_adherence_options(self, bot_id: str) -> dict[str, object]:
        chatbot_role = self._config.get_optional(f"bots.{bot_id}.chatbot_role", default="")
        return {"chatbot_role": chatbot_role or None}
