"""Unit tests for MetricFactory (M3.1, data-model.md, FR-004/FR-008/FR-009/FR-010)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from deepeval_platform.evaluation.errors import DuplicateMetricNameError, UnknownMetricError
from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


@pytest.fixture(autouse=True)
def isolated_registry():
    """Snapshot/restore MetricFactory._registry so this file's dummy registrations never leak."""
    original = MetricFactory._registry.copy()
    yield
    MetricFactory._registry.clear()
    MetricFactory._registry.update(original)


class _DummyMetricA(MetricBase):
    _native_metric_cls = MagicMock()


class _DummyMetricB(MetricBase):
    _native_metric_cls = MagicMock()


class TestMetricFactoryRegister:
    def test_register_decorator_adds_to_registry(self):
        MetricFactory.register("dummy_register_test")(_DummyMetricA)
        assert MetricFactory._registry["dummy_register_test"] is _DummyMetricA

    def test_register_duplicate_name_raises(self):
        MetricFactory.register("dummy_dup_test")(_DummyMetricA)
        with pytest.raises(DuplicateMetricNameError) as exc_info:
            MetricFactory.register("dummy_dup_test")(_DummyMetricB)
        error = exc_info.value
        assert error.name == "dummy_dup_test"
        assert error.existing_cls is _DummyMetricA
        assert error.new_cls is _DummyMetricB


class TestMetricFactoryCreate:
    def test_create_returns_new_instance_every_call(self):
        MetricFactory.register("dummy_create_test")(_DummyMetricA)
        deepeval_model = MagicMock()
        first = MetricFactory.create(
            "dummy_create_test", threshold=0.8, deepeval_model=deepeval_model
        )
        second = MetricFactory.create(
            "dummy_create_test", threshold=0.8, deepeval_model=deepeval_model
        )
        assert isinstance(first, _DummyMetricA)
        assert isinstance(second, _DummyMetricA)
        assert first is not second

    def test_create_unknown_name_raises(self):
        with pytest.raises(UnknownMetricError) as exc_info:
            MetricFactory.create("nonexistent", threshold=0.8, deepeval_model=MagicMock())
        error = exc_info.value
        assert error.names == ["nonexistent"]

    def test_create_unknown_name_lists_all_supported_names(self):
        MetricFactory.register("dummy_supported_test")(_DummyMetricA)
        with pytest.raises(UnknownMetricError) as exc_info:
            MetricFactory.create("nonexistent", threshold=0.8, deepeval_model=MagicMock())
        assert "dummy_supported_test" in exc_info.value.supported

    def test_create_never_returns_none(self):
        MetricFactory.register("dummy_none_test")(_DummyMetricA)
        result = MetricFactory.create("dummy_none_test", threshold=0.8, deepeval_model=MagicMock())
        assert result is not None

    def test_create_never_touches_config_manager(self, mocker):
        MetricFactory.register("dummy_config_test")(_DummyMetricA)
        instance_spy = mocker.patch(
            "deepeval_platform.config.config_manager.ConfigManager.instance"
        )
        MetricFactory.create("dummy_config_test", threshold=0.8, deepeval_model=MagicMock())
        instance_spy.assert_not_called()
