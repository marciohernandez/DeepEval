"""Unit tests for JsonDatasetExporter/CsvDatasetExporter (M4.1, T028)."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from deepeval_platform.repositories.models import (
    ConversationRecord,
    DocumentFailure,
    GoldenRecord,
    SyntheticDataset,
)
from deepeval_platform.synthetic.csv_dataset_exporter import CsvDatasetExporter
from deepeval_platform.synthetic.json_dataset_exporter import JsonDatasetExporter


def _dataset() -> SyntheticDataset:
    dataset_id = uuid4()
    golden = GoldenRecord(
        id=uuid4(),
        dataset_id=dataset_id,
        org_id=None,
        persona_name="frustrated_customer",
        input="Where is my order?",
        expected_output="It shipped yesterday.",
        context=["order context"],
        source_file="docs/order.md",
    )
    conversation = ConversationRecord(
        id=uuid4(),
        dataset_id=dataset_id,
        org_id=None,
        persona_name="frustrated_customer",
        scenario_name="refund_request",
        turns=[
            {"role": "user", "content": "hi", "metadata": {}},
            {"role": "assistant", "content": "[BOT_UNREACHABLE]", "metadata": {"error": {"code": "invocation_error"}}},
        ],
        ending_status="bot_failure",
        bot_error={"code": "invocation_error", "type": "RuntimeError", "message": "boom", "bot_id": "test_rag_bot"},
    )
    return SyntheticDataset(
        id=dataset_id,
        bot_id="test_rag_bot",
        org_id=None,
        personas=["frustrated_customer"],
        source_documents=["docs/order.md"],
        document_failures=[
            DocumentFailure(
                path="docs/corrupt.pdf",
                stage="parsing",
                error_type="PdfReadError",
                message="could not parse",
            )
        ],
        indexing_status="indexed",
        created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        goldens=[golden],
        conversations=[conversation],
    )


class TestJsonDatasetExporter:
    def test_export_writes_json_with_all_sections(self, tmp_path):
        dataset = _dataset()
        exporter = JsonDatasetExporter()

        path = exporter.export(dataset, str(tmp_path))

        assert path.exists()
        data = json.loads(path.read_text())
        assert data["bot_id"] == "test_rag_bot"
        assert len(data["goldens"]) == 1
        assert data["goldens"][0]["input"] == "Where is my order?"
        assert len(data["conversations"]) == 1
        assert data["conversations"][0]["ending_status"] == "bot_failure"
        assert data["conversations"][0]["bot_error"]["code"] == "invocation_error"
        assert len(data["document_failures"]) == 1
        assert data["document_failures"][0]["stage"] == "parsing"

    def test_export_does_not_leak_access_tokens(self, tmp_path):
        dataset = _dataset()
        exporter = JsonDatasetExporter()

        path = exporter.export(dataset, str(tmp_path))

        text = path.read_text()
        assert "access_token" not in text.lower()


class TestCsvDatasetExporter:
    def test_export_writes_csv_with_all_record_types(self, tmp_path):
        dataset = _dataset()
        exporter = CsvDatasetExporter()

        path = exporter.export(dataset, str(tmp_path))

        assert path.exists()
        with open(path, newline="") as fh:
            rows = list(csv.DictReader(fh))

        record_types = {row["record_type"] for row in rows}
        assert record_types == {"dataset_metadata", "golden", "conversation", "document_failure"}

        golden_rows = [r for r in rows if r["record_type"] == "golden"]
        assert golden_rows[0]["input"] == "Where is my order?"

        conversation_rows = [r for r in rows if r["record_type"] == "conversation"]
        assert conversation_rows[0]["ending_status"] == "bot_failure"
        assert "invocation_error" in conversation_rows[0]["bot_error"]

        failure_rows = [r for r in rows if r["record_type"] == "document_failure"]
        assert failure_rows[0]["stage"] == "parsing"

    def test_export_does_not_leak_access_tokens(self, tmp_path):
        dataset = _dataset()
        exporter = CsvDatasetExporter()

        path = exporter.export(dataset, str(tmp_path))

        text = path.read_text()
        assert "access_token" not in text.lower()
