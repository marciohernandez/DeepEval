"""Unit tests for EvaluationConfig/MetricThreshold (M4.2, data-model.md, contracts/evaluator-api.md).

EvaluationConfig is a passive value object: it normalizes/validates only what needs no
collaborator (UTC normalization, period ordering). Metric/threshold/bot validation is
Evaluator.start()'s responsibility and is NOT covered here (see test_evaluator.py).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from deepeval_platform.evaluation.errors import InvalidPeriodError
from deepeval_platform.evaluation.evaluation_config import EvaluationConfig, MetricThreshold


class TestMetricThresholdConstruction:
    def test_requires_name_and_threshold(self):
        with pytest.raises(TypeError):
            MetricThreshold()

    def test_requires_threshold_when_name_given(self):
        with pytest.raises(TypeError):
            MetricThreshold(name="faithfulness")

    def test_requires_name_when_threshold_given(self):
        with pytest.raises(TypeError):
            MetricThreshold(threshold=0.5)

    def test_construction_does_not_coerce_raw_threshold(self):
        threshold = MetricThreshold(name="faithfulness", threshold="0.5")
        # No coercion at construction time — the raw string is preserved as-is;
        # Evaluator.start() is the only place that validates/converts it.
        assert threshold.threshold == "0.5"


class TestEvaluationConfigUtcNormalization:
    def test_naive_period_start_means_utc(self):
        config = EvaluationConfig(
            bot_id="test_rag_bot",
            metric_thresholds=[MetricThreshold("faithfulness", 0.8)],
            period_start=datetime(2026, 7, 1, 12, 0, 0),
            period_end=datetime(2026, 7, 8),
        )
        assert config.period_start == datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert config.period_start.tzinfo is timezone.utc

    def test_naive_period_end_means_utc(self):
        config = EvaluationConfig(
            bot_id="test_rag_bot",
            metric_thresholds=[MetricThreshold("faithfulness", 0.8)],
            period_start=datetime(2026, 7, 1),
            period_end=datetime(2026, 7, 8, 6, 30, 0),
        )
        assert config.period_end == datetime(2026, 7, 8, 6, 30, 0, tzinfo=timezone.utc)

    def test_aware_period_start_converted_to_utc(self):
        from datetime import timedelta

        minus_three = timezone(timedelta(hours=-3))
        config = EvaluationConfig(
            bot_id="test_rag_bot",
            metric_thresholds=[MetricThreshold("faithfulness", 0.8)],
            period_start=datetime(2026, 7, 1, 9, 0, 0, tzinfo=minus_three),
            period_end=datetime(2026, 7, 8, tzinfo=timezone.utc),
        )
        assert config.period_start == datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert config.period_start.tzinfo is timezone.utc

    def test_non_datetime_period_start_raises_type_error(self):
        with pytest.raises(TypeError):
            EvaluationConfig(
                bot_id="test_rag_bot",
                metric_thresholds=[MetricThreshold("faithfulness", 0.8)],
                period_start="2026-07-01",
                period_end=datetime(2026, 7, 8, tzinfo=timezone.utc),
            )

    def test_non_datetime_period_end_raises_type_error(self):
        with pytest.raises(TypeError):
            EvaluationConfig(
                bot_id="test_rag_bot",
                metric_thresholds=[MetricThreshold("faithfulness", 0.8)],
                period_start=datetime(2026, 7, 1, tzinfo=timezone.utc),
                period_end="2026-07-08",
            )


class TestEvaluationConfigPeriodOrdering:
    def test_period_end_not_later_than_period_start_raises_invalid_period_error(self):
        with pytest.raises(InvalidPeriodError):
            EvaluationConfig(
                bot_id="test_rag_bot",
                metric_thresholds=[MetricThreshold("faithfulness", 0.8)],
                period_start=datetime(2026, 7, 8, tzinfo=timezone.utc),
                period_end=datetime(2026, 7, 1, tzinfo=timezone.utc),
            )

    def test_equal_boundaries_raise_invalid_period_error(self):
        same = datetime(2026, 7, 1, tzinfo=timezone.utc)
        with pytest.raises(InvalidPeriodError):
            EvaluationConfig(
                bot_id="test_rag_bot",
                metric_thresholds=[MetricThreshold("faithfulness", 0.8)],
                period_start=same,
                period_end=same,
            )

    def test_error_carries_normalized_boundaries(self):
        with pytest.raises(InvalidPeriodError) as exc_info:
            EvaluationConfig(
                bot_id="test_rag_bot",
                metric_thresholds=[MetricThreshold("faithfulness", 0.8)],
                period_start=datetime(2026, 7, 8),
                period_end=datetime(2026, 7, 1),
            )
        assert exc_info.value.period_start == datetime(2026, 7, 8, tzinfo=timezone.utc)
        assert exc_info.value.period_end == datetime(2026, 7, 1, tzinfo=timezone.utc)


class TestEvaluationConfigPreservesDuplicateEntries:
    def test_duplicate_metric_names_preserved_until_evaluator_validates(self):
        thresholds = [
            MetricThreshold("faithfulness", 0.8),
            MetricThreshold("faithfulness", 0.9),
        ]
        config = EvaluationConfig(
            bot_id="test_rag_bot",
            metric_thresholds=thresholds,
            period_start=datetime(2026, 7, 1, tzinfo=timezone.utc),
            period_end=datetime(2026, 7, 8, tzinfo=timezone.utc),
        )
        assert config.metric_thresholds == thresholds
        assert len(config.metric_thresholds) == 2

    def test_empty_metric_thresholds_preserved_not_rejected_here(self):
        config = EvaluationConfig(
            bot_id="test_rag_bot",
            metric_thresholds=[],
            period_start=datetime(2026, 7, 1, tzinfo=timezone.utc),
            period_end=datetime(2026, 7, 8, tzinfo=timezone.utc),
        )
        assert config.metric_thresholds == []
