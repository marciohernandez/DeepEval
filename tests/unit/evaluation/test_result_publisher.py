"""Unit tests for ResultPublisher/ResultObserver (M4.2, data-model.md, Constitution Principle VI)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from deepeval_platform.evaluation.result_publisher import ResultObserver, ResultPublisher


class TestResultObserverIsAbstract:
    def test_cannot_be_instantiated_directly(self):
        with pytest.raises(TypeError):
            ResultObserver()

    def test_concrete_subclass_satisfies_isinstance(self):
        class ConcreteObserver(ResultObserver):
            def publish(self, run, results):
                pass

        observer = ConcreteObserver()
        assert isinstance(observer, ResultObserver)


class TestResultPublisherPublish:
    def test_invokes_only_the_supplied_observer(self):
        run = MagicMock()
        results = {"trace-1": MagicMock()}
        observer = MagicMock(spec=ResultObserver)
        other_observer = MagicMock(spec=ResultObserver)

        ResultPublisher().publish(run, results, observer)

        observer.publish.assert_called_once_with(run, results)
        other_observer.publish.assert_not_called()

    def test_propagates_observer_error_to_caller(self):
        run = MagicMock()
        results = {}
        observer = MagicMock(spec=ResultObserver)
        observer.publish.side_effect = RuntimeError("delivery destination unreachable")

        with pytest.raises(RuntimeError, match="delivery destination unreachable"):
            ResultPublisher().publish(run, results, observer)
