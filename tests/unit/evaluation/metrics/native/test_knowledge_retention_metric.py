"""Unit tests for KnowledgeRetentionMetricWrapper self-registration (M3.3, US3, FR-008)."""
from __future__ import annotations

from deepeval.metrics import KnowledgeRetentionMetric

from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.knowledge_retention_metric import (
    KnowledgeRetentionMetricWrapper,
)


class TestKnowledgeRetentionMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["knowledge_retention"] is KnowledgeRetentionMetricWrapper

    def test_wraps_native_knowledge_retention_metric(self):
        assert (
            KnowledgeRetentionMetricWrapper._native_metric_cls is KnowledgeRetentionMetric
        )
