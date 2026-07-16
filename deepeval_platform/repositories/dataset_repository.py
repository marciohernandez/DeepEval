"""DatasetRepository — persistence-only aggregate save/load/list, atomic-visibility
semantic indexing across goldens and conversations, normalized search, and
whole-dataset retry (M4.1, R7/R8). No export-format responsibility.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from deepeval_platform.repositories.models import (
    ConversationRecord,
    DocumentFailure,
    GoldenRecord,
    SearchResult,
    SyntheticDataset,
)
from deepeval_platform.synthetic.authorization import AuthenticatedPrincipal
from deepeval_platform.vector_store.qdrant_provider import QdrantVectorStoreProvider

_DATASET_TABLE = "synthetic_datasets"
_GOLDEN_TABLE = "synthetic_goldens"
_CONVERSATION_TABLE = "synthetic_conversations"
_COLLECTION = "synthetic_content"


class RepositoryError(Exception):
    pass


class DatasetRepository:
    def __init__(self, qdrant_provider: QdrantVectorStoreProvider | None = None) -> None:
        self._qdrant_provider = (
            qdrant_provider if qdrant_provider is not None else QdrantVectorStoreProvider.instance()
        )

    def save(self, dataset: SyntheticDataset, principal: AuthenticatedPrincipal) -> UUID:
        client = principal.supabase_client
        try:
            client.table(_DATASET_TABLE).insert(self._dataset_row(dataset)).execute()
            if dataset.goldens:
                client.table(_GOLDEN_TABLE).insert(
                    [self._golden_row(golden) for golden in dataset.goldens]
                ).execute()
            if dataset.conversations:
                client.table(_CONVERSATION_TABLE).insert(
                    [self._conversation_row(conversation) for conversation in dataset.conversations]
                ).execute()
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc

        self._index_content(dataset, principal)
        return dataset.id

    def get_by_id(self, dataset_id: UUID, principal: AuthenticatedPrincipal) -> SyntheticDataset:
        client = principal.supabase_client
        try:
            response = (
                client.table(_DATASET_TABLE)
                .select("*")
                .eq("id", str(dataset_id))
                .eq("org_id", str(principal.org_id))
                .execute()
            )
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc

        if not response.data:
            raise RepositoryError(f"SyntheticDataset {dataset_id} not found")

        return self._load_aggregate(response.data[0], principal)

    def get_by_bot(
        self, bot_id: str, principal: AuthenticatedPrincipal
    ) -> list[SyntheticDataset]:
        client = principal.supabase_client
        try:
            response = (
                client.table(_DATASET_TABLE)
                .select("*")
                .eq("bot_id", bot_id)
                .eq("org_id", str(principal.org_id))
                .execute()
            )
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc

        return [self._load_aggregate(row, principal) for row in response.data]

    def search_content(
        self, query: str, principal: AuthenticatedPrincipal, k: int = 5
    ) -> list[SearchResult]:
        client = principal.supabase_client
        try:
            response = (
                client.table(_DATASET_TABLE)
                .select("id")
                .eq("org_id", str(principal.org_id))
                .eq("indexing_status", "indexed")
                .execute()
            )
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc

        authorized_ids = {row["id"] for row in response.data}
        if not authorized_ids:
            return []

        store = self._qdrant_provider.get_store(_COLLECTION)
        search_filter = Filter(
            must=[
                FieldCondition(
                    key="metadata.dataset_id", match=MatchAny(any=list(authorized_ids))
                )
            ]
        )
        hits = store.similarity_search_with_score(query, k=k, filter=search_filter)

        results: list[SearchResult] = []
        for doc, score in hits:
            metadata = doc.metadata
            if metadata.get("dataset_id") not in authorized_ids:
                continue
            results.append(
                SearchResult(
                    content_type=metadata["content_type"],
                    source_record_id=UUID(metadata["source_record_id"]),
                    dataset_id=UUID(metadata["dataset_id"]),
                    persona_name=metadata["persona_name"],
                    text=doc.page_content,
                    score=score,
                    metadata=metadata,
                )
            )
        return results

    def retry_indexing(self, dataset_id: UUID, principal: AuthenticatedPrincipal) -> None:
        dataset = self.get_by_id(dataset_id, principal)
        self._index_content(dataset, principal)

    # -- indexing -----------------------------------------------------------

    def _index_content(self, dataset: SyntheticDataset, principal: AuthenticatedPrincipal) -> None:
        store = self._qdrant_provider.get_store(_COLLECTION)

        texts: list[str] = []
        metadatas: list[dict] = []
        ids: list[str] = []

        for golden in dataset.goldens:
            texts.append(self._golden_text(golden))
            metadatas.append(
                {
                    "content_type": "golden",
                    "source_record_id": str(golden.id),
                    "dataset_id": str(dataset.id),
                    "org_id": str(principal.org_id),
                    "persona_name": golden.persona_name,
                    "source_file": golden.source_file,
                }
            )
            ids.append(str(golden.id))

        for conversation in dataset.conversations:
            texts.append(self._conversation_text(conversation))
            metadatas.append(
                {
                    "content_type": "conversation",
                    "source_record_id": str(conversation.id),
                    "dataset_id": str(dataset.id),
                    "org_id": str(principal.org_id),
                    "persona_name": conversation.persona_name,
                    "scenario_name": conversation.scenario_name,
                }
            )
            ids.append(str(conversation.id))

        if not texts:
            self._set_indexing_status(dataset.id, principal, "indexed")
            return

        try:
            store.add_texts(texts=texts, metadatas=metadatas, ids=ids)
        except Exception:
            self._cleanup_failed_index(dataset.id, store)
            self._set_indexing_status(dataset.id, principal, "failed")
            return

        self._set_indexing_status(dataset.id, principal, "indexed")

    def _cleanup_failed_index(self, dataset_id: UUID, store) -> None:
        try:
            store.client.delete(
                collection_name=store.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="metadata.dataset_id", match=MatchValue(value=str(dataset_id))
                        )
                    ]
                ),
            )
        except Exception:
            pass

    def _set_indexing_status(
        self, dataset_id: UUID, principal: AuthenticatedPrincipal, status: str
    ) -> None:
        principal.supabase_client.table(_DATASET_TABLE).update(
            {"indexing_status": status}
        ).eq("id", str(dataset_id)).execute()

    # -- row mapping ----------------------------------------------------------

    @staticmethod
    def _dataset_row(dataset: SyntheticDataset) -> dict:
        return {
            "id": str(dataset.id),
            "bot_id": dataset.bot_id,
            "org_id": str(dataset.org_id) if dataset.org_id is not None else None,
            "personas": dataset.personas,
            "source_documents": dataset.source_documents,
            "document_failures": [
                {
                    "path": failure.path,
                    "stage": failure.stage,
                    "error_type": failure.error_type,
                    "message": failure.message,
                }
                for failure in dataset.document_failures
            ],
            "indexing_status": dataset.indexing_status,
            "created_at": dataset.created_at.isoformat(),
        }

    @staticmethod
    def _golden_row(golden: GoldenRecord) -> dict:
        return {
            "id": str(golden.id),
            "dataset_id": str(golden.dataset_id),
            "org_id": str(golden.org_id) if golden.org_id is not None else None,
            "persona_name": golden.persona_name,
            "input": golden.input,
            "expected_output": golden.expected_output,
            "context": golden.context,
            "source_file": golden.source_file,
        }

    @staticmethod
    def _conversation_row(conversation: ConversationRecord) -> dict:
        return {
            "id": str(conversation.id),
            "dataset_id": str(conversation.dataset_id),
            "org_id": str(conversation.org_id) if conversation.org_id is not None else None,
            "persona_name": conversation.persona_name,
            "scenario_name": conversation.scenario_name,
            "turns": conversation.turns,
            "ending_status": conversation.ending_status,
            "bot_error": conversation.bot_error,
        }

    def _load_aggregate(self, dataset_row: dict, principal: AuthenticatedPrincipal) -> SyntheticDataset:
        client = principal.supabase_client
        dataset_id = UUID(dataset_row["id"])

        try:
            golden_response = (
                client.table(_GOLDEN_TABLE)
                .select("*")
                .eq("dataset_id", str(dataset_id))
                .eq("org_id", str(principal.org_id))
                .execute()
            )
            conversation_response = (
                client.table(_CONVERSATION_TABLE)
                .select("*")
                .eq("dataset_id", str(dataset_id))
                .eq("org_id", str(principal.org_id))
                .execute()
            )
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc

        return SyntheticDataset(
            id=dataset_id,
            bot_id=dataset_row["bot_id"],
            org_id=UUID(dataset_row["org_id"]) if dataset_row.get("org_id") else None,
            personas=list(dataset_row.get("personas") or []),
            source_documents=list(dataset_row.get("source_documents") or []),
            document_failures=[
                DocumentFailure(
                    path=failure["path"],
                    stage=failure["stage"],
                    error_type=failure["error_type"],
                    message=failure["message"],
                )
                for failure in dataset_row.get("document_failures") or []
            ],
            indexing_status=dataset_row["indexing_status"],
            created_at=self._parse_datetime(dataset_row["created_at"]),
            goldens=[self._row_to_golden(row) for row in golden_response.data],
            conversations=[
                self._row_to_conversation(row) for row in conversation_response.data
            ],
        )

    @staticmethod
    def _row_to_golden(row: dict) -> GoldenRecord:
        return GoldenRecord(
            id=UUID(row["id"]),
            dataset_id=UUID(row["dataset_id"]),
            org_id=UUID(row["org_id"]) if row.get("org_id") else None,
            persona_name=row["persona_name"],
            input=row["input"],
            expected_output=row.get("expected_output"),
            context=list(row.get("context") or []),
            source_file=row["source_file"],
        )

    @staticmethod
    def _row_to_conversation(row: dict) -> ConversationRecord:
        return ConversationRecord(
            id=UUID(row["id"]),
            dataset_id=UUID(row["dataset_id"]),
            org_id=UUID(row["org_id"]) if row.get("org_id") else None,
            persona_name=row["persona_name"],
            scenario_name=row["scenario_name"],
            turns=list(row.get("turns") or []),
            ending_status=row["ending_status"],
            bot_error=row.get("bot_error"),
        )

    @staticmethod
    def _golden_text(golden: GoldenRecord) -> str:
        parts = [golden.input]
        if golden.expected_output:
            parts.append(golden.expected_output)
        parts.extend(golden.context)
        return "\n".join(parts)

    @staticmethod
    def _conversation_text(conversation: ConversationRecord) -> str:
        return "\n".join(
            f"{turn.get('role', '')}: {turn.get('content', '')}" for turn in conversation.turns
        )

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        return datetime.fromisoformat(value)
