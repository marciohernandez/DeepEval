"""Domain models for repository layer (US5, US6, M4.1)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


@dataclass
class DocumentFailure:
    """Structured unreadable/parser-invalid document failure (M4.1 data-model.md).

    stage distinguishes a file the loader could not open ("readability") from
    one it opened but could not parse ("parsing").
    """

    path: str
    stage: Literal["readability", "parsing"]
    error_type: str
    message: str


@dataclass
class TraceRecord:
    """Structured bot interaction trace read from Langfuse (FR-014).

    bot_id maps to the bot_name tag stored on the Langfuse trace.
    output is None for interrupted sessions (Edge Case per spec).
    end_time is None when not available from the Langfuse list API.
    """

    trace_id: str
    session_id: str | None
    bot_id: str
    input: dict | str
    output: dict | str | None
    metadata: dict
    start_time: datetime
    end_time: datetime | None


@dataclass
class EvaluationResult:
    """Persisted evaluation record in Supabase (FR-015, FR-016, FR-017).

    id is application-generated (uuid.uuid4()) before insert; caller knows
    the UUID without a DB round-trip.
    org_id is always included in the insert, even when None (FR-016).
    """

    id: UUID
    bot_id: str
    trace_id: str | None
    metric_name: str
    score: float
    passed: bool
    threshold: float
    reason: str | None
    metadata: dict
    org_id: UUID | None
    created_at: datetime
