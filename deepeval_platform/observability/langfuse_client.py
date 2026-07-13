"""LangfuseClient singleton and related types (US2 — Reliable Observability Telemetry)."""
from __future__ import annotations

import atexit
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar

from langfuse import Langfuse
from langfuse.api.ingestion.types import IngestionEvent_TraceCreate, TraceBody

from deepeval_platform.config.config_manager import ConfigManager

logger = logging.getLogger(__name__)


@dataclass
class TelemetryEvent:
    session_id: str
    name: str
    input: dict | str | None
    output: dict | str | None
    metadata: dict
    start_time: datetime | None
    trace_id: str | None = None
    end_time: datetime | None = None


class LangfuseError(Exception):
    """Reserved public exception for future milestones.

    Not raised internally in M1 — both __init__() and submit() log WARNING
    and continue per FR-007. Exported as public API for callers in future
    milestones that may need to catch connection failures explicitly.
    """


class LangfuseClient:
    """Singleton wrapping the Langfuse Python SDK.

    Credentials are sourced exclusively from ConfigManager:
        LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY

    atexit flush is registered once at singleton creation (FR-006).
    SDK errors are logged as WARNING and never re-raised (FR-007).
    """

    _instance: ClassVar[LangfuseClient | None] = None

    def __init__(self) -> None:
        raise TypeError("Use LangfuseClient.instance() to obtain the singleton.")

    @classmethod
    def instance(cls) -> "LangfuseClient":
        if cls._instance is None:
            obj: LangfuseClient = object.__new__(cls)
            obj._client: Langfuse | None = None
            config = ConfigManager.instance()
            try:
                obj._client = Langfuse(
                    host=config.get("LANGFUSE_HOST"),
                    public_key=config.get("LANGFUSE_PUBLIC_KEY"),
                    secret_key=config.get("LANGFUSE_SECRET_KEY"),
                )
            except Exception as exc:
                logger.warning("LangfuseClient: SDK initialization failed: %s", exc)
            atexit.register(obj.flush)
            cls._instance = obj
        return cls._instance

    def submit(self, event: TelemetryEvent) -> None:
        """Queue event for async export via langfuse.trace().

        Logs WARNING and returns without raising when not connected (FR-007b)
        or when the SDK raises during submission (FR-007).
        """
        if not self.is_connected():
            logger.warning(
                "LangfuseClient: not connected, dropping event '%s'", event.name
            )
            return
        try:
            now = datetime.now(timezone.utc)
            body = TraceBody(
                id=event.trace_id or str(uuid.uuid4()),
                name=event.name,
                session_id=event.session_id,
                input=event.input,
                output=event.output,
                metadata=event.metadata,
                timestamp=event.start_time or now,
            )
            self._client.api.ingestion.batch(  # type: ignore[union-attr]
                batch=[
                    IngestionEvent_TraceCreate(
                        type="trace-create",
                        id=str(uuid.uuid4()),
                        timestamp=now.isoformat(),
                        body=body,
                    )
                ]
            )
        except Exception as exc:
            logger.warning(
                "LangfuseClient: failed to submit event '%s': %s", event.name, exc
            )

    def flush(self) -> None:
        """Flush buffered telemetry events. Called automatically on process exit."""
        if self._client is not None:
            self._client.flush()

    def is_connected(self) -> bool:
        """True when the underlying SDK client is initialised."""
        return self._client is not None
