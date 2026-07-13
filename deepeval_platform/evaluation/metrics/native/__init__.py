"""Importing this package triggers every native wrapper's @MetricFactory.register self-registration."""
from __future__ import annotations

from deepeval_platform.evaluation.metrics.native import (
    answer_relevancy_metric,  # noqa: F401
    contextual_precision_metric,  # noqa: F401
    contextual_recall_metric,  # noqa: F401
    contextual_relevancy_metric,  # noqa: F401
    faithfulness_metric,  # noqa: F401
    tool_correctness_metric,  # noqa: F401
)
