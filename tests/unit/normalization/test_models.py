"""Unit tests for NormalizedTrace, ToolCall, Message (M2.2, FR-001)."""
from __future__ import annotations

import dataclasses

from deepeval_platform.normalization.models import Message, NormalizedTrace, ToolCall


class TestNormalizedTraceFields:
    def test_exposes_exactly_seven_fields(self):
        field_names = {f.name for f in dataclasses.fields(NormalizedTrace)}
        assert field_names == {
            "input",
            "output",
            "context",
            "expected_output",
            "tools_called",
            "messages",
            "metadata",
        }

    def test_default_scalars_are_none(self):
        trace = NormalizedTrace()
        assert trace.input is None
        assert trace.output is None
        assert trace.expected_output is None

    def test_default_list_fields_are_empty_lists(self):
        trace = NormalizedTrace()
        assert trace.context == []
        assert trace.tools_called == []
        assert trace.messages == []

    def test_default_metadata_is_empty_dict(self):
        trace = NormalizedTrace()
        assert trace.metadata == {}

    def test_default_list_fields_are_independent_instances(self):
        a = NormalizedTrace()
        b = NormalizedTrace()
        a.context.append("x")
        assert b.context == []


class TestToolCall:
    def test_exposes_name_input_parameters_output(self):
        call = ToolCall(name="search", input_parameters={"q": "x"}, output="result")
        assert call.name == "search"
        assert call.input_parameters == {"q": "x"}
        assert call.output == "result"

    def test_defaults_are_none(self):
        call = ToolCall()
        assert call.name is None
        assert call.input_parameters is None
        assert call.output is None


class TestMessage:
    def test_exposes_role_and_content(self):
        message = Message(role="user", content="hi")
        assert message.role == "user"
        assert message.content == "hi"

    def test_defaults_are_none(self):
        message = Message()
        assert message.role is None
        assert message.content is None
