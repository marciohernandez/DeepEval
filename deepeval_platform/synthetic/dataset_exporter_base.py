"""DatasetExporterBase — export strategy contract (M4.1, R9)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from deepeval_platform.repositories.models import SyntheticDataset


class DatasetExporterBase(ABC):
    @abstractmethod
    def export(self, dataset: SyntheticDataset, output_dir: str) -> Path:
        ...
