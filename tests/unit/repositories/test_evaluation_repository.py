"""Unit tests for EvaluationRepository (US6 — Evaluation Results Persistence)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from deepeval_platform.repositories.models import EvaluationResult
from deepeval_platform.repositories.evaluation_repository import EvaluationRepository, RepositoryError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(**overrides) -> EvaluationResult:
    defaults = dict(
        id=uuid.uuid4(),
        bot_id="test-bot",
        trace_id="trace-001",
        metric_name="answer_relevancy",
        score=0.85,
        passed=True,
        threshold=0.7,
        reason="Looks good",
        metadata={"env": "test"},
        org_id=None,
        created_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return EvaluationResult(**defaults)


def _make_row(result: EvaluationResult) -> dict:
    """Simulate Supabase row format (strings for numeric/UUID fields per T053)."""
    return {
        "id": str(result.id),
        "bot_id": result.bot_id,
        "trace_id": result.trace_id,
        "metric_name": result.metric_name,
        "score": result.score,
        "passed": result.passed,
        "threshold": result.threshold,
        "reason": result.reason,
        "metadata": result.metadata,
        "org_id": str(result.org_id) if result.org_id else None,
        "created_at": result.created_at.isoformat(),
    }


def _make_supabase_client(response_data: list | None = None) -> MagicMock:
    """Return a chainable mock Supabase client."""
    sb = MagicMock()
    mock_response = MagicMock()
    mock_response.data = response_data or []
    sb.table.return_value = sb
    sb.select.return_value = sb
    sb.eq.return_value = sb
    sb.gte.return_value = sb
    sb.lt.return_value = sb
    sb.insert.return_value = sb
    sb.execute.return_value = mock_response
    return sb


@pytest.fixture(autouse=True)
def patch_supabase_config(mock_config):
    """Ensure ConfigManager is always mocked — no real credentials needed."""


# ---------------------------------------------------------------------------
# save()
# ---------------------------------------------------------------------------

class TestSave:
    def test_save_returns_result_id(self):
        result = _make_result()
        sb = _make_supabase_client()

        with patch("deepeval_platform.repositories.evaluation_repository.create_client", return_value=sb):
            repo = EvaluationRepository()
            returned_id = repo.save(result)

        assert returned_id == result.id

    def test_save_org_id_none_included_in_insert(self):
        """org_id=None must always be present in the insert dict (FR-016)."""
        result = _make_result(org_id=None)
        sb = _make_supabase_client()

        with patch("deepeval_platform.repositories.evaluation_repository.create_client", return_value=sb):
            repo = EvaluationRepository()
            repo.save(result)

        inserted_data = sb.insert.call_args[0][0]
        assert "org_id" in inserted_data
        assert inserted_data["org_id"] is None

    def test_save_raises_repository_error_on_sdk_failure(self):
        """Write failure raises RepositoryError — no silent data loss (FR-017)."""
        result = _make_result()
        sb = _make_supabase_client()
        sb.execute.side_effect = Exception("DB connection failed")

        with patch("deepeval_platform.repositories.evaluation_repository.create_client", return_value=sb):
            repo = EvaluationRepository()
            with pytest.raises(RepositoryError):
                repo.save(result)

    def test_save_raises_repository_error_missing_table_preserves_message(self):
        """'relation does not exist' error preserved in RepositoryError message."""
        result = _make_result()
        sb = _make_supabase_client()
        original_msg = 'relation "evaluation_results" does not exist'
        sb.execute.side_effect = Exception(original_msg)

        with patch("deepeval_platform.repositories.evaluation_repository.create_client", return_value=sb):
            repo = EvaluationRepository()
            with pytest.raises(RepositoryError) as exc_info:
                repo.save(result)

        assert original_msg in str(exc_info.value)


# ---------------------------------------------------------------------------
# get_by_id()
# ---------------------------------------------------------------------------

class TestGetById:
    def test_get_by_id_returns_evaluation_result(self):
        result = _make_result()
        sb = _make_supabase_client(response_data=[_make_row(result)])

        with patch("deepeval_platform.repositories.evaluation_repository.create_client", return_value=sb):
            repo = EvaluationRepository()
            fetched = repo.get_by_id(result.id)

        assert isinstance(fetched, EvaluationResult)

    def test_get_by_id_all_fields_populated(self):
        org = uuid.uuid4()
        result = _make_result(org_id=org)
        sb = _make_supabase_client(response_data=[_make_row(result)])

        with patch("deepeval_platform.repositories.evaluation_repository.create_client", return_value=sb):
            repo = EvaluationRepository()
            fetched = repo.get_by_id(result.id)

        assert fetched.id == result.id
        assert fetched.bot_id == result.bot_id
        assert fetched.trace_id == result.trace_id
        assert fetched.metric_name == result.metric_name
        assert fetched.score == result.score
        assert fetched.passed == result.passed
        assert fetched.threshold == result.threshold
        assert fetched.reason == result.reason
        assert fetched.metadata == result.metadata
        assert fetched.org_id == org

    def test_get_by_id_org_id_none_returned(self):
        result = _make_result(org_id=None)
        sb = _make_supabase_client(response_data=[_make_row(result)])

        with patch("deepeval_platform.repositories.evaluation_repository.create_client", return_value=sb):
            repo = EvaluationRepository()
            fetched = repo.get_by_id(result.id)

        assert fetched.org_id is None

    def test_get_by_id_raises_repository_error_on_sdk_failure(self):
        sb = _make_supabase_client()
        sb.execute.side_effect = Exception("timeout")

        with patch("deepeval_platform.repositories.evaluation_repository.create_client", return_value=sb):
            repo = EvaluationRepository()
            with pytest.raises(RepositoryError):
                repo.get_by_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# get_by_bot()
# ---------------------------------------------------------------------------

class TestGetByBot:
    def test_get_by_bot_returns_list_of_evaluation_results(self):
        result = _make_result()
        sb = _make_supabase_client(response_data=[_make_row(result)])

        with patch("deepeval_platform.repositories.evaluation_repository.create_client", return_value=sb):
            repo = EvaluationRepository()
            results = repo.get_by_bot("test-bot")

        assert len(results) == 1
        assert isinstance(results[0], EvaluationResult)

    def test_get_by_bot_filters_by_bot_id(self):
        result = _make_result(bot_id="my-bot")
        sb = _make_supabase_client(response_data=[_make_row(result)])

        with patch("deepeval_platform.repositories.evaluation_repository.create_client", return_value=sb):
            repo = EvaluationRepository()
            results = repo.get_by_bot("my-bot")

        assert results[0].bot_id == "my-bot"

    def test_get_by_bot_empty_result_returns_empty_list(self):
        sb = _make_supabase_client(response_data=[])

        with patch("deepeval_platform.repositories.evaluation_repository.create_client", return_value=sb):
            repo = EvaluationRepository()
            results = repo.get_by_bot("nonexistent-bot")

        assert results == []

    def test_get_by_bot_with_date_filters_by_utc_day(self):
        result = _make_result()
        sb = _make_supabase_client(response_data=[_make_row(result)])
        utc_date = datetime(2026, 1, 1, tzinfo=timezone.utc)

        with patch("deepeval_platform.repositories.evaluation_repository.create_client", return_value=sb):
            repo = EvaluationRepository()
            repo.get_by_bot("test-bot", date=utc_date)

        assert sb.gte.called
        assert sb.lt.called

    def test_get_by_bot_non_utc_timezone_raises_value_error(self):
        """FR-015: timezone-aware datetimes that are not UTC must be rejected."""
        non_utc = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=-5)))
        sb = _make_supabase_client()

        with patch("deepeval_platform.repositories.evaluation_repository.create_client", return_value=sb):
            repo = EvaluationRepository()
            with pytest.raises(ValueError):
                repo.get_by_bot("test-bot", date=non_utc)

    def test_get_by_bot_naive_datetime_treated_as_utc(self):
        """Naive datetimes must not raise — treated as UTC."""
        result = _make_result()
        sb = _make_supabase_client(response_data=[_make_row(result)])
        naive_date = datetime(2026, 1, 1)

        with patch("deepeval_platform.repositories.evaluation_repository.create_client", return_value=sb):
            repo = EvaluationRepository()
            results = repo.get_by_bot("test-bot", date=naive_date)

        assert isinstance(results, list)

    def test_get_by_bot_raises_repository_error_on_sdk_failure(self):
        sb = _make_supabase_client()
        sb.execute.side_effect = Exception("query failed")

        with patch("deepeval_platform.repositories.evaluation_repository.create_client", return_value=sb):
            repo = EvaluationRepository()
            with pytest.raises(RepositoryError):
                repo.get_by_bot("test-bot")


# ---------------------------------------------------------------------------
# RepositoryError
# ---------------------------------------------------------------------------

class TestRepositoryError:
    def test_is_exception_subclass(self):
        assert issubclass(RepositoryError, Exception)

    def test_can_be_instantiated_with_message(self):
        err = RepositoryError("write failed")
        assert str(err) == "write failed"
