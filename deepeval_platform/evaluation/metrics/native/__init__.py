"""Importing this package triggers every native wrapper's @MetricFactory.register self-registration."""
from __future__ import annotations

from deepeval_platform.evaluation.metrics.native import (
    answer_relevancy_metric,  # noqa: F401
    bias_metric,  # noqa: F401
    contextual_precision_metric,  # noqa: F401
    contextual_recall_metric,  # noqa: F401
    contextual_relevancy_metric,  # noqa: F401
    conversation_completeness_metric,  # noqa: F401
    conversation_relevancy_metric,  # noqa: F401
    conversational_g_eval_metric,  # noqa: F401
    faithfulness_metric,  # noqa: F401
    hallucination_metric,  # noqa: F401
    json_correctness_metric,  # noqa: F401
    knowledge_retention_metric,  # noqa: F401
    prompt_alignment_metric,  # noqa: F401
    role_adherence_metric,  # noqa: F401
    summarization_metric,  # noqa: F401
    task_completion_metric,  # noqa: F401
    tool_correctness_metric,  # noqa: F401
    toxicity_metric,  # noqa: F401
)
