"""Unit tests for TraceNormalizer (M2.2, US1 — FR-002 through FR-005)."""
from __future__ import annotations

from datetime import datetime

import pytest

from deepeval_platform.normalization.errors import UnmappedBotError
from deepeval_platform.normalization.models import NormalizedTrace
from deepeval_platform.normalization.trace_normalizer import TraceNormalizer
from deepeval_platform.repositories.models import TraceRecord


def _make_record(bot_id="test_rag_bot", input_=None, output=None, metadata=None) -> TraceRecord:
    return TraceRecord(
        trace_id="t1",
        session_id=None,
        bot_id=bot_id,
        input=input_ if input_ is not None else {},
        output=output if output is not None else {},
        metadata=metadata if metadata is not None else {},
        start_time=datetime(2026, 1, 1),
        end_time=None,
    )


def _stub_config(mocker, *, bot_types: dict[str, str], mapping: dict[str, str]):
    config = mocker.MagicMock()

    def _get(key: str):
        from deepeval_platform.config.config_manager import ConfigError

        for bot_id, bot_type in bot_types.items():
            if key == f"bots.{bot_id}.bot_type":
                return bot_type
        raise ConfigError(key, ".env or config/*.yaml")

    config.get.side_effect = _get
    config.get_optional.side_effect = lambda key, default="": mapping.get(key, default)
    mocker.patch(
        "deepeval_platform.config.config_manager.ConfigManager.instance",
        return_value=config,
    )
    return config


class TestFullMapping:
    def test_known_bot_full_mapping_produces_correct_normalized_trace(self, mocker):
        _stub_config(
            mocker,
            bot_types={"test_rag_bot": "rag"},
            mapping={
                "bots.test_rag_bot.field_mapping.input": "input.data.question",
                "bots.test_rag_bot.field_mapping.output": "output.data.answer",
                "bots.test_rag_bot.field_mapping.context": "output.data.contexts",
                "bots.test_rag_bot.field_mapping.expected_output": "metadata.expected",
            },
        )
        record = _make_record(
            input_={"data": {"question": "Q"}},
            output={"data": {"answer": "A", "contexts": ["c1", "c2"]}},
            metadata={"expected": "E"},
        )

        trace = TraceNormalizer().normalize(record)

        assert trace == NormalizedTrace(
            input="Q",
            output="A",
            context=["c1", "c2"],
            expected_output="E",
            tools_called=[],
            messages=[],
            metadata={"expected": "E"},
        )


class TestPartialMapping:
    def test_known_bot_partial_mapping_leaves_undeclared_fields_empty_no_error(self, mocker):
        _stub_config(
            mocker,
            bot_types={"test_rag_bot": "rag"},
            mapping={"bots.test_rag_bot.field_mapping.input": "input.data.question"},
        )
        record = _make_record(input_={"data": {"question": "Q"}})

        trace = TraceNormalizer().normalize(record)

        assert trace.input == "Q"
        assert trace.output is None
        assert trace.context == []
        assert trace.expected_output is None
        assert trace.tools_called == []
        assert trace.messages == []


class TestUnknownBot:
    def test_unknown_bot_id_raises_unmapped_bot_error_naming_the_bot(self, mocker):
        _stub_config(mocker, bot_types={}, mapping={})
        record = _make_record(bot_id="no_such_bot")

        with pytest.raises(UnmappedBotError) as exc_info:
            TraceNormalizer().normalize(record)

        assert "no_such_bot" in str(exc_info.value)


class TestZeroDeclaredFields:
    def test_known_bot_zero_declared_fields_raises_unmapped_bot_error(self, mocker):
        _stub_config(
            mocker,
            bot_types={"test_rag_bot": "rag"},
            mapping={},
        )
        record = _make_record(bot_id="test_rag_bot")

        with pytest.raises(UnmappedBotError) as exc_info:
            TraceNormalizer().normalize(record)

        assert "test_rag_bot" in str(exc_info.value)
