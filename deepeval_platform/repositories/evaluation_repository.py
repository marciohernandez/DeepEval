"""EvaluationRepository — persists EvaluationResult to Supabase (US6)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from supabase import create_client

from deepeval_platform.config.config_manager import ConfigManager
from deepeval_platform.repositories.models import EvaluationResult

_TABLE = "evaluation_results"


class RepositoryError(Exception):
    """Raised on Supabase connectivity or write/read failure."""


class EvaluationRepository:
    """Persists and retrieves EvaluationResult records from Supabase."""

    def __init__(self) -> None:
        config = ConfigManager.instance()
        url = config.get("SUPABASE_URL")
        key = config.get("SUPABASE_SERVICE_KEY")
        self._client = create_client(url, key)

    def save(self, result: EvaluationResult) -> UUID:
        """Insert result and return its pre-generated UUID without a DB round-trip."""
        data = {
            "id": str(result.id),
            "bot_id": result.bot_id,
            "trace_id": result.trace_id,
            "metric_name": result.metric_name,
            "score": result.score,
            "passed": result.passed,
            "threshold": result.threshold,
            "reason": result.reason,
            "metadata": result.metadata,
            "org_id": str(result.org_id) if result.org_id is not None else None,
            "created_at": result.created_at.isoformat(),
        }
        try:
            self._client.table(_TABLE).insert(data).execute()
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc
        return result.id

    def get_by_id(self, result_id: UUID) -> EvaluationResult:
        """Return the EvaluationResult with the given id."""
        try:
            response = (
                self._client.table(_TABLE)
                .select("*")
                .eq("id", str(result_id))
                .execute()
            )
            if not response.data:
                raise RepositoryError(f"EvaluationResult {result_id} not found")
            return self._row_to_result(response.data[0])
        except RepositoryError:
            raise
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc

    def get_by_bot(
        self,
        bot_id: str,
        date: datetime | None = None,
    ) -> list[EvaluationResult]:
        """Return all results for bot_id, optionally filtered to a UTC calendar day.

        Naive datetimes are treated as UTC.
        Timezone-aware datetimes must be UTC — any other offset raises ValueError.
        """
        if date is not None and date.tzinfo is not None:
            if date.utcoffset() != timedelta(0):
                raise ValueError(
                    "date must be UTC (or naive, treated as UTC); "
                    f"received offset {date.utcoffset()}"
                )
        try:
            query = self._client.table(_TABLE).select("*").eq("bot_id", bot_id)
            if date is not None:
                utc_date = date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date
                start = utc_date.replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + timedelta(days=1)
                query = query.gte("created_at", start.isoformat()).lt(
                    "created_at", end.isoformat()
                )
            response = query.execute()
            return [self._row_to_result(row) for row in response.data]
        except (RepositoryError, ValueError):
            raise
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc

    def _row_to_result(self, row: dict) -> EvaluationResult:
        """Map a Supabase row dict to EvaluationResult with explicit type coercion."""
        return EvaluationResult(
            id=UUID(row["id"]),
            bot_id=row["bot_id"],
            trace_id=row.get("trace_id"),
            metric_name=row["metric_name"],
            score=float(row["score"]),
            passed=bool(row["passed"]),
            threshold=float(row["threshold"]),
            reason=row.get("reason"),
            metadata=row.get("metadata") or {},
            org_id=UUID(row["org_id"]) if row.get("org_id") else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )
