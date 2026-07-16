"""CsvDatasetExporter — writes the full aggregate (metadata, goldens,
conversations, document failures) as one tagged-row CSV file (M4.1, R9).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from deepeval_platform.repositories.models import SyntheticDataset
from deepeval_platform.synthetic.dataset_exporter_base import DatasetExporterBase

_FIELDNAMES = [
    "record_type",
    "id",
    "bot_id",
    "org_id",
    "personas",
    "source_documents",
    "indexing_status",
    "created_at",
    "persona_name",
    "input",
    "expected_output",
    "context",
    "source_file",
    "scenario_name",
    "turns",
    "ending_status",
    "bot_error",
    "path",
    "stage",
    "error_type",
    "message",
]


class CsvDatasetExporter(DatasetExporterBase):
    def export(self, dataset: SyntheticDataset, output_dir: str) -> Path:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        path = output_path / f"{dataset.id}.csv"

        with open(path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
            writer.writeheader()

            writer.writerow(
                {
                    "record_type": "dataset_metadata",
                    "id": str(dataset.id),
                    "bot_id": dataset.bot_id,
                    "org_id": str(dataset.org_id) if dataset.org_id is not None else "",
                    "personas": json.dumps(dataset.personas),
                    "source_documents": json.dumps(dataset.source_documents),
                    "indexing_status": dataset.indexing_status,
                    "created_at": dataset.created_at.isoformat(),
                }
            )

            for golden in dataset.goldens:
                writer.writerow(
                    {
                        "record_type": "golden",
                        "id": str(golden.id),
                        "persona_name": golden.persona_name,
                        "input": golden.input,
                        "expected_output": golden.expected_output or "",
                        "context": json.dumps(golden.context),
                        "source_file": golden.source_file,
                    }
                )

            for conversation in dataset.conversations:
                writer.writerow(
                    {
                        "record_type": "conversation",
                        "id": str(conversation.id),
                        "persona_name": conversation.persona_name,
                        "scenario_name": conversation.scenario_name,
                        "turns": json.dumps(conversation.turns),
                        "ending_status": conversation.ending_status,
                        "bot_error": json.dumps(conversation.bot_error)
                        if conversation.bot_error
                        else "",
                    }
                )

            for failure in dataset.document_failures:
                writer.writerow(
                    {
                        "record_type": "document_failure",
                        "path": failure.path,
                        "stage": failure.stage,
                        "error_type": failure.error_type,
                        "message": failure.message,
                    }
                )

        return path
