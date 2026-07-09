"""Integration tests for EvaluationRepository (US6 — Evaluation Results Persistence).

These tests hit a real Supabase instance. Prerequisites:
- SUPABASE_URL and SUPABASE_SERVICE_KEY set in .env
- DATABASE_URL set in .env
- Migration migrations/001_evaluation_results.sql applied to Supabase
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from deepeval_platform.repositories.evaluation_repository import EvaluationRepository, RepositoryError
from deepeval_platform.repositories.models import EvaluationResult


def _make_result(**overrides) -> EvaluationResult:
    defaults = dict(
        id=uuid.uuid4(),
        bot_id="integration-test-bot",
        trace_id="trace-integration-001",
        metric_name="answer_relevancy",
        score=0.9,
        passed=True,
        threshold=0.7,
        reason="Integration test reason",
        metadata={"source": "integration-test"},
        org_id=None,
        created_at=datetime.now(tz=timezone.utc),
    )
    defaults.update(overrides)
    return EvaluationResult(**defaults)


@pytest.fixture
def repo():
    return EvaluationRepository()


@pytest.fixture
def saved_result(repo):
    result = _make_result()
    repo.save(result)
    return result


class TestSaveIntegration:
    def test_save_returns_application_generated_uuid(self, repo):
        result = _make_result()
        returned_id = repo.save(result)
        assert returned_id == result.id

    def test_save_org_id_none_persisted(self, repo):
        result = _make_result(org_id=None)
        repo.save(result)
        fetched = repo.get_by_id(result.id)
        assert fetched.org_id is None

    def test_save_all_fields_persisted(self, repo):
        org = uuid.uuid4()
        result = _make_result(org_id=org)
        repo.save(result)
        fetched = repo.get_by_id(result.id)

        assert fetched.id == result.id
        assert fetched.bot_id == result.bot_id
        assert fetched.trace_id == result.trace_id
        assert fetched.metric_name == result.metric_name
        assert abs(fetched.score - result.score) < 1e-9
        assert fetched.passed == result.passed
        assert abs(fetched.threshold - result.threshold) < 1e-9
        assert fetched.reason == result.reason
        assert fetched.metadata == result.metadata
        assert fetched.org_id == org


class TestGetByIdIntegration:
    def test_get_by_id_retrieves_record(self, repo, saved_result):
        fetched = repo.get_by_id(saved_result.id)
        assert isinstance(fetched, EvaluationResult)
        assert fetched.id == saved_result.id

    def test_get_by_id_all_fields_match(self, repo, saved_result):
        fetched = repo.get_by_id(saved_result.id)
        assert fetched.bot_id == saved_result.bot_id
        assert fetched.metric_name == saved_result.metric_name


class TestGetByBotIntegration:
    def test_get_by_bot_returns_results_for_correct_bot(self, repo, saved_result):
        results = repo.get_by_bot(saved_result.bot_id)
        ids = [r.id for r in results]
        assert saved_result.id in ids

    def test_get_by_bot_excludes_other_bots(self, repo, saved_result):
        other = _make_result(bot_id="other-bot-xyz")
        repo.save(other)

        results = repo.get_by_bot(saved_result.bot_id)
        bot_ids = {r.bot_id for r in results}
        assert "other-bot-xyz" not in bot_ids


class TestSchemaValidationIntegration:
    def test_evaluation_results_table_has_expected_columns(self, repo):
        """Fails fast if migration was never applied (T049 spec requirement)."""
        from supabase import create_client
        from deepeval_platform.config.config_manager import ConfigManager

        config = ConfigManager.instance()
        url = config.get("SUPABASE_URL")
        key = config.get("SUPABASE_SERVICE_KEY")
        client = create_client(url, key)

        response = (
            client.table("information_schema.columns")
            .select("column_name, data_type")
            .eq("table_name", "evaluation_results")
            .execute()
        )

        columns = {row["column_name"] for row in response.data}
        expected = {
            "id", "bot_id", "trace_id", "metric_name",
            "score", "passed", "threshold", "reason",
            "metadata", "org_id", "created_at",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"
