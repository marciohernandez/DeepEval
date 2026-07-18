"""EvaluationOrchestrator — resolves thresholds/timeouts/judge, runs every requested metric
concurrently, and aggregates into an EvaluationResult (M3.1). The primary entry point for this
feature (contracts/evaluation-api.md)."""
from __future__ import annotations

import asyncio
import inspect
import logging

from deepeval_platform.config.config_manager import ConfigManager
from deepeval_platform.evaluation.bot_metric_config_resolver import BotMetricConfigResolver
from deepeval_platform.evaluation.errors import (
    ConfigResolutionError,
    DuplicateMetricRequestError,
    EmptyMetricListError,
    ErrorDetail,
    InvalidThresholdError,
    InvalidTimeoutError,
    UnknownMetricError,
    sanitize_error,
)
from deepeval_platform.evaluation.evaluation_context import EvaluationContext
from deepeval_platform.evaluation.evaluation_result import EvaluationResult, MetricResult
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.llm.factory import LLMProviderFactory
from deepeval_platform.normalization.models import NormalizedTrace

logger = logging.getLogger(__name__)


class EvaluationOrchestrator:
    def __init__(
        self,
        config: ConfigManager | None = None,
        resolver: BotMetricConfigResolver | None = None,
    ) -> None:
        self._config = config if config is not None else ConfigManager.instance()
        self._resolver = resolver if resolver is not None else BotMetricConfigResolver()

    async def evaluate(
        self,
        trace: NormalizedTrace,
        bot_id: str,
        metric_names: list[str],
        *,
        thresholds: dict[str, float] | None = None,
    ) -> EvaluationResult:
        if not metric_names:
            raise EmptyMetricListError()

        duplicates = self._find_duplicates(metric_names)
        if duplicates:
            raise DuplicateMetricRequestError(duplicates)

        unknown = [name for name in metric_names if name not in MetricFactory._registry]
        if unknown:
            raise UnknownMetricError(unknown, supported=sorted(MetricFactory._registry))

        try:
            resolved_thresholds = (
                thresholds if thresholds is not None else self._resolve_thresholds(bot_id, metric_names)
            )
            timeouts = self._resolve_timeouts(metric_names)
            judge = self._resolve_judge()
        except (InvalidThresholdError, InvalidTimeoutError):
            raise
        except Exception as exc:
            raise ConfigResolutionError(bot_id, exc) from exc

        context = EvaluationContext(trace=trace, thresholds=resolved_thresholds)

        results = await asyncio.gather(
            *(
                self._measure_one(
                    bot_id, name, resolved_thresholds[name], timeouts[name], judge, context
                )
                for name in metric_names
            )
        )
        metrics = dict(zip(metric_names, results))
        passed = all(result.passed for result in metrics.values())
        return EvaluationResult(passed=passed, metrics=metrics)

    async def _measure_one(
        self,
        bot_id: str,
        name: str,
        threshold: float,
        timeout: float,
        judge,
        context: EvaluationContext,
    ) -> MetricResult:
        try:
            options = self._resolver.resolve_options(bot_id, [name])[name]
            metric = MetricFactory.create(
                name, threshold=threshold, deepeval_model=judge, **options
            )
            return await asyncio.wait_for(metric.measure(context), timeout=timeout)
        except asyncio.TimeoutError:
            logger.exception("Metric '%s' exceeded its %ss timeout", name, timeout)
            detail = ErrorDetail(
                category="timeout",
                message=f"Metric '{name}' exceeded its {timeout}s timeout.",
            )
            return MetricResult(score=None, threshold=threshold, passed=False, error=detail)
        except Exception as exc:
            logger.exception("Metric '%s' raised during measure()", name)
            return MetricResult(
                score=None, threshold=threshold, passed=False, error=sanitize_error(exc)
            )

    @staticmethod
    def _find_duplicates(metric_names: list[str]) -> list[str]:
        seen: set[str] = set()
        duplicates: list[str] = []
        for name in metric_names:
            if name in seen and name not in duplicates:
                duplicates.append(name)
            seen.add(name)
        return duplicates

    def _resolve_thresholds(self, bot_id: str, metric_names: list[str]) -> dict[str, float]:
        offending: list[tuple[str, object]] = []
        resolved: dict[str, float] = {}
        for name in metric_names:
            raw = self._config.get_optional(f"bots.{bot_id}.metrics.{name}.threshold", default="")
            if raw == "":
                value = self._native_default_threshold(name)
            else:
                try:
                    value = float(raw)
                except (ValueError, TypeError):
                    offending.append((name, raw))
                    continue
            if not isinstance(value, (int, float)) or not (0.0 <= value <= 1.0):
                offending.append((name, value))
                continue
            resolved[name] = float(value)
        if offending:
            raise InvalidThresholdError(offending)
        return resolved

    @staticmethod
    def _native_default_threshold(name: str) -> float:
        native_cls = MetricFactory._registry[name]._native_metric_cls
        return inspect.signature(native_cls.__init__).parameters["threshold"].default

    def _resolve_timeouts(self, metric_names: list[str]) -> dict[str, float]:
        offending: list[tuple[str, object]] = []

        raw_default = self._config.get_optional("evaluation.metric_timeout_seconds", default="")
        try:
            default_timeout: float | None = float(raw_default)
        except (ValueError, TypeError):
            offending.append(("default", raw_default))
            default_timeout = None
        else:
            if default_timeout <= 0:
                offending.append(("default", default_timeout))
                default_timeout = None

        resolved: dict[str, float] = {}
        for name in metric_names:
            raw = self._config.get_optional(
                f"evaluation.metric_timeout_overrides.{name}", default=""
            )
            if raw == "":
                if default_timeout is not None:
                    resolved[name] = default_timeout
                continue
            try:
                value = float(raw)
            except (ValueError, TypeError):
                offending.append((name, raw))
                continue
            if value <= 0:
                offending.append((name, value))
                continue
            resolved[name] = value

        if offending:
            raise InvalidTimeoutError(offending)
        return resolved

    def _resolve_judge(self):
        provider = self._config.get("evaluation.llm_judge.provider")
        model = self._config.get("evaluation.llm_judge.model")
        return LLMProviderFactory.create(provider, model).as_deepeval_model()
