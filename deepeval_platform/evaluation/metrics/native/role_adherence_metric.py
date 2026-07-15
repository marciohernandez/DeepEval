"""RoleAdherenceMetricWrapper — self-registers under 'role_adherence' (M3.3, US3, FR-008/FR-010a).

Optional chatbot_role, sourced from bots.yaml via BotMetricConfigResolver/EvaluationOrchestrator
(FR-010a); its absence isolates only this metric via the native MissingTestCaseParamsError,
propagated uncaught through measure() per research.md §R2 — no bespoke validation here.
"""
from __future__ import annotations

from deepeval.metrics import RoleAdherenceMetric
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.test_case import ConversationalTestCase

from deepeval_platform.evaluation.metrics.conversational_metric_base import (
    ConversationalMetricBase,
)
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.normalization.models import NormalizedTrace


@MetricFactory.register("role_adherence")
class RoleAdherenceMetricWrapper(ConversationalMetricBase):
    _native_metric_cls = RoleAdherenceMetric

    def __init__(
        self, threshold: float, deepeval_model: DeepEvalBaseLLM, chatbot_role: str | None = None
    ) -> None:
        super().__init__(threshold, deepeval_model)
        self._chatbot_role = chatbot_role

    def _build_test_case(self, trace: NormalizedTrace) -> ConversationalTestCase:
        return ConversationalMetricBase._build_test_case(trace, chatbot_role=self._chatbot_role)
