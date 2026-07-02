"""TraceRepository — reads bot interaction traces from Langfuse (US5).

SDK Research Gate (T043a) findings:
  get_by_bot      → langfuse._client.api.trace.list(tags=[bot_id])
  get_by_session  → langfuse._client.api.trace.list(session_id=session_id)
  get_by_date_range → langfuse._client.api.trace.list(
                          tags=[bot_id],
                          from_timestamp=start,
                          to_timestamp=end,
                      )
  All three params exist natively in langfuse.api.trace.client.TraceClient.list().
  No fallback strategy required. No blocking gaps found.
  end_time is not available in the Langfuse list API response (TraceWithDetails
  does not expose it); all TraceRecord.end_time values will be None.
"""
from __future__ import annotations

from typing import Any

from deepeval.observability.langfuse_client import LangfuseClient
from deepeval.repositories.models import TraceRecord


class TraceRepositoryError(Exception):
    """Raised on Langfuse connectivity or SDK failure during trace reads."""


class TraceRepository:
    """Reads bot interaction traces from Langfuse as structured TraceRecord instances.

    Delegates the underlying SDK connection to LangfuseClient.instance() (singleton).
    Never exposes raw Langfuse API response objects to callers (FR-014).
    All query methods return [] on empty result without raising (FR-013).
    """

    def __init__(self) -> None:
        self._langfuse = LangfuseClient.instance()

    def get_by_bot(self, bot_id: str) -> list[TraceRecord]:
        """Return all traces tagged with bot_id.

        Raises TraceRepositoryError on Langfuse SDK failure (FR-013).
        """
        try:
            result = self._langfuse._client.api.trace.list(tags=[bot_id])
            return [self._to_trace_record(raw, bot_id=bot_id) for raw in result.data]
        except TraceRepositoryError:
            raise
        except Exception as exc:
            raise TraceRepositoryError(str(exc)) from exc

    def get_by_session(self, session_id: str) -> list[TraceRecord]:
        """Return all traces for session_id.

        Raises TraceRepositoryError on Langfuse SDK failure.
        """
        try:
            result = self._langfuse._client.api.trace.list(session_id=session_id)
            return [self._to_trace_record(raw) for raw in result.data]
        except TraceRepositoryError:
            raise
        except Exception as exc:
            raise TraceRepositoryError(str(exc)) from exc

    def get_by_date_range(
        self,
        bot_id: str,
        start: Any,
        end: Any,
    ) -> list[TraceRecord]:
        """Return traces tagged with bot_id within [start, end] (UTC).

        Raises TraceRepositoryError on Langfuse SDK failure.
        """
        try:
            result = self._langfuse._client.api.trace.list(
                tags=[bot_id],
                from_timestamp=start,
                to_timestamp=end,
            )
            return [self._to_trace_record(raw, bot_id=bot_id) for raw in result.data]
        except TraceRepositoryError:
            raise
        except Exception as exc:
            raise TraceRepositoryError(str(exc)) from exc

    def _to_trace_record(self, raw: Any, bot_id: str = "") -> TraceRecord:
        """Map a raw Langfuse SDK trace object to a TraceRecord value object.

        bot_id is passed explicitly by get_by_bot and get_by_date_range (which
        know the bot_id from the query). For get_by_session, bot_id is extracted
        from the first tag on the trace (the bot_name tag convention per data model).
        """
        effective_bot_id = bot_id or (raw.tags[0] if raw.tags else "")
        return TraceRecord(
            trace_id=raw.id,
            session_id=raw.session_id,
            bot_id=effective_bot_id,
            input=raw.input if raw.input is not None else {},
            output=raw.output,
            metadata=raw.metadata if raw.metadata is not None else {},
            start_time=raw.timestamp,
            end_time=None,
        )
