from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar
from urllib.parse import urlparse

from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from deepeval_platform.config.config_manager import ConfigManager

_COLLECTION_NAME_RE = re.compile(r"[a-zA-Z0-9_-]+")


@dataclass
class VectorCollection:
    name: str
    embedding_model: str
    embedding_dimensions: int
    created_at: datetime | None


class VectorStoreError(Exception):
    pass


class QdrantVectorStoreProvider:
    _instance: ClassVar[QdrantVectorStoreProvider | None] = None

    def __init__(self) -> None:
        config = ConfigManager.instance()

        # These raise ConfigError on missing key — must NOT be caught (FR-008)
        self._embedding_model: str = config.get("embedding.model")
        self._embedding_dimensions: int = int(config.get("embedding.dimensions"))
        host: str = config.get("QDRANT_HOST")
        port: int = int(config.get("qdrant.port"))
        api_key: str = config.get_optional("QDRANT_API_KEY")
        openai_key: str = config.get("OPENAI_API_KEY")

        try:
            if host.startswith(("http://", "https://")):
                parsed = urlparse(host)
                if parsed.port is None:
                    default_port = 443 if parsed.scheme == "https" else port
                    url = f"{host.rstrip('/')}:{default_port}"
                else:
                    url = host
                self._client = QdrantClient(url=url, api_key=api_key or None)
            else:
                self._client = QdrantClient(host=host, port=port, api_key=api_key or None)
        except Exception as exc:
            raise VectorStoreError("Cannot connect to Qdrant") from exc

        self._embeddings = OpenAIEmbeddings(
            model=self._embedding_model,
            api_key=openai_key,
        )
        self._provisioned: set[str] = set()

    @classmethod
    def instance(cls) -> QdrantVectorStoreProvider:
        if cls._instance is None:
            obj = cls.__new__(cls)
            obj.__init__()
            cls._instance = obj
        return cls._instance

    def get_store(self, collection_name: str) -> QdrantVectorStore:
        if not _COLLECTION_NAME_RE.fullmatch(collection_name):
            raise VectorStoreError(
                f"Invalid collection name '{collection_name}'. "
                "Must match ^[a-zA-Z0-9_-]+$"
            )

        try:
            exists = self._client.collection_exists(collection_name)
        except Exception as exc:
            raise VectorStoreError(
                f"Qdrant error checking collection: {type(exc).__name__}"
            ) from exc

        if exists and collection_name not in self._provisioned:
            self._check_dimension(collection_name)

        if not exists:
            try:
                self._client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=self._embedding_dimensions,
                        distance=Distance.COSINE,
                    ),
                )
            except Exception as exc:
                raise VectorStoreError(
                    f"Cannot create collection: {type(exc).__name__}"
                ) from exc

        self._provisioned.add(collection_name)

        return QdrantVectorStore(
            client=self._client,
            collection_name=collection_name,
            embedding=self._embeddings,
        )

    def collection_exists(self, collection_name: str) -> bool:
        try:
            return self._client.collection_exists(collection_name)
        except Exception as exc:
            raise VectorStoreError(f"Qdrant error: {type(exc).__name__}") from exc

    def delete_collection(self, collection_name: str) -> None:
        try:
            self._client.delete_collection(collection_name)
            self._provisioned.discard(collection_name)
        except Exception as exc:
            raise VectorStoreError(
                f"Cannot delete collection: {type(exc).__name__}"
            ) from exc

    def _check_dimension(self, collection_name: str) -> None:
        try:
            info = self._client.get_collection(collection_name)
            vectors = info.config.params.vectors
            if isinstance(vectors, dict):
                size = next(iter(vectors.values())).size
            else:
                size = vectors.size
        except Exception as exc:
            raise VectorStoreError(f"Qdrant error: {type(exc).__name__}") from exc

        if size != self._embedding_dimensions:
            raise VectorStoreError(
                f"Collection '{collection_name}' has vector dimension {size}, "
                f"but config requires {self._embedding_dimensions}"
            )
