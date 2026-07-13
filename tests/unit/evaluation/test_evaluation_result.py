"""Unit tests for MetricResult + EvaluationResult (M3.1, data-model.md, FR-006/FR-007)."""
from __future__ import annotations

from deepeval_platform.evaluation.errors import ErrorDetail
from deepeval_platform.evaluation.evaluation_result import EvaluationResult, MetricResult


class TestMetricResult:
    def test_successful_result_has_no_error(self):
        result = MetricResult(score=0.9, threshold=0.8, passed=True, error=None)
        assert result.score == 0.9
        assert result.threshold == 0.8
        assert result.passed is True
        assert result.error is None

    def test_failed_result_score_is_none_never_coerced_to_zero(self):
        detail = ErrorDetail(category="TimeoutError", message="metric timed out")
        result = MetricResult(score=None, threshold=0.8, passed=False, error=detail)
        assert result.score is None
        assert result.score != 0.0
        assert result.passed is False
        assert result.error is detail

    def test_threshold_always_populated_even_on_failure(self):
        detail = ErrorDetail(category="ValueError", message="boom")
        result = MetricResult(score=None, threshold=0.8, passed=False, error=detail)
        assert result.threshold == 0.8


class TestEvaluationResult:
    def test_passed_true_when_all_metrics_pass(self):
        metrics = {
            "answer_relevancy": MetricResult(score=0.9, threshold=0.7, passed=True, error=None),
            "faithfulness": MetricResult(score=0.85, threshold=0.8, passed=True, error=None),
        }
        result = EvaluationResult(passed=all(m.passed for m in metrics.values()), metrics=metrics)
        assert result.passed is True

    def test_passed_false_when_any_metric_fails(self):
        metrics = {
            "answer_relevancy": MetricResult(score=0.9, threshold=0.7, passed=True, error=None),
            "faithfulness": MetricResult(score=0.5, threshold=0.8, passed=False, error=None),
        }
        result = EvaluationResult(passed=all(m.passed for m in metrics.values()), metrics=metrics)
        assert result.passed is False

    def test_metrics_dict_keyed_by_canonical_name(self):
        metrics = {
            "faithfulness": MetricResult(score=0.85, threshold=0.8, passed=True, error=None),
        }
        result = EvaluationResult(passed=True, metrics=metrics)
        assert set(result.metrics.keys()) == {"faithfulness"}
