from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Literal, TypeVar

_T = TypeVar("_T")

import yaml
from dotenv import dotenv_values

_SENSITIVE_TERMS = frozenset({"key", "secret", "password", "token", "api"})


@dataclass
class ConfigEntry:
    key: str
    value: str
    source: Literal["env", "yaml"]
    source_file: str
    is_sensitive: bool

    def __repr__(self) -> str:
        display = "***" if self.is_sensitive else self.value
        return (
            f"ConfigEntry(key={self.key!r}, value={display!r}, "
            f"source={self.source!r}, source_file={self.source_file!r})"
        )


class ConfigError(Exception):
    def __init__(self, key: str, source_file: str) -> None:
        self.key = key
        self.source_file = source_file
        super().__init__(
            f"Configuration key '{key}' is missing or empty. "
            f"Expected in: {source_file}"
        )


class ConfigManager:
    _instance: ClassVar[ConfigManager | None] = None
    _loaded: ClassVar[bool] = False

    def __init__(self) -> None:
        self._store: dict[str, ConfigEntry] = {}

    @classmethod
    def instance(cls) -> ConfigManager:
        if cls._instance is None:
            obj = cls.__new__(cls)
            obj.__init__()
            obj._load()
            cls._instance = obj
            cls._loaded = True
        return cls._instance

    def _load(self) -> None:
        # YAML first (lower priority — overwritten by .env on collision)
        config_dir = Path("config")
        if config_dir.exists():
            for yaml_path in sorted(config_dir.glob("*.yaml")):
                with open(yaml_path) as fh:
                    data = yaml.safe_load(fh) or {}
                self._flatten_yaml(data, prefix="", source_file=str(yaml_path))

        # .env second (higher priority — overwrites YAML on collision)
        env_path = Path(".env")
        if env_path.exists():
            for key, value in dotenv_values(env_path).items():
                self._store[key] = ConfigEntry(
                    key=key,
                    value=value if value is not None else "",
                    source="env",
                    source_file=str(env_path),
                    is_sensitive=self._is_sensitive(key),
                )

    def _flatten_yaml(self, data: dict[str, Any], prefix: str, source_file: str) -> None:
        for k, v in data.items():
            flat_key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                self._flatten_yaml(v, flat_key, source_file)
            elif isinstance(v, list):
                self._flatten_yaml(
                    {str(i): item for i, item in enumerate(v)}, flat_key, source_file
                )
            else:
                self._store[flat_key] = ConfigEntry(
                    key=flat_key,
                    value=str(v) if v is not None else "",
                    source="yaml",
                    source_file=source_file,
                    is_sensitive=self._is_sensitive(flat_key),
                )

    @staticmethod
    def _is_sensitive(key: str) -> bool:
        key_lower = key.lower()
        return any(term in key_lower for term in _SENSITIVE_TERMS)

    def get(self, key: str) -> str:
        entry = self._store.get(key)
        if entry is None or entry.value == "":
            raise ConfigError(key, ".env or config/*.yaml")
        return entry.value

    def get_optional(self, key: str, default: str = "") -> str:
        try:
            return self.get(key)
        except ConfigError:
            return default

    def get_typed(self, key: str, expected_type: type[_T]) -> _T:
        value = self.get(key)
        try:
            return expected_type(value)
        except (ValueError, TypeError) as exc:
            raise ConfigError(key, ".env or config/*.yaml") from exc

    def __repr__(self) -> str:
        parts = ", ".join(f"{k}={v!r}" for k, v in self._store.items())
        return f"ConfigManager({parts})"
