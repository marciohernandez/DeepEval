"""Unit tests for TraceExtractorBase ABC (US1 — Trace Collection)."""
from __future__ import annotations

import pytest

from deepeval_platform.collection.extractor_base import TraceExtractorBase


class TestTraceExtractorBaseIsAbstract:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            TraceExtractorBase()

    def test_subclass_without_extract_cannot_be_instantiated(self):
        class Incomplete(TraceExtractorBase):
            pass

        with pytest.raises(TypeError):
            Incomplete()

    def test_subclass_implementing_extract_can_be_instantiated(self):
        class Complete(TraceExtractorBase):
            def extract(self, records, status):
                return records

        instance = Complete()
        assert instance.extract([], None) == []
