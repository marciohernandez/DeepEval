"""Unit tests for TraceCollector (US1 — Trace Collection)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pytest

from deepeval_platform.collection.trace_collector import TraceCollector
from deepeval_platform.collection.trace_filter import InteractionStatus, TraceFilter
from deepeval_platform.repositories.models import TraceRecord
from deepeval_platform.repositories.trace_repository import TraceRepositoryError


def _make_record(index: int, output=None) -> TraceRecord:
    return TraceRecord(
        trace_id=f"trace-{index}",
        session_id=None,
        bot_id="my-bot",
        input={},
        output=output if output is not None else {"ok": True},
        metadata={},
        start_time=datetime(2026, 1, 1) + timedelta(minutes=index),
        end_time=None,
    )


def _make_filter(**overrides) -> TraceFilter:
    defaults = dict(
        bot_id="my-bot",
        start_date=datetime(2026, 1, 1),
        end_date=datetime(2026, 1, 2),
    )
    defaults.update(overrides)
    return TraceFilter(**defaults)


def _stub_config_platform(mocker, platform: str):
    config = mocker.MagicMock()
    config.get.return_value = platform
    mocker.patch(
        "deepeval_platform.config.config_manager.ConfigManager.instance",
        return_value=config,
    )
    return config


def _stub_repository(mocker, records: list[TraceRecord] | Exception):
    repo = mocker.MagicMock()
    if isinstance(records, Exception):
        repo.get_by_date_range.side_effect = records
    else:
        repo.get_by_date_range.return_value = records
    return repo


# ---------------------------------------------------------------------------
# Extractor selection
# ---------------------------------------------------------------------------

class TestExtractorSelection:
    def test_selects_flowise_extractor_when_platform_flowise(self, mocker):
        _stub_config_platform(mocker, "flowise")
        repo = _stub_repository(mocker, [_make_record(1)])
        flowise_spy = mocker.patch(
            "deepeval_platform.collection.extractors.flowise_extractor.FlowiseExtractor.extract",
            return_value=[],
        )
        langchain_spy = mocker.patch(
            "deepeval_platform.collection.extractors.langchain_extractor.LangChainExtractor.extract",
            return_value=[],
        )

        TraceCollector(repo).collect(_make_filter())

        flowise_spy.assert_called_once()
        langchain_spy.assert_not_called()

    def test_selects_langchain_extractor_when_platform_langchain(self, mocker):
        _stub_config_platform(mocker, "langchain")
        repo = _stub_repository(mocker, [_make_record(1)])
        flowise_spy = mocker.patch(
            "deepeval_platform.collection.extractors.flowise_extractor.FlowiseExtractor.extract",
            return_value=[],
        )
        langchain_spy = mocker.patch(
            "deepeval_platform.collection.extractors.langchain_extractor.LangChainExtractor.extract",
            return_value=[],
        )

        TraceCollector(repo).collect(_make_filter())

        langchain_spy.assert_called_once()
        flowise_spy.assert_not_called()

    def test_reads_platform_from_config_using_bot_scoped_key(self, mocker):
        config = _stub_config_platform(mocker, "flowise")
        repo = _stub_repository(mocker, [])

        TraceCollector(repo).collect(_make_filter(bot_id="my-bot"))

        config.get.assert_called_once_with("bots.my-bot.platform")


# ---------------------------------------------------------------------------
# Logging behaviour
# ---------------------------------------------------------------------------

class TestLogging:
    def test_emits_debug_log_on_extractor_selection(self, mocker, caplog):
        _stub_config_platform(mocker, "flowise")
        repo = _stub_repository(mocker, [])

        with caplog.at_level(logging.DEBUG, logger="deepeval_platform.collection.trace_collector"):
            TraceCollector(repo).collect(_make_filter())

        assert any(
            "FlowiseExtractor" in r.message and "my-bot" in r.message
            for r in caplog.records
            if r.levelno == logging.DEBUG
        )

    def test_emits_warning_when_truncating(self, mocker, caplog):
        _stub_config_platform(mocker, "flowise")
        records = [_make_record(i) for i in range(600)]
        repo = _stub_repository(mocker, records)

        with caplog.at_level(logging.WARNING, logger="deepeval_platform.collection.trace_collector"):
            TraceCollector(repo).collect(_make_filter())

        assert any(
            "500" in r.message and "my-bot" in r.message
            for r in caplog.records
            if r.levelno == logging.WARNING
        )

    def test_no_warning_when_under_cap(self, mocker, caplog):
        _stub_config_platform(mocker, "flowise")
        records = [_make_record(i) for i in range(3)]
        repo = _stub_repository(mocker, records)

        with caplog.at_level(logging.WARNING, logger="deepeval_platform.collection.trace_collector"):
            TraceCollector(repo).collect(_make_filter())

        assert not any(r.levelno == logging.WARNING for r in caplog.records)


# ---------------------------------------------------------------------------
# Cap + ordering
# ---------------------------------------------------------------------------

class TestCapAndOrdering:
    def test_returns_most_recent_500_when_more_than_500_match(self, mocker):
        _stub_config_platform(mocker, "flowise")
        records = [_make_record(i) for i in range(600)]
        repo = _stub_repository(mocker, records)

        result = TraceCollector(repo).collect(_make_filter())

        assert len(result) == 500
        # Most recent first: highest index (largest start_time) is first.
        assert result[0].trace_id == "trace-599"
        assert result[-1].trace_id == "trace-100"

    def test_sorted_descending_by_start_time(self, mocker):
        _stub_config_platform(mocker, "flowise")
        records = [_make_record(2), _make_record(0), _make_record(1)]
        repo = _stub_repository(mocker, records)

        result = TraceCollector(repo).collect(_make_filter())

        assert [r.trace_id for r in result] == ["trace-2", "trace-1", "trace-0"]

    def test_none_start_time_sinks_to_end(self, mocker):
        _stub_config_platform(mocker, "flowise")
        undated = _make_record(0)
        undated.start_time = None
        undated.trace_id = "trace-undated"
        records = [undated, _make_record(1)]
        repo = _stub_repository(mocker, records)

        result = TraceCollector(repo).collect(_make_filter())

        assert result[-1].trace_id == "trace-undated"


# ---------------------------------------------------------------------------
# Empty result / error propagation
# ---------------------------------------------------------------------------

class TestEmptyAndErrors:
    def test_returns_empty_list_on_empty_result(self, mocker):
        _stub_config_platform(mocker, "flowise")
        repo = _stub_repository(mocker, [])

        result = TraceCollector(repo).collect(_make_filter())

        assert result == []

    def test_propagates_trace_repository_error_immediately_no_retry(self, mocker):
        _stub_config_platform(mocker, "flowise")
        repo = _stub_repository(mocker, TraceRepositoryError("connection failed"))

        with pytest.raises(TraceRepositoryError):
            TraceCollector(repo).collect(_make_filter())

        assert repo.get_by_date_range.call_count == 1

    def test_status_filter_is_passed_through_to_extractor(self, mocker):
        _stub_config_platform(mocker, "flowise")
        repo = _stub_repository(mocker, [])
        extract_spy = mocker.patch(
            "deepeval_platform.collection.extractors.flowise_extractor.FlowiseExtractor.extract",
            return_value=[],
        )

        TraceCollector(repo).collect(_make_filter(status=InteractionStatus.COMPLETED))

        args, _ = extract_spy.call_args
        assert args[1] == InteractionStatus.COMPLETED
