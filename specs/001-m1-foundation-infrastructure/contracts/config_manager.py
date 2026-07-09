"""
Public interface contract for ConfigManager.

This file is a CONTRACT SPECIFICATION, not implementation.
It defines the public API surface that ConfigManager must honour.
Callers import from deepeval_platform.config — not from this file.
"""
from __future__ import annotations

from typing import Any


class ConfigManagerContract:
    """
    Singleton. Loads .env and config/*.yaml exactly once per process.

    .env values take precedence over YAML values for the same key.
    Empty string values are treated as missing (raise ConfigError).
    Sensitive keys (containing key/secret/password/token/api, case-insensitive)
    are masked in __repr__ and all log output.

    Usage:
        from deepeval_platform.config import ConfigManager
        cfg = ConfigManager.instance()
        value = cfg.get("LANGFUSE_HOST")               # from .env
        value = cfg.get("embedding.model")              # from settings.yaml
        value = cfg.get("MISSING_KEY")                  # raises ConfigError
    """

    @classmethod
    def instance(cls) -> "ConfigManagerContract":
        """Return the singleton instance, loading config on first call."""
        ...

    def get(self, key: str) -> str:
        """
        Return the value for `key`.

        Raises:
            ConfigError: if key is absent or has an empty string value.
                         Error message names the key and its expected source file.
        """
        ...

    def get_optional(self, key: str, default: str = "") -> str:
        """Return the value for `key`, or `default` if absent (no error)."""
        ...

    def get_typed(self, key: str, expected_type: type) -> Any:
        """
        Return the value for `key` cast to `expected_type`.

        Raises:
            ConfigError: if key is absent/empty or value cannot be cast.
        """
        ...

    def is_loaded(self) -> bool:
        """True if config has been loaded at least once in this process."""
        ...


class ConfigError(Exception):
    """Raised when a required configuration key is absent or empty."""
