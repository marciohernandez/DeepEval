"""Unit tests for FieldMapper (M2.2, US1 — FR-002 through FR-005, FR-009)."""
from __future__ import annotations

from datetime import datetime

import pytest

from deepeval_platform.normalization.errors import FieldMappingTypeError
from deepeval_platform.normalization.field_mapper import FieldMapper
from deepeval_platform.normalization.models import Message, ToolCall
from deepeval_platform.repositories.models import TraceRecord


def _make_record(
    input_=None, output=None, metadata=None, bot_id="test_bot"
) -> TraceRecord:
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


def _stub_config(mocker, mapping: dict[str, str]):
    config = mocker.MagicMock()
    config.get_optional.side_effect = lambda key, default="": mapping.get(key, default)
    mocker.patch(
        "deepeval_platform.config.config_manager.ConfigManager.instance",
        return_value=config,
    )
    return config


class TestScalarPathResolution:
    def test_resolves_declared_scalar_path_rooted_at_input(self, mocker):
        _stub_config(mocker, {"bots.b1.field_mapping.input": "input.data.question"})
        record = _make_record(input_={"data": {"question": "What is DeepEval?"}})

        result = FieldMapper().resolve_field("b1", record, "input")

        assert result == "What is DeepEval?"

    def test_resolves_declared_scalar_path_rooted_at_output(self, mocker):
        _stub_config(mocker, {"bots.b1.field_mapping.output": "output.data.answer"})
        record = _make_record(output={"data": {"answer": "An eval framework."}})

        result = FieldMapper().resolve_field("b1", record, "output")

        assert result == "An eval framework."

    def test_resolves_declared_scalar_path_rooted_at_metadata(self, mocker):
        _stub_config(
            mocker,
            {"bots.b1.field_mapping.expected_output": "metadata.expected_answer"},
        )
        record = _make_record(metadata={"expected_answer": "Expected."})

        result = FieldMapper().resolve_field("b1", record, "expected_output")

        assert result == "Expected."


class TestListIndexPathResolution:
    def test_resolves_positive_numeric_list_index(self, mocker):
        _stub_config(
            mocker, {"bots.b1.field_mapping.input": "input.data.messages.0.content"}
        )
        record = _make_record(
            input_={"data": {"messages": [{"content": "first"}, {"content": "second"}]}}
        )

        result = FieldMapper().resolve_field("b1", record, "input")

        assert result == "first"

    def test_resolves_negative_numeric_list_index_for_last_item(self, mocker):
        _stub_config(
            mocker, {"bots.b1.field_mapping.output": "output.data.messages.-1.content"}
        )
        record = _make_record(
            output={"data": {"messages": [{"content": "first"}, {"content": "last"}]}}
        )

        result = FieldMapper().resolve_field("b1", record, "output")

        assert result == "last"


class TestAbsentPathHandling:
    def test_declared_path_absent_from_record_returns_defined_empty_scalar(self, mocker):
        _stub_config(mocker, {"bots.b1.field_mapping.input": "input.data.question"})
        record = _make_record(input_={"data": {}})

        result = FieldMapper().resolve_field("b1", record, "input")

        assert result is None

    def test_declared_path_absent_from_record_returns_defined_empty_list(self, mocker):
        _stub_config(mocker, {"bots.b1.field_mapping.context": "output.data.contexts"})
        record = _make_record(output={"data": {}})

        result = FieldMapper().resolve_field("b1", record, "context")

        assert result == []

    def test_undeclared_path_returns_defined_empty_value_no_error(self, mocker):
        _stub_config(mocker, {})
        record = _make_record()

        result = FieldMapper().resolve_field("b1", record, "input")

        assert result is None

    def test_scalar_root_cannot_continue_traversal_returns_defined_empty(self, mocker):
        _stub_config(mocker, {"bots.b1.field_mapping.input": "input.data.question"})
        record = _make_record(input_="a plain string, not a dict")

        result = FieldMapper().resolve_field("b1", record, "input")

        assert result is None

    def test_scalar_intermediate_segment_cannot_continue_returns_defined_empty(self, mocker):
        _stub_config(
            mocker, {"bots.b1.field_mapping.input": "input.data.question.nested"}
        )
        record = _make_record(input_={"data": {"question": "a scalar string"}})

        result = FieldMapper().resolve_field("b1", record, "input")

        assert result is None


class TestListTypeMismatch:
    def test_list_field_resolving_to_non_list_raises_field_mapping_type_error(self, mocker):
        _stub_config(mocker, {"bots.b1.field_mapping.context": "output.data.contexts"})
        record = _make_record(output={"data": {"contexts": "not a list"}})

        with pytest.raises(FieldMappingTypeError) as exc_info:
            FieldMapper().resolve_field("b1", record, "context")

        message = str(exc_info.value)
        assert "b1" in message
        assert "context" in message
        assert "output.data.contexts" in message


class TestItemReshaping:
    def test_tools_called_items_reshaped_via_explicit_item_mapping(self, mocker):
        _stub_config(
            mocker,
            {
                "bots.b1.field_mapping.tools_called": "output.data.tool_calls",
                "bots.b1.field_mapping.tools_called_item.name": "tool_name",
                "bots.b1.field_mapping.tools_called_item.input_parameters": "arguments",
                "bots.b1.field_mapping.tools_called_item.output": "result",
            },
        )
        record = _make_record(
            output={
                "data": {
                    "tool_calls": [
                        {"tool_name": "search", "arguments": {"q": "x"}, "result": "ok"}
                    ]
                }
            }
        )

        result = FieldMapper().resolve_field("b1", record, "tools_called")

        assert result == [ToolCall(name="search", input_parameters={"q": "x"}, output="ok")]

    def test_messages_items_reshaped_via_explicit_item_mapping(self, mocker):
        _stub_config(
            mocker,
            {
                "bots.b1.field_mapping.messages": "output.data.history",
                "bots.b1.field_mapping.messages_item.role": "role",
                "bots.b1.field_mapping.messages_item.content": "text",
            },
        )
        record = _make_record(
            output={"data": {"history": [{"role": "user", "text": "hi"}]}}
        )

        result = FieldMapper().resolve_field("b1", record, "messages")

        assert result == [Message(role="user", content="hi")]

    def test_tools_called_items_reshaped_via_same_name_default_when_item_block_omitted(
        self, mocker
    ):
        _stub_config(mocker, {"bots.b1.field_mapping.tools_called": "output.data.tool_calls"})
        record = _make_record(
            output={
                "data": {
                    "tool_calls": [
                        {"name": "search", "input_parameters": {"q": "x"}, "output": "ok"}
                    ]
                }
            }
        )

        result = FieldMapper().resolve_field("b1", record, "tools_called")

        assert result == [ToolCall(name="search", input_parameters={"q": "x"}, output="ok")]

    def test_messages_items_reshaped_via_same_name_default_when_item_block_omitted(
        self, mocker
    ):
        _stub_config(mocker, {"bots.b1.field_mapping.messages": "output.data.history"})
        record = _make_record(
            output={"data": {"history": [{"role": "user", "content": "hi"}]}}
        )

        result = FieldMapper().resolve_field("b1", record, "messages")

        assert result == [Message(role="user", content="hi")]


class TestMetadataPassthrough:
    def test_metadata_always_equals_record_metadata_verbatim(self, mocker):
        _stub_config(mocker, {"bots.b1.field_mapping.expected_output": "metadata.x"})
        record = _make_record(metadata={"x": "y", "z": 1})

        result = FieldMapper().resolve_field("b1", record, "metadata")

        assert result == {"x": "y", "z": 1}
        assert result is record.metadata
