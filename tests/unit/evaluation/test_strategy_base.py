"""Unit tests for EvaluationStrategyBase ABC (US2 — Metric Selection)."""
from __future__ import annotations

import pytest

from deepeval_platform.evaluation.strategy_base import EvaluationStrategyBase


class TestEvaluationStrategyBaseIsAbstract:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            EvaluationStrategyBase()

    def test_subclass_without_get_metrics_cannot_be_instantiated(self):
        class Incomplete(EvaluationStrategyBase):
            pass

        with pytest.raises(TypeError):
            Incomplete()

    def test_subclass_implementing_get_metrics_can_be_instantiated(self):
        class Complete(EvaluationStrategyBase):
            def get_metrics(self):
                return ["some_metric"]

        instance = Complete()
        assert instance.get_metrics() == ["some_metric"]
