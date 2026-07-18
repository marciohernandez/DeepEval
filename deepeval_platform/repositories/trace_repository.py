"""TraceRepository — reads bot interaction traces from Langfuse (US5).

Uses direct HTTP calls to the Langfuse REST API (/api/public/traces) instead
of the SDK's typed client to avoid Pydantic version-skew errors between the
langfuse-python SDK and self-hosted Langfuse server versions.
"""
from __future__ import annotations

import base64
import urllib.parse
import urllib.request
import json
from datetime import datetime

from deepeval_platform.config.config_manager import ConfigManager
from deepeval_platform.repositories.models import TraceRecord


class TraceRepositoryError(Exception):
    """Raised on Langfuse connectivity or SDK failure during trace reads."""


class TraceRepository:
    """Reads bot interaction traces from Langfuse as structured TraceRecord instances.

    Uses the Langfuse REST API directly (GET /api/public/traces) with Basic auth.
    Never exposes raw Langfuse API response objects to callers (FR-014).
    All query methods return [] on empty result without raising (FR-013).
    """

    def __init__(self) -> None:
        config = ConfigManager.instance()
        host = config.get("LANGFUSE_HOST").rstrip("/")
        public_key = config.get("LANGFUSE_PUBLIC_KEY")
        secret_key = config.get("LANGFUSE_SECRET_KEY")
        token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        self._base_url = f"{host}/api/public/traces"
        self._auth_header = f"Basic {token}"

    _EXHAUSTIVE_PAGE_SIZE = 100

    def _fetch_json(self, params: dict) -> dict:
        """GET /api/public/traces with query params; returns the full parsed JSON body."""
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{self._base_url}?{qs}" if qs else self._base_url
        req = urllib.request.Request(url, headers={"Authorization": self._auth_header})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception as exc:
            raise TraceRepositoryError(str(exc)) from exc

    def _fetch(self, params: dict) -> list[dict]:
        """GET /api/public/traces with query params; returns raw trace dicts."""
        return self._fetch_json(params)["data"]

    def get_by_bot(self, bot_id: str) -> list[TraceRecord]:
        """Return all traces tagged with bot_id."""
        rows = self._fetch({"tags": bot_id})
        return [self._to_trace_record(r, bot_id=bot_id) for r in rows]

    def get_by_session(self, session_id: str) -> list[TraceRecord]:
        """Return all traces for session_id."""
        rows = self._fetch({"sessionId": session_id})
        return [self._to_trace_record(r) for r in rows]

    def get_by_date_range(
        self,
        bot_id: str,
        start: datetime,
        end: datetime,
    ) -> list[TraceRecord]:
        """Return traces tagged with bot_id within [start, end] (UTC)."""
        rows = self._fetch({
            "tags": bot_id,
            "fromTimestamp": start.isoformat(),
            "toTimestamp": end.isoformat(),
        })
        return [self._to_trace_record(r, bot_id=bot_id) for r in rows]

    def get_all_by_date_range(
        self,
        bot_id: str,
        start: datetime,
        end: datetime,
    ) -> list[TraceRecord]:
        """Exhaustively paginate GET /api/public/traces for [start, end] (UTC), ascending order.

        Uses one fixed page size and follows meta.totalPages until every page is
        consumed. Raises TraceRepositoryError for missing/malformed pagination
        metadata, a non-advancing/repeated page number, a totalPages value that
        changes between responses, a premature empty page before the declared
        final page, or a trace record missing either ordering component
        (id/timestamp) — never loops or returns a partial result.
        """
        rows: list[dict] = []
        seen_ids: set[str] = set()
        total_pages: int | None = None
        page = 1
        while True:
            payload = self._fetch_json({
                "tags": bot_id,
                "fromTimestamp": start.isoformat(),
                "toTimestamp": end.isoformat(),
                "page": page,
                "limit": self._EXHAUSTIVE_PAGE_SIZE,
                "orderBy": "timestamp.asc",
            })
            data = payload.get("data")
            meta = payload.get("meta")
            if not isinstance(data, list) or not isinstance(meta, dict):
                raise TraceRepositoryError(
                    f"Malformed pagination response on page {page}: expected 'data' list and "
                    "'meta' object."
                )
            try:
                meta_page = meta["page"]
                meta_total_pages = meta["totalPages"]
            except KeyError as exc:
                raise TraceRepositoryError(
                    f"Missing pagination metadata on page {page}: {exc}"
                ) from exc
            if meta_page != page:
                raise TraceRepositoryError(
                    f"Unexpected page number {meta_page!r} in response, requested page {page}."
                )
            if total_pages is None:
                total_pages = meta_total_pages
            elif meta_total_pages != total_pages:
                raise TraceRepositoryError(
                    f"totalPages changed between responses: {total_pages!r} -> "
                    f"{meta_total_pages!r}."
                )
            if not data and page < total_pages:
                raise TraceRepositoryError(
                    f"Premature empty page {page} before declared final page {total_pages}."
                )
            for row in data:
                row_id = row.get("id")
                timestamp = row.get("timestamp")
                if not row_id or not timestamp:
                    raise TraceRepositoryError(
                        "Trace record missing required ordering component (id/timestamp)."
                    )
                if row_id in seen_ids:
                    raise TraceRepositoryError(f"Duplicate trace id {row_id!r} across pages.")
                seen_ids.add(row_id)
                rows.append(row)
            if page >= total_pages:
                break
            page += 1

        return [self._to_trace_record(r, bot_id=bot_id) for r in rows]

    def _to_trace_record(self, raw: dict, bot_id: str = "") -> TraceRecord:
        tags = raw.get("tags") or []
        effective_bot_id = bot_id or (tags[0] if tags else "")
        timestamp = raw.get("timestamp")
        return TraceRecord(
            trace_id=raw["id"],
            session_id=raw.get("sessionId"),
            bot_id=effective_bot_id,
            input=raw.get("input") or {},
            output=raw.get("output"),
            metadata=raw.get("metadata") or {},
            start_time=datetime.fromisoformat(timestamp) if timestamp else None,
            end_time=None,
        )
