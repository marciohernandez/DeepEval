"""
Public interface contract for QdrantVectorStoreProvider.

This file is a CONTRACT SPECIFICATION, not implementation.

LangChain-first: QdrantVectorStoreProvider returns langchain_qdrant.QdrantVectorStore
instances, which are natively compatible with LangChain/LangGraph retrievers (FR-009).
"""
from __future__ import annotations

# These imports name the LangChain types the provider must return.
# In production code: from langchain_qdrant import QdrantVectorStore
# from langchain_core.vectorstores import VectorStore


class QdrantVectorStoreProviderContract:
    """
    Provider/Factory. Returns ready-to-use QdrantVectorStore instances.

    - Singleton: one underlying QdrantClient connection per process (FR-008).
    - Collections are created automatically if absent; reused if exists (FR-008).
    - Embedding model and dimensions sourced from ConfigManager (settings.yaml) (FR-008).
    - Returns langchain_qdrant.QdrantVectorStore for LangChain/LangGraph compatibility (FR-009).
    - Underlying QdrantClient connection is shared across all collections (FR-009).

    ConfigManager keys consumed:
        embedding.model          (str) — e.g. "text-embedding-3-small"
        embedding.dimensions     (int) — e.g. 1536
        QDRANT_HOST              (str) — e.g. "http://localhost"
        QDRANT_PORT              (int) — e.g. 6333
        QDRANT_API_KEY           (str) — Qdrant API key (sensitive)

    Usage:
        from deepeval.vector_store import QdrantVectorStoreProvider
        provider = QdrantVectorStoreProvider.instance()
        store = provider.get_store("evaluation-goldens")
        store.add_documents(docs)
        results = store.similarity_search("query", k=5)
        retriever = store.as_retriever()    # LangChain VectorStoreRetriever
    """

    @classmethod
    def instance(cls) -> "QdrantVectorStoreProviderContract":
        """Return the singleton instance."""
        ...

    def get_store(self, collection_name: str) -> "QdrantVectorStore":  # type: ignore[name-defined]
        """
        Return a ready-to-use QdrantVectorStore for `collection_name`.

        If the collection does not exist, it is created automatically with the
        global embedding model configured in settings.yaml.
        If it exists, it is reused with the shared connection.

        Args:
            collection_name: Must match ^[a-zA-Z0-9_-]+$

        Returns:
            langchain_qdrant.QdrantVectorStore — natively compatible with LangChain.

        Raises:
            VectorStoreError: if collection_name is invalid (FR-008).
            VectorStoreError: if Qdrant is unreachable (FR-008).
        """
        ...

    def collection_exists(self, collection_name: str) -> bool:
        """True if the named collection exists in Qdrant."""
        ...

    def delete_collection(self, collection_name: str) -> None:
        """Delete a collection. Used in test teardown only."""
        ...


class VectorStoreError(Exception):
    """Raised on Qdrant connection or collection operation failure."""
