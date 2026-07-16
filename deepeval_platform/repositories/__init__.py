"""Repository layer public API (US5, US6, M4.1)."""
from deepeval_platform.repositories.dataset_repository import DatasetRepository
from deepeval_platform.repositories.dataset_repository import RepositoryError as DatasetRepositoryError
from deepeval_platform.repositories.evaluation_repository import EvaluationRepository, RepositoryError
from deepeval_platform.repositories.models import (
    ConversationEndingStatus,
    ConversationRecord,
    DocumentFailure,
    EvaluationResult,
    GoldenRecord,
    SearchResult,
    SyntheticDataset,
    TraceRecord,
)
from deepeval_platform.repositories.trace_repository import TraceRepository, TraceRepositoryError

__all__ = [
    "ConversationEndingStatus",
    "ConversationRecord",
    "DatasetRepository",
    "DatasetRepositoryError",
    "DocumentFailure",
    "EvaluationRepository",
    "EvaluationResult",
    "GoldenRecord",
    "RepositoryError",
    "SearchResult",
    "SyntheticDataset",
    "TraceRecord",
    "TraceRepository",
    "TraceRepositoryError",
]
