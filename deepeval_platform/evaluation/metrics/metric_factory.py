"""MetricFactory — Factory Method registry for MetricBase subclasses, self-registered via decorator (M3.1)."""
from __future__ import annotations

from typing import ClassVar

from deepeval.models.base_model import DeepEvalBaseLLM

from deepeval_platform.evaluation.errors import DuplicateMetricNameError, UnknownMetricError
from deepeval_platform.evaluation.metrics.metric_base import MetricBase


class MetricFactory:
    _registry: ClassVar[dict[str, type[MetricBase]]] = {}

    @classmethod
    def register(cls, name: str):
        def decorator(metric_cls: type[MetricBase]) -> type[MetricBase]:
            if name in cls._registry:
                raise DuplicateMetricNameError(name, cls._registry[name], metric_cls)
            cls._registry[name] = metric_cls
            return metric_cls

        return decorator

    @classmethod
    def is_registered(cls, name: str) -> bool:
        return name in cls._registry

    @classmethod
    def create(
        cls, name: str, *, threshold: float, deepeval_model: DeepEvalBaseLLM, **options: object
    ) -> MetricBase:
        if name not in cls._registry:
            raise UnknownMetricError(name, supported=sorted(cls._registry))
        return cls._registry[name](threshold=threshold, deepeval_model=deepeval_model, **options)
