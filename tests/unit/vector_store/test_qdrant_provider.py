"""Unit tests for QdrantVectorStoreProvider (US3 — Vector Store Access for Orchestration)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from deepeval_platform.config.config_manager import ConfigError
from deepeval_platform.vector_store.qdrant_provider import (
    QdrantVectorStoreProvider,
    VectorCollection,
    VectorStoreError,
)


@pytest.fixture(autouse=True)
def reset_qdrant_singleton():
    """Reset QdrantVectorStoreProvider singleton after every test."""
    yield
    QdrantVectorStoreProvider._instance = None


@pytest.fixture
def mock_qdrant_client():
    client = MagicMock()
    client.collection_exists.return_value = False
    return client


@pytest.fixture
def mock_embeddings():
    return MagicMock()


@pytest.fixture
def mock_store():
    return MagicMock()


@pytest.fixture
def provider_patches(mock_config, mock_qdrant_client, mock_embeddings, mock_store):
    """Patch all external SDKs; tests run with patches active."""
    with patch(
        "deepeval_platform.vector_store.qdrant_provider.QdrantClient",
        return_value=mock_qdrant_client,
    ):
        with patch(
            "deepeval_platform.vector_store.qdrant_provider.OpenAIEmbeddings",
            return_value=mock_embeddings,
        ):
            with patch(
                "deepeval_platform.vector_store.qdrant_provider.QdrantVectorStore",
                return_value=mock_store,
            ):
                yield mock_qdrant_client, mock_embeddings, mock_store


# ---------------------------------------------------------------------------
# VectorCollection dataclass
# ---------------------------------------------------------------------------

class TestVectorCollection:
    def test_creation_with_all_fields(self):
        from datetime import datetime
        vc = VectorCollection(
            name="my-collection",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            created_at=datetime(2026, 1, 1),
        )
        assert vc.name == "my-collection"
        assert vc.embedding_model == "text-embedding-3-small"
        assert vc.embedding_dimensions == 1536

    def test_created_at_optional(self):
        vc = VectorCollection(
            name="col",
            embedding_model="model",
            embedding_dimensions=512,
            created_at=None,
        )
        assert vc.created_at is None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_instance_returns_same_object(self, provider_patches):
        p1 = QdrantVectorStoreProvider.instance()
        p2 = QdrantVectorStoreProvider.instance()
        assert p1 is p2

    def test_qdrant_client_initialized_only_once(self, mock_config, mock_embeddings):
        with patch(
            "deepeval_platform.vector_store.qdrant_provider.QdrantClient",
        ) as mock_client_cls:
            inner_client = MagicMock()
            inner_client.collection_exists.return_value = False
            mock_client_cls.return_value = inner_client
            with patch(
                "deepeval_platform.vector_store.qdrant_provider.OpenAIEmbeddings",
                return_value=mock_embeddings,
            ):
                QdrantVectorStoreProvider.instance()
                QdrantVectorStoreProvider.instance()
                mock_client_cls.assert_called_once()


# ---------------------------------------------------------------------------
# get_store()
# ---------------------------------------------------------------------------

class TestGetStore:
    def test_valid_name_succeeds(self, provider_patches):
        _, _, store = provider_patches
        provider = QdrantVectorStoreProvider.instance()
        result = provider.get_store("valid-collection")
        assert result is store

    def test_invalid_name_raises_vector_store_error(self, provider_patches):
        provider = QdrantVectorStoreProvider.instance()
        with pytest.raises(VectorStoreError):
            provider.get_store("has spaces")

    def test_name_with_dot_raises_vector_store_error(self, provider_patches):
        provider = QdrantVectorStoreProvider.instance()
        with pytest.raises(VectorStoreError):
            provider.get_store("has.dot")

    def test_valid_names_accepted(self, provider_patches):
        client, _, store = provider_patches
        client.collection_exists.return_value = False
        provider = QdrantVectorStoreProvider.instance()
        for name in ("valid-name", "valid_name", "UPPERCASE", "name123", "a"):
            provider._provisioned.clear()
            result = provider.get_store(name)
            assert result is store

    def test_dimension_mismatch_raises_vector_store_error(self, provider_patches):
        client, _, _ = provider_patches
        client.collection_exists.return_value = True

        mock_info = MagicMock()
        mock_info.config.params.vectors.size = 512  # config expects 1536
        client.get_collection.return_value = mock_info

        provider = QdrantVectorStoreProvider.instance()
        with pytest.raises(VectorStoreError):
            provider.get_store("test-collection")

    def test_dimension_check_skipped_for_provisioned_collection(self, provider_patches):
        """Second call skips dimension check (caching boundary)."""
        client, _, store = provider_patches
        client.collection_exists.return_value = True

        mock_info = MagicMock()
        mock_info.config.params.vectors.size = 1536  # matches config
        client.get_collection.return_value = mock_info

        provider = QdrantVectorStoreProvider.instance()
        provider.get_store("cached-collection")  # first call: validates
        client.get_collection.reset_mock()

        client.collection_exists.return_value = True
        provider.get_store("cached-collection")  # second call: skips check
        client.get_collection.assert_not_called()

    def test_shared_qdrant_client_reused(self, provider_patches):
        provider = QdrantVectorStoreProvider.instance()
        assert provider._client is provider._client


# ---------------------------------------------------------------------------
# collection_exists()
# ---------------------------------------------------------------------------

class TestCollectionExists:
    def test_returns_false_when_absent(self, provider_patches):
        client, _, _ = provider_patches
        client.collection_exists.return_value = False
        provider = QdrantVectorStoreProvider.instance()
        assert provider.collection_exists("some-collection") is False

    def test_returns_true_when_present(self, provider_patches):
        client, _, _ = provider_patches
        client.collection_exists.return_value = True
        provider = QdrantVectorStoreProvider.instance()
        assert provider.collection_exists("some-collection") is True


# ---------------------------------------------------------------------------
# URL-based host handling (https:// / http:// prefix)
# ---------------------------------------------------------------------------

class TestURLHostHandling:
    def _make_config(self, mocker, host: str):
        config = MagicMock()
        values = {
            "QDRANT_HOST": host,
            "QDRANT_API_KEY": "key",
            "OPENAI_API_KEY": "openai-key",
            "embedding.model": "text-embedding-3-small",
            "embedding.dimensions": "1536",
            "qdrant.port": "6333",
        }
        config.get.side_effect = lambda k: values[k]
        config.get_optional.side_effect = lambda k, default="": values.get(k, default)
        mocker.patch("deepeval_platform.config.config_manager.ConfigManager.instance", return_value=config)
        return config

    def test_https_host_without_port_appends_443(self, mocker):
        self._make_config(mocker, "https://qdrant.example.com")
        mock_client_cls = MagicMock(return_value=MagicMock())
        with patch("deepeval_platform.vector_store.qdrant_provider.QdrantClient", mock_client_cls):
            with patch("deepeval_platform.vector_store.qdrant_provider.OpenAIEmbeddings"):
                QdrantVectorStoreProvider.instance()
        mock_client_cls.assert_called_once_with(url="https://qdrant.example.com:443", api_key="key")

    def test_https_host_with_port_uses_url_as_is(self, mocker):
        self._make_config(mocker, "https://qdrant.example.com:8080")
        mock_client_cls = MagicMock(return_value=MagicMock())
        with patch("deepeval_platform.vector_store.qdrant_provider.QdrantClient", mock_client_cls):
            with patch("deepeval_platform.vector_store.qdrant_provider.OpenAIEmbeddings"):
                QdrantVectorStoreProvider.instance()
        mock_client_cls.assert_called_once_with(url="https://qdrant.example.com:8080", api_key="key")

    def test_http_host_without_port_appends_configured_port(self, mocker):
        self._make_config(mocker, "http://qdrant.example.com")
        mock_client_cls = MagicMock(return_value=MagicMock())
        with patch("deepeval_platform.vector_store.qdrant_provider.QdrantClient", mock_client_cls):
            with patch("deepeval_platform.vector_store.qdrant_provider.OpenAIEmbeddings"):
                QdrantVectorStoreProvider.instance()
        mock_client_cls.assert_called_once_with(url="http://qdrant.example.com:6333", api_key="key")


# ---------------------------------------------------------------------------
# Qdrant connection failures
# ---------------------------------------------------------------------------

class TestConnectionFailure:
    def test_qdrant_unreachable_raises_vector_store_error(self, mock_config):
        with patch(
            "deepeval_platform.vector_store.qdrant_provider.QdrantClient",
            side_effect=Exception("connection refused"),
        ):
            with patch("deepeval_platform.vector_store.qdrant_provider.OpenAIEmbeddings"):
                with pytest.raises(VectorStoreError):
                    QdrantVectorStoreProvider.instance()

    def test_qdrant_unreachable_no_credential_exposure(self, mock_config):
        with patch(
            "deepeval_platform.vector_store.qdrant_provider.QdrantClient",
            side_effect=Exception("connection refused"),
        ):
            with patch("deepeval_platform.vector_store.qdrant_provider.OpenAIEmbeddings"):
                with pytest.raises(VectorStoreError) as exc_info:
                    QdrantVectorStoreProvider.instance()
        assert "test-qdrant-api-key" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# ConfigError propagation (FR-008)
# ---------------------------------------------------------------------------

class TestConfigErrors:
    def test_missing_embedding_model_propagates_config_error(self, mock_config):
        mock_config.get.side_effect = ConfigError("embedding.model", "config/settings.yaml")
        with pytest.raises(ConfigError):
            QdrantVectorStoreProvider.instance()

    def test_missing_embedding_dimensions_propagates_config_error(self, mock_config):
        def _get(key):
            if key == "embedding.dimensions":
                raise ConfigError("embedding.dimensions", "config/settings.yaml")
            # embedding.model succeeds; after it fails nothing else matters
            return "text-embedding-3-small"

        mock_config.get.side_effect = _get
        with pytest.raises(ConfigError):
            QdrantVectorStoreProvider.instance()


# ---------------------------------------------------------------------------
# VectorStoreError
# ---------------------------------------------------------------------------

class TestVectorStoreError:
    def test_is_exception_subclass(self):
        assert issubclass(VectorStoreError, Exception)

    def test_can_be_instantiated_with_message(self):
        err = VectorStoreError("something went wrong")
        assert str(err) == "something went wrong"
