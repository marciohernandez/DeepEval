"""Unit tests for the evaluation-domain shared exceptions (M3.1).

Covers data-model.md's Exceptions table and research.md §6 (error sanitization).
"""
from __future__ import annotations

import pytest

from deepeval_platform.evaluation.errors import (
    ConfigResolutionError,
    DuplicateMetricNameError,
    DuplicateMetricRequestError,
    EmptyMetricListError,
    ErrorDetail,
    EvaluationOrchestratorError,
    InvalidThresholdError,
    InvalidTimeoutError,
    UnknownMetricError,
    sanitize_error,
)


class TestErrorDetail:
    def test_construction(self):
        detail = ErrorDetail(category="ValueError", message="something went wrong")
        assert detail.category == "ValueError"
        assert detail.message == "something went wrong"


class TestEmptyMetricListError:
    def test_is_orchestrator_error(self):
        assert issubclass(EmptyMetricListError, EvaluationOrchestratorError)

    def test_raises_and_carries_message(self):
        with pytest.raises(EmptyMetricListError):
            raise EmptyMetricListError()


class TestUnknownMetricError:
    def test_is_orchestrator_error(self):
        assert issubclass(UnknownMetricError, EvaluationOrchestratorError)

    def test_single_unknown_name_message(self):
        error = UnknownMetricError("nonexistent", supported=["faithfulness", "answer_relevancy"])
        message = str(error)
        assert "nonexistent" in message
        assert "faithfulness" in message
        assert "answer_relevancy" in message

    def test_multiple_unknown_names_message(self):
        error = UnknownMetricError(
            ["nonexistent", "also_missing"], supported=["faithfulness"]
        )
        message = str(error)
        assert "nonexistent" in message
        assert "also_missing" in message

    def test_carries_names_and_supported_attributes(self):
        error = UnknownMetricError("nonexistent", supported=["faithfulness", "answer_relevancy"])
        assert error.names == ["nonexistent"]
        assert error.supported == ["answer_relevancy", "faithfulness"]


class TestDuplicateMetricRequestError:
    def test_is_orchestrator_error(self):
        assert issubclass(DuplicateMetricRequestError, EvaluationOrchestratorError)

    def test_message_lists_all_duplicates(self):
        error = DuplicateMetricRequestError(["faithfulness", "faithfulness"])
        message = str(error)
        assert "faithfulness" in message
        assert error.duplicates == ["faithfulness", "faithfulness"]


class TestDuplicateMetricNameError:
    def test_is_orchestrator_error(self):
        assert issubclass(DuplicateMetricNameError, EvaluationOrchestratorError)

    def test_message_identifies_name_and_both_classes(self):
        class ExistingWrapper:
            pass

        class NewWrapper:
            pass

        error = DuplicateMetricNameError("faithfulness", ExistingWrapper, NewWrapper)
        message = str(error)
        assert "faithfulness" in message
        assert "ExistingWrapper" in message
        assert "NewWrapper" in message
        assert error.name == "faithfulness"
        assert error.existing_cls is ExistingWrapper
        assert error.new_cls is NewWrapper


class TestInvalidThresholdError:
    def test_is_orchestrator_error(self):
        assert issubclass(InvalidThresholdError, EvaluationOrchestratorError)

    def test_message_lists_every_offending_pair(self):
        error = InvalidThresholdError([("faithfulness", 1.5), ("answer_relevancy", "abc")])
        message = str(error)
        assert "faithfulness" in message
        assert "1.5" in message
        assert "answer_relevancy" in message
        assert "abc" in message
        assert error.offending == [("faithfulness", 1.5), ("answer_relevancy", "abc")]


class TestInvalidTimeoutError:
    def test_is_orchestrator_error(self):
        assert issubclass(InvalidTimeoutError, EvaluationOrchestratorError)

    def test_message_lists_every_offending_pair(self):
        error = InvalidTimeoutError([("default", -1), ("faithfulness", "abc")])
        message = str(error)
        assert "default" in message
        assert "-1" in message
        assert "faithfulness" in message
        assert error.offending == [("default", -1), ("faithfulness", "abc")]


class TestConfigResolutionError:
    def test_is_orchestrator_error(self):
        assert issubclass(ConfigResolutionError, EvaluationOrchestratorError)

    def test_wraps_original_exception(self):
        original = ValueError("malformed yaml")
        error = ConfigResolutionError("test_rag_bot", original)
        assert "test_rag_bot" in str(error)
        assert error.bot_id == "test_rag_bot"
        assert error.__cause__ is original or error.original is original


class TestSanitizeError:
    def test_category_is_exception_class_name(self):
        detail = sanitize_error(ValueError("boom"))
        assert detail.category == "ValueError"

    def test_redacts_bearer_token(self):
        detail = sanitize_error(Exception("failed with header Bearer sk-abcdefghij1234567890"))
        assert "sk-abcdefghij1234567890" not in detail.message
        assert "Bearer" not in detail.message or "REDACTED" in detail.message

    def test_redacts_api_key_shaped_token(self):
        detail = sanitize_error(Exception("invalid key sk-proj-abcdefghijklmnopqrstuvwxyz123456"))
        assert "sk-proj-abcdefghijklmnopqrstuvwxyz123456" not in detail.message

    def test_redacts_long_opaque_string(self):
        opaque = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
        detail = sanitize_error(Exception(f"token {opaque} rejected"))
        assert opaque not in detail.message

    def test_caps_message_length(self):
        long_message = "x " * 5000
        detail = sanitize_error(Exception(long_message))
        assert len(detail.message) < len(long_message)

    def test_returns_error_detail(self):
        detail = sanitize_error(ValueError("boom"))
        assert isinstance(detail, ErrorDetail)
