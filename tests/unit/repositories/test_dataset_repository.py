"""Unit tests for DatasetRepository (M4.1, T027). Supabase and Qdrant are mocked."""
from __future__ import annotations

import inspect
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from deepeval_platform.repositories.dataset_repository import (
    DatasetRepository,
    RepositoryError,
)
from deepeval_platform.repositories.models import (
    ConversationRecord,
    DocumentFailure,
    GoldenRecord,
    SyntheticDataset,
)
from deepeval_platform.synthetic.authorization import AuthenticatedPrincipal

_ORG_ID = UUID("22222222-2222-2222-2222-222222222222")
_OTHER_ORG_ID = UUID("33333333-3333-3333-3333-333333333333")
_USER_ID = UUID("11111111-1111-1111-1111-111111111111")


def _chainable_table(execute_return):
    table = MagicMock()
    table.insert.return_value = table
    table.select.return_value = table
    table.update.return_value = table
    table.eq.return_value = table
    table.execute.return_value = execute_return
    return table


def _response(data):
    response = MagicMock()
    response.data = data
    return response


def _principal(org_id: UUID = _ORG_ID, tables: dict | None = None) -> AuthenticatedPrincipal:
    client = MagicMock()
    tables = tables or {}
    client.table.side_effect = lambda name: tables.get(name, _chainable_table(_response([])))
    return AuthenticatedPrincipal(
        user_id=_USER_ID, org_id=org_id, access_token="tok", supabase_client=client
    )


def _golden(dataset_id: UUID, **overrides) -> GoldenRecord:
    defaults = dict(
        id=uuid4(),
        dataset_id=dataset_id,
        org_id=_ORG_ID,
        persona_name="frustrated_customer",
        input="Where is my order?",
        expected_output="It shipped yesterday.",
        context=["order context"],
        source_file="docs/order.md",
    )
    defaults.update(overrides)
    return GoldenRecord(**defaults)


def _conversation(dataset_id: UUID, **overrides) -> ConversationRecord:
    defaults = dict(
        id=uuid4(),
        dataset_id=dataset_id,
        org_id=_ORG_ID,
        persona_name="frustrated_customer",
        scenario_name="refund_request",
        turns=[{"role": "user", "content": "hi", "metadata": {}}],
        ending_status="expected_outcome_reached",
        bot_error=None,
    )
    defaults.update(overrides)
    return ConversationRecord(**defaults)


def _dataset(**overrides) -> SyntheticDataset:
    dataset_id = overrides.pop("id", uuid4())
    defaults = dict(
        id=dataset_id,
        bot_id="test_rag_bot",
        org_id=_ORG_ID,
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
        indexing_status="pending",
        created_at=datetime.now(timezone.utc),
        goldens=[_golden(dataset_id)],
        conversations=[_conversation(dataset_id)],
    )
    defaults.update(overrides)
    return SyntheticDataset(**defaults)


@pytest.fixture
def qdrant_provider():
    provider = MagicMock()
    store = MagicMock()
    provider.get_store.return_value = store
    return provider, store


class TestNoExportMethods:
    def test_repository_has_no_export_method(self):
        methods = {name for name, _ in inspect.getmembers(DatasetRepository, predicate=callable)}
        assert not any("export" in name for name in methods)


class TestPrincipalOnlySignatures:
    @pytest.mark.parametrize(
        "method_name",
        ["save", "get_by_id", "get_by_bot", "search_content", "retry_indexing"],
    )
    def test_no_org_id_or_access_token_parameter(self, method_name):
        method = getattr(DatasetRepository, method_name)
        params = set(inspect.signature(method).parameters)
        assert "org_id" not in params
        assert "access_token" not in params
        assert "principal" in params


class TestSaveAggregateRowMapping:
    def test_save_inserts_dataset_golden_and_conversation_rows(self, qdrant_provider):
        provider, store = qdrant_provider
        dataset_table = _chainable_table(_response([{"id": "x"}]))
        golden_table = _chainable_table(_response([{"id": "x"}]))
        conversation_table = _chainable_table(_response([{"id": "x"}]))
        tables = {
            "synthetic_datasets": dataset_table,
            "synthetic_goldens": golden_table,
            "synthetic_conversations": conversation_table,
        }
        principal = _principal(tables=tables)
        dataset = _dataset()
        repo = DatasetRepository(qdrant_provider=provider)

        returned_id = repo.save(dataset, principal=principal)

        assert returned_id == dataset.id
        dataset_insert_payload = dataset_table.insert.call_args.args[0]
        assert dataset_insert_payload["id"] == str(dataset.id)
        assert dataset_insert_payload["bot_id"] == "test_rag_bot"
        assert dataset_insert_payload["document_failures"] == [
            {
                "path": "docs/corrupt.pdf",
                "stage": "parsing",
                "error_type": "PdfReadError",
                "message": "could not parse",
            }
        ]

        golden_insert_payload = golden_table.insert.call_args.args[0]
        assert golden_insert_payload[0]["dataset_id"] == str(dataset.id)
        assert golden_insert_payload[0]["input"] == "Where is my order?"

        conversation_insert_payload = conversation_table.insert.call_args.args[0]
        assert conversation_insert_payload[0]["ending_status"] == "expected_outcome_reached"

    def test_save_raises_repository_error_on_supabase_failure(self, qdrant_provider):
        provider, _ = qdrant_provider
        dataset_table = MagicMock()
        dataset_table.insert.side_effect = Exception("db down")
        principal = _principal(tables={"synthetic_datasets": dataset_table})
        repo = DatasetRepository(qdrant_provider=provider)

        with pytest.raises(RepositoryError):
            repo.save(_dataset(), principal=principal)


class TestBothContentTypesIndexed:
    def test_add_texts_called_with_goldens_and_conversations(self, qdrant_provider):
        provider, store = qdrant_provider
        principal = _principal()
        dataset = _dataset()
        repo = DatasetRepository(qdrant_provider=provider)

        repo.save(dataset, principal=principal)

        _, kwargs = store.add_texts.call_args
        metadatas = kwargs["metadatas"]
        content_types = {m["content_type"] for m in metadatas}
        assert content_types == {"golden", "conversation"}
        assert all(m["dataset_id"] == str(dataset.id) for m in metadatas)


class TestFailedIndexingCleanupAndRetry:
    def test_indexing_failure_deletes_points_and_marks_failed(self, qdrant_provider):
        provider, store = qdrant_provider
        store.add_texts.side_effect = Exception("qdrant down")
        dataset_table = _chainable_table(_response([{"id": "x"}]))
        principal = _principal(tables={"synthetic_datasets": dataset_table})
        dataset = _dataset()
        repo = DatasetRepository(qdrant_provider=provider)

        repo.save(dataset, principal=principal)

        store.client.delete.assert_called_once()
        update_call = dataset_table.update.call_args.args[0]
        assert update_call["indexing_status"] == "failed"

    def test_retry_indexing_reloads_and_reattempts_full_index(self, qdrant_provider):
        provider, store = qdrant_provider
        dataset = _dataset(indexing_status="failed")
        dataset_row = {
            "id": str(dataset.id),
            "bot_id": dataset.bot_id,
            "org_id": str(_ORG_ID),
            "personas": dataset.personas,
            "source_documents": dataset.source_documents,
            "document_failures": [
                {
                    "path": f.path,
                    "stage": f.stage,
                    "error_type": f.error_type,
                    "message": f.message,
                }
                for f in dataset.document_failures
            ],
            "indexing_status": "failed",
            "created_at": dataset.created_at.isoformat(),
        }
        golden_row = {
            "id": str(dataset.goldens[0].id),
            "dataset_id": str(dataset.id),
            "org_id": str(_ORG_ID),
            "persona_name": dataset.goldens[0].persona_name,
            "input": dataset.goldens[0].input,
            "expected_output": dataset.goldens[0].expected_output,
            "context": dataset.goldens[0].context,
            "source_file": dataset.goldens[0].source_file,
        }
        conversation_row = {
            "id": str(dataset.conversations[0].id),
            "dataset_id": str(dataset.id),
            "org_id": str(_ORG_ID),
            "persona_name": dataset.conversations[0].persona_name,
            "scenario_name": dataset.conversations[0].scenario_name,
            "turns": dataset.conversations[0].turns,
            "ending_status": dataset.conversations[0].ending_status,
            "bot_error": dataset.conversations[0].bot_error,
        }
        dataset_table = _chainable_table(_response([dataset_row]))
        golden_table = _chainable_table(_response([golden_row]))
        conversation_table = _chainable_table(_response([conversation_row]))
        principal = _principal(
            tables={
                "synthetic_datasets": dataset_table,
                "synthetic_goldens": golden_table,
                "synthetic_conversations": conversation_table,
            }
        )
        repo = DatasetRepository(qdrant_provider=provider)

        repo.retry_indexing(dataset.id, principal=principal)

        store.add_texts.assert_called_once()
        update_call = dataset_table.update.call_args.args[0]
        assert update_call["indexing_status"] == "indexed"


class TestNormalizedSearch:
    def test_search_returns_normalized_search_results_for_indexed_datasets(self, qdrant_provider):
        provider, store = qdrant_provider
        indexed_dataset_id = uuid4()
        dataset_table = _chainable_table(
            _response([{"id": str(indexed_dataset_id)}])
        )
        principal = _principal(tables={"synthetic_datasets": dataset_table})

        golden_id = uuid4()
        doc = MagicMock()
        doc.page_content = "Where is my order? -> It shipped yesterday."
        doc.metadata = {
            "content_type": "golden",
            "source_record_id": str(golden_id),
            "dataset_id": str(indexed_dataset_id),
            "persona_name": "frustrated_customer",
            "source_file": "docs/order.md",
        }
        store.similarity_search_with_score.return_value = [(doc, 0.87)]

        repo = DatasetRepository(qdrant_provider=provider)
        results = repo.search_content("order status", principal=principal, k=5)

        assert len(results) == 1
        result = results[0]
        assert result.content_type == "golden"
        assert result.source_record_id == golden_id
        assert result.dataset_id == indexed_dataset_id
        assert result.persona_name == "frustrated_customer"
        assert result.text == "Where is my order? -> It shipped yesterday."
        assert result.score == 0.87

    def test_search_returns_empty_when_no_indexed_datasets_for_org(self, qdrant_provider):
        provider, store = qdrant_provider
        dataset_table = _chainable_table(_response([]))
        principal = _principal(tables={"synthetic_datasets": dataset_table})

        repo = DatasetRepository(qdrant_provider=provider)
        results = repo.search_content("order status", principal=principal, k=5)

        assert results == []
        store.similarity_search_with_score.assert_not_called()


class TestSameOrgFiltering:
    def test_get_by_id_filters_by_principal_org(self, qdrant_provider):
        provider, _ = qdrant_provider
        dataset_id = uuid4()
        dataset_row = {
            "id": str(dataset_id),
            "bot_id": "test_rag_bot",
            "org_id": str(_ORG_ID),
            "personas": ["frustrated_customer"],
            "source_documents": ["docs/order.md"],
            "document_failures": [],
            "indexing_status": "indexed",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        dataset_table = _chainable_table(_response([dataset_row]))
        golden_table = _chainable_table(_response([]))
        conversation_table = _chainable_table(_response([]))
        principal = _principal(
            tables={
                "synthetic_datasets": dataset_table,
                "synthetic_goldens": golden_table,
                "synthetic_conversations": conversation_table,
            }
        )

        repo = DatasetRepository(qdrant_provider=provider)
        result = repo.get_by_id(dataset_id, principal=principal)

        assert result.id == dataset_id
        eq_calls = [call.args for call in dataset_table.eq.call_args_list]
        assert ("org_id", str(_ORG_ID)) in eq_calls

    def test_get_by_id_missing_raises(self, qdrant_provider):
        provider, _ = qdrant_provider
        dataset_table = _chainable_table(_response([]))
        principal = _principal(tables={"synthetic_datasets": dataset_table})

        repo = DatasetRepository(qdrant_provider=provider)
        with pytest.raises(RepositoryError):
            repo.get_by_id(uuid4(), principal=principal)


class TestDistinctRunIds:
    def test_two_datasets_for_same_bot_have_distinct_ids(self):
        first = _dataset()
        second = _dataset()
        assert first.id != second.id


class TestStructuredDocumentFailuresRoundTrip:
    def test_document_failures_reloaded_as_document_failure_instances(self, qdrant_provider):
        provider, _ = qdrant_provider
        dataset_id = uuid4()
        dataset_row = {
            "id": str(dataset_id),
            "bot_id": "test_rag_bot",
            "org_id": str(_ORG_ID),
            "personas": [],
            "source_documents": [],
            "document_failures": [
                {
                    "path": "docs/corrupt.pdf",
                    "stage": "parsing",
                    "error_type": "PdfReadError",
                    "message": "could not parse",
                }
            ],
            "indexing_status": "indexed",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        dataset_table = _chainable_table(_response([dataset_row]))
        golden_table = _chainable_table(_response([]))
        conversation_table = _chainable_table(_response([]))
        principal = _principal(
            tables={
                "synthetic_datasets": dataset_table,
                "synthetic_goldens": golden_table,
                "synthetic_conversations": conversation_table,
            }
        )

        repo = DatasetRepository(qdrant_provider=provider)
        result = repo.get_by_id(dataset_id, principal=principal)

        assert len(result.document_failures) == 1
        failure = result.document_failures[0]
        assert isinstance(failure, DocumentFailure)
        assert failure.stage == "parsing"


class TestConversationBotErrorRoundTrip:
    def test_bot_error_preserved_through_persist_and_reload(self, qdrant_provider):
        provider, _ = qdrant_provider
        dataset_id = uuid4()
        bot_error = {
            "code": "invocation_error",
            "type": "RuntimeError",
            "message": "boom",
            "bot_id": "test_rag_bot",
        }
        dataset_row = {
            "id": str(dataset_id),
            "bot_id": "test_rag_bot",
            "org_id": str(_ORG_ID),
            "personas": [],
            "source_documents": [],
            "document_failures": [],
            "indexing_status": "indexed",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        conversation_row = {
            "id": str(uuid4()),
            "dataset_id": str(dataset_id),
            "org_id": str(_ORG_ID),
            "persona_name": "frustrated_customer",
            "scenario_name": "refund_request",
            "turns": [{"role": "user", "content": "hi", "metadata": {}}],
            "ending_status": "bot_failure",
            "bot_error": bot_error,
        }
        dataset_table = _chainable_table(_response([dataset_row]))
        golden_table = _chainable_table(_response([]))
        conversation_table = _chainable_table(_response([conversation_row]))
        principal = _principal(
            tables={
                "synthetic_datasets": dataset_table,
                "synthetic_goldens": golden_table,
                "synthetic_conversations": conversation_table,
            }
        )

        repo = DatasetRepository(qdrant_provider=provider)
        result = repo.get_by_id(dataset_id, principal=principal)

        assert result.conversations[0].ending_status == "bot_failure"
        assert result.conversations[0].bot_error == bot_error


class TestCoverageGaps:
    """Closes coverage gaps identified by T043 for dataset_repository.py."""

    def test_get_by_id_raises_repository_error_on_supabase_failure(self, qdrant_provider):
        provider, _ = qdrant_provider
        dataset_table = MagicMock()
        dataset_table.select.return_value = dataset_table
        dataset_table.eq.return_value = dataset_table
        dataset_table.execute.side_effect = Exception("db unreachable")
        principal = _principal(tables={"synthetic_datasets": dataset_table})

        repo = DatasetRepository(qdrant_provider=provider)
        with pytest.raises(RepositoryError):
            repo.get_by_id(uuid4(), principal=principal)

    def test_get_by_bot_returns_matching_datasets(self, qdrant_provider):
        provider, _ = qdrant_provider
        dataset_id = uuid4()
        dataset_row = {
            "id": str(dataset_id),
            "bot_id": "test_rag_bot",
            "org_id": str(_ORG_ID),
            "personas": [],
            "source_documents": [],
            "document_failures": [],
            "indexing_status": "indexed",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        dataset_table = _chainable_table(_response([dataset_row]))
        golden_table = _chainable_table(_response([]))
        conversation_table = _chainable_table(_response([]))
        principal = _principal(
            tables={
                "synthetic_datasets": dataset_table,
                "synthetic_goldens": golden_table,
                "synthetic_conversations": conversation_table,
            }
        )

        repo = DatasetRepository(qdrant_provider=provider)
        results = repo.get_by_bot("test_rag_bot", principal=principal)

        assert len(results) == 1
        assert results[0].id == dataset_id

    def test_get_by_bot_raises_repository_error_on_supabase_failure(self, qdrant_provider):
        provider, _ = qdrant_provider
        dataset_table = MagicMock()
        dataset_table.select.return_value = dataset_table
        dataset_table.eq.return_value = dataset_table
        dataset_table.execute.side_effect = Exception("db unreachable")
        principal = _principal(tables={"synthetic_datasets": dataset_table})

        repo = DatasetRepository(qdrant_provider=provider)
        with pytest.raises(RepositoryError):
            repo.get_by_bot("test_rag_bot", principal=principal)

    def test_search_content_raises_repository_error_on_supabase_failure(self, qdrant_provider):
        provider, _ = qdrant_provider
        dataset_table = MagicMock()
        dataset_table.select.return_value = dataset_table
        dataset_table.eq.return_value = dataset_table
        dataset_table.execute.side_effect = Exception("db unreachable")
        principal = _principal(tables={"synthetic_datasets": dataset_table})

        repo = DatasetRepository(qdrant_provider=provider)
        with pytest.raises(RepositoryError):
            repo.search_content("query", principal=principal)

    def test_search_content_excludes_hits_outside_authorized_datasets(self, qdrant_provider):
        provider, store = qdrant_provider
        authorized_id = uuid4()
        unauthorized_id = uuid4()
        dataset_table = _chainable_table(_response([{"id": str(authorized_id)}]))
        principal = _principal(tables={"synthetic_datasets": dataset_table})

        authorized_doc = MagicMock()
        authorized_doc.page_content = "authorized text"
        authorized_doc.metadata = {
            "content_type": "golden",
            "source_record_id": str(uuid4()),
            "dataset_id": str(authorized_id),
            "persona_name": "frustrated_customer",
        }
        unauthorized_doc = MagicMock()
        unauthorized_doc.page_content = "unauthorized text"
        unauthorized_doc.metadata = {
            "content_type": "golden",
            "source_record_id": str(uuid4()),
            "dataset_id": str(unauthorized_id),
            "persona_name": "frustrated_customer",
        }
        store.similarity_search_with_score.return_value = [
            (authorized_doc, 0.9),
            (unauthorized_doc, 0.95),
        ]

        repo = DatasetRepository(qdrant_provider=provider)
        results = repo.search_content("query", principal=principal, k=5)

        assert len(results) == 1
        assert results[0].dataset_id == authorized_id

    def test_index_content_with_no_goldens_or_conversations_marks_indexed(self, qdrant_provider):
        provider, store = qdrant_provider
        dataset_table = _chainable_table(_response([{"id": "x"}]))
        principal = _principal(tables={"synthetic_datasets": dataset_table})
        dataset = _dataset(goldens=[], conversations=[])

        repo = DatasetRepository(qdrant_provider=provider)
        repo.save(dataset, principal=principal)

        store.add_texts.assert_not_called()
        update_call = dataset_table.update.call_args.args[0]
        assert update_call["indexing_status"] == "indexed"

    def test_cleanup_failure_itself_is_swallowed(self, qdrant_provider):
        provider, store = qdrant_provider
        store.add_texts.side_effect = Exception("qdrant down")
        store.client.delete.side_effect = Exception("delete also fails")
        dataset_table = _chainable_table(_response([{"id": "x"}]))
        principal = _principal(tables={"synthetic_datasets": dataset_table})
        dataset = _dataset()

        repo = DatasetRepository(qdrant_provider=provider)
        # Must not raise even though both the write and the cleanup delete fail.
        repo.save(dataset, principal=principal)

        update_call = dataset_table.update.call_args.args[0]
        assert update_call["indexing_status"] == "failed"

    def test_load_aggregate_raises_repository_error_when_child_query_fails(self, qdrant_provider):
        provider, _ = qdrant_provider
        dataset_id = uuid4()
        dataset_row = {
            "id": str(dataset_id),
            "bot_id": "test_rag_bot",
            "org_id": str(_ORG_ID),
            "personas": [],
            "source_documents": [],
            "document_failures": [],
            "indexing_status": "indexed",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        dataset_table = _chainable_table(_response([dataset_row]))
        golden_table = MagicMock()
        golden_table.select.return_value = golden_table
        golden_table.eq.return_value = golden_table
        golden_table.execute.side_effect = Exception("child query failed")
        principal = _principal(
            tables={"synthetic_datasets": dataset_table, "synthetic_goldens": golden_table}
        )

        repo = DatasetRepository(qdrant_provider=provider)
        with pytest.raises(RepositoryError):
            repo.get_by_id(dataset_id, principal=principal)
