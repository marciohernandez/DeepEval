"""DatasetExporterFactory — imports and validates synthetic.exporters.<format>;
no fixed registry. A new export target requires only a subclass and config
entry (M4.1, R9).
"""
from __future__ import annotations

import importlib
import inspect

from deepeval_platform.config.config_manager import ConfigManager
from deepeval_platform.synthetic.dataset_exporter_base import DatasetExporterBase


class DatasetExporterConfigError(Exception):
    pass


class DatasetExporterFactory:
    @classmethod
    def create(cls, format: str, config: ConfigManager | None = None) -> DatasetExporterBase:
        config = config if config is not None else ConfigManager.instance()

        try:
            dotted_path = config.get(f"synthetic.exporters.{format}")
        except Exception as exc:
            raise DatasetExporterConfigError(
                f"No exporter configured for format {format!r}"
            ) from exc

        module_path, _, class_name = dotted_path.rpartition(".")
        try:
            module = importlib.import_module(module_path)
            exporter_cls = getattr(module, class_name)
        except Exception as exc:
            raise DatasetExporterConfigError(
                f"Cannot import exporter class {dotted_path!r} for format {format!r}"
            ) from exc

        if not (inspect.isclass(exporter_cls) and issubclass(exporter_cls, DatasetExporterBase)):
            raise DatasetExporterConfigError(
                f"{dotted_path!r} is not a DatasetExporterBase subclass"
            )
        if inspect.isabstract(exporter_cls):
            raise DatasetExporterConfigError(
                f"{dotted_path!r} is abstract and cannot be instantiated"
            )

        return exporter_cls()
