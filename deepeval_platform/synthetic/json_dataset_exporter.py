"""JsonDatasetExporter — writes the full aggregate (metadata, goldens,
conversations, document failures) as a single JSON file (M4.1, R9).
"""
from __future__ import annotations

import json
from pathlib import Path

from deepeval_platform.repositories.models import SyntheticDataset
from deepeval_platform.synthetic.dataset_exporter_base import DatasetExporterBase


class JsonDatasetExporter(DatasetExporterBase):
    def export(self, dataset: SyntheticDataset, output_dir: str) -> Path:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        path = output_path / f"{dataset.id}.json"

        data = {
            "id": str(dataset.id),
            "bot_id": dataset.bot_id,
            "org_id": str(dataset.org_id) if dataset.org_id is not None else None,
            "personas": dataset.personas,
            "source_documents": dataset.source_documents,
            "indexing_status": dataset.indexing_status,
            "created_at": dataset.created_at.isoformat(),
            "document_failures": [
                {
                    "path": failure.path,
                    "stage": failure.stage,
                    "error_type": failure.error_type,
                    "message": failure.message,
                }
                for failure in dataset.document_failures
            ],
            "goldens": [
                {
                    "id": str(golden.id),
                    "persona_name": golden.persona_name,
                    "input": golden.input,
                    "expected_output": golden.expected_output,
                    "context": golden.context,
                    "source_file": golden.source_file,
                }
                for golden in dataset.goldens
            ],
            "conversations": [
                {
                    "id": str(conversation.id),
                    "persona_name": conversation.persona_name,
                    "scenario_name": conversation.scenario_name,
                    "turns": conversation.turns,
                    "ending_status": conversation.ending_status,
                    "bot_error": conversation.bot_error,
                }
                for conversation in dataset.conversations
            ],
        }

        path.write_text(json.dumps(data, indent=2))
        return path
