"""Integration tests for QdrantVectorStoreProvider (US3).

Requires a real Qdrant instance with credentials in .env:
    QDRANT_HOST, QDRANT_API_KEY
And config/settings.yaml keys:
    qdrant.port, embedding.model, embedding.dimensions, openai.default_model

After tests pass, manually verify collections were created/deleted in the Qdrant dashboard.
"""
from __future__ import annotations

import pytest
from langchain_core.documents import Document

from deepeval.vector_store.qdrant_provider import QdrantVectorStoreProvider

_TEST_COLLECTION = "integration-test-qdrant-us3"


@pytest.fixture(autouse=True)
def reset_singleton():
    """Isolate each test with a fresh singleton."""
    QdrantVectorStoreProvider._instance = None
    yield
    QdrantVectorStoreProvider._instance = None


@pytest.fixture
def provider():
    """Real QdrantVectorStoreProvider using credentials from ConfigManager."""
    return QdrantVectorStoreProvider.instance()


@pytest.fixture(autouse=True)
def cleanup_collection(provider):
    """Delete the test collection before and after each test."""
    if provider.collection_exists(_TEST_COLLECTION):
        provider.delete_collection(_TEST_COLLECTION)
    yield
    if provider.collection_exists(_TEST_COLLECTION):
        provider.delete_collection(_TEST_COLLECTION)


def test_real_qdrant_connection_established(provider):
    """Provider initialises without error using real credentials."""
    assert provider is not None


def test_collection_auto_created_when_absent(provider):
    """get_store() auto-creates the collection when it does not exist."""
    assert not provider.collection_exists(_TEST_COLLECTION)
    store = provider.get_store(_TEST_COLLECTION)
    assert store is not None
    assert provider.collection_exists(_TEST_COLLECTION)


def test_add_documents_and_similarity_search(provider):
    """Documents added via add_documents() are retrievable via similarity_search()."""
    store = provider.get_store(_TEST_COLLECTION)
    docs = [Document(page_content="The quick brown fox jumps over the lazy dog")]
    store.add_documents(docs)

    results = store.similarity_search("fox", k=1)
    assert len(results) > 0
    assert "fox" in results[0].page_content.lower()


def test_as_retriever_returns_vector_store_retriever(provider):
    """as_retriever() returns an object usable as a LangChain VectorStoreRetriever."""
    from langchain_core.vectorstores import VectorStoreRetriever

    store = provider.get_store(_TEST_COLLECTION)
    retriever = store.as_retriever()
    assert isinstance(retriever, VectorStoreRetriever)


def test_singleton_stable_across_multiple_calls():
    """instance() returns the same object on every call."""
    p1 = QdrantVectorStoreProvider.instance()
    p2 = QdrantVectorStoreProvider.instance()
    assert p1 is p2


def test_delete_collection_removes_collection(provider):
    """delete_collection() removes the collection so collection_exists() returns False."""
    provider.get_store(_TEST_COLLECTION)
    assert provider.collection_exists(_TEST_COLLECTION)

    provider.delete_collection(_TEST_COLLECTION)
    assert not provider.collection_exists(_TEST_COLLECTION)
