"""
Public interface contract for LangfuseClient.

This file is a CONTRACT SPECIFICATION, not implementation.
"""
from __future__ import annotations

from deepeval_contracts_config_manager import TelemetryEvent  # type: ignore[import]


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
        Queue `event` for async export to the observability platform.

        If the platform is temporarily unreachable, logs a warning and continues —
        retry is delegated to the Langfuse SDK's built-in mechanism (FR-007).
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
    """Raised when the Langfuse connection cannot be established."""
