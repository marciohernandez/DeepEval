"""
Public interface contract for LangfuseClient.

This file is a CONTRACT SPECIFICATION, not implementation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deepeval.observability.langfuse_client import TelemetryEvent


class LangfuseClientContract:
    """
    Singleton. Manages a single active connection to the Langfuse observability platform.

    Connection credentials are sourced exclusively from ConfigManager:
        LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY

    On creation, registers flush() via atexit for guaranteed shutdown flush (FR-006).
    Delegates all retry/back-off to the Langfuse SDK (FR-007).

    Usage:
        from deepeval.observability import LangfuseClient
        client = LangfuseClient.instance()
        client.submit(event)
        client.flush()          # called automatically on process exit
    """

    @classmethod
    def instance(cls) -> "LangfuseClientContract":
        """Return the singleton instance, establishing connection on first call."""
        ...

    def submit(self, event: TelemetryEvent) -> None:
        """
        Queue `event` for async export to the observability platform via langfuse.trace().

        SDK mapping (FR-007a):
            langfuse.trace(
                id=event.trace_id,          # None → new trace; set → updates existing
                name=event.name,
                session_id=event.session_id,
                input=event.input,
                output=event.output,
                metadata=event.metadata,
                start_time=event.start_time,
                end_time=event.end_time,
            )

        No span(), generation(), or event() primitives are used in M1.

        If the platform is temporarily unreachable, logs a warning and continues —
        retry is delegated to the Langfuse SDK's built-in mechanism (FR-007).

        If is_connected() is False (SDK failed to initialise), logs a WARNING and
        returns immediately without invoking the SDK — no exception is raised (FR-007b).
        """
        ...

    def flush(self) -> None:
        """
        Flush all buffered telemetry events to the platform.

        Blocks until flush completes or times out. Called automatically on process
        exit via atexit (FR-006).
        """
        ...

    def is_connected(self) -> bool:
        """True if the underlying SDK client has been initialised."""
        ...


class LangfuseError(Exception):
    """Reserved public exception for future milestones.

    Not raised internally in M1 — both __init__() and submit() log WARNING
    and continue per FR-007. Exported as public API for callers in future
    milestones that may need to catch connection failures explicitly.
    """
