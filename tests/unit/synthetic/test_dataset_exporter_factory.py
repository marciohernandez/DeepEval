"""Unit tests for DatasetExporterFactory (M4.1, T029): dotted-class config,
no fixed registry, supported JSON/CSV, custom exporter via config only.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from deepeval_platform.repositories.models import SyntheticDataset
from deepeval_platform.synthetic.csv_dataset_exporter import CsvDatasetExporter
from deepeval_platform.synthetic.dataset_exporter_base import DatasetExporterBase
from deepeval_platform.synthetic.dataset_exporter_factory import (
    DatasetExporterConfigError,
    DatasetExporterFactory,
)
from deepeval_platform.synthetic.json_dataset_exporter import JsonDatasetExporter


class _CustomTestExporter(DatasetExporterBase):
    def export(self, dataset: SyntheticDataset, output_dir: str) -> Path:
        return Path(output_dir) / "custom.txt"


class _NotAnExporter:
    pass


def _config(values: dict) -> MagicMock:
    config = MagicMock()
    config.get.side_effect = lambda key: values[key]
    return config


class TestSupportedFormats:
    def test_json_format_loads_json_exporter(self):
        config = _config(
            {
                "synthetic.exporters.json": (
                    "deepeval_platform.synthetic.json_dataset_exporter.JsonDatasetExporter"
                )
            }
        )
        exporter = DatasetExporterFactory.create("json", config=config)
        assert isinstance(exporter, JsonDatasetExporter)

    def test_csv_format_loads_csv_exporter(self):
        config = _config(
            {
                "synthetic.exporters.csv": (
                    "deepeval_platform.synthetic.csv_dataset_exporter.CsvDatasetExporter"
                )
            }
        )
        exporter = DatasetExporterFactory.create("csv", config=config)
        assert isinstance(exporter, CsvDatasetExporter)


class TestCustomExporterViaConfigOnly:
    def test_custom_exporter_loads_solely_from_config(self):
        config = _config(
            {
                "synthetic.exporters.custom": (
                    "tests.unit.synthetic.test_dataset_exporter_factory._CustomTestExporter"
                )
            }
        )
        exporter = DatasetExporterFactory.create("custom", config=config)
        assert isinstance(exporter, _CustomTestExporter)


class TestInvalidTargets:
    def test_non_subclass_target_fails_clearly(self):
        config = _config(
            {
                "synthetic.exporters.bad": (
                    "tests.unit.synthetic.test_dataset_exporter_factory._NotAnExporter"
                )
            }
        )
        with pytest.raises(DatasetExporterConfigError):
            DatasetExporterFactory.create("bad", config=config)

    def test_missing_format_fails_clearly(self):
        config = MagicMock()
        config.get.side_effect = KeyError("synthetic.exporters.xml")
        with pytest.raises(DatasetExporterConfigError):
            DatasetExporterFactory.create("xml", config=config)

    def test_missing_module_fails_clearly(self):
        config = _config(
            {"synthetic.exporters.broken": "deepeval_platform.synthetic.does_not_exist.Nope"}
        )
        with pytest.raises(DatasetExporterConfigError):
            DatasetExporterFactory.create("broken", config=config)
