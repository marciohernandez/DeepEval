import pytest
from deepeval.config.config_manager import ConfigManager, ConfigError, ConfigEntry


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_env(tmp_path, content: str) -> None:
    (tmp_path / ".env").write_text(content)


def _make_settings(tmp_path, content: str) -> None:
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "settings.yaml").write_text(content)


# ── Singleton ─────────────────────────────────────────────────────────────────

class TestSingleton:
    def test_instance_returns_same_object(self, tmp_path, monkeypatch):
        _make_env(tmp_path, "OPENAI_API_KEY=sk-test\n")
        _make_settings(tmp_path, "embedding:\n  model: text-embedding-3-small\n")
        monkeypatch.chdir(tmp_path)

        c1 = ConfigManager.instance()
        c2 = ConfigManager.instance()
        assert c1 is c2

    def test_second_call_does_not_re_read(self, tmp_path, monkeypatch):
        _make_env(tmp_path, "OPENAI_API_KEY=sk-original\n")
        _make_settings(tmp_path, "{}")
        monkeypatch.chdir(tmp_path)

        ConfigManager.instance()
        # Overwrite the file — the singleton must NOT pick up the change
        (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-changed\n")
        cfg = ConfigManager.instance()

        assert cfg.get("OPENAI_API_KEY") == "sk-original"


# ── .env loading ──────────────────────────────────────────────────────────────

class TestEnvLoading:
    def test_env_value_loaded(self, tmp_path, monkeypatch):
        _make_env(tmp_path, "OPENAI_API_KEY=sk-test\n")
        _make_settings(tmp_path, "{}")
        monkeypatch.chdir(tmp_path)

        cfg = ConfigManager.instance()
        assert cfg.get("OPENAI_API_KEY") == "sk-test"

    def test_yaml_value_loaded_via_dot_notation(self, tmp_path, monkeypatch):
        _make_env(tmp_path, "OPENAI_API_KEY=sk-test\n")
        _make_settings(tmp_path, "embedding:\n  model: text-embedding-3-small\n  dimensions: 1536\n")
        monkeypatch.chdir(tmp_path)

        cfg = ConfigManager.instance()
        assert cfg.get("embedding.model") == "text-embedding-3-small"

    def test_env_takes_precedence_over_yaml(self, tmp_path, monkeypatch):
        _make_env(tmp_path, "SHARED_KEY=from-env\n")
        _make_settings(tmp_path, "SHARED_KEY: from-yaml\n")
        monkeypatch.chdir(tmp_path)

        cfg = ConfigManager.instance()
        assert cfg.get("SHARED_KEY") == "from-env"

    def test_env_precedence_raises_no_exception(self, tmp_path, monkeypatch):
        """When the same key exists in both .env and YAML, .env wins — no ConfigError."""
        _make_env(tmp_path, "SHARED_KEY=env-value\n")
        _make_settings(tmp_path, "SHARED_KEY: yaml-value\n")
        monkeypatch.chdir(tmp_path)

        cfg = ConfigManager.instance()
        try:
            result = cfg.get("SHARED_KEY")
        except Exception as exc:
            pytest.fail(f"No exception expected when key exists in both sources, got: {exc}")
        assert result == "env-value"


# ── ConfigError ───────────────────────────────────────────────────────────────

class TestConfigError:
    def test_absent_key_raises_config_error(self, tmp_path, monkeypatch):
        _make_env(tmp_path, "")
        _make_settings(tmp_path, "{}")
        monkeypatch.chdir(tmp_path)

        cfg = ConfigManager.instance()
        with pytest.raises(ConfigError) as exc_info:
            cfg.get("NONEXISTENT_KEY")
        assert "NONEXISTENT_KEY" in str(exc_info.value)

    def test_absent_key_names_source_file_in_message(self, tmp_path, monkeypatch):
        _make_env(tmp_path, "")
        _make_settings(tmp_path, "{}")
        monkeypatch.chdir(tmp_path)

        cfg = ConfigManager.instance()
        with pytest.raises(ConfigError) as exc_info:
            cfg.get("MISSING_KEY")
        msg = str(exc_info.value).lower()
        # Message must reference a source (env or config file)
        assert any(term in msg for term in ("env", "yaml", "config", ".env"))

    def test_empty_string_raises_config_error(self, tmp_path, monkeypatch):
        _make_env(tmp_path, "OPENAI_API_KEY=\n")
        _make_settings(tmp_path, "{}")
        monkeypatch.chdir(tmp_path)

        cfg = ConfigManager.instance()
        with pytest.raises(ConfigError) as exc_info:
            cfg.get("OPENAI_API_KEY")
        assert "OPENAI_API_KEY" in str(exc_info.value)

    def test_empty_string_identical_to_absent(self, tmp_path, monkeypatch):
        """Empty string value and absent key must both raise ConfigError."""
        _make_env(tmp_path, "EMPTY_KEY=\n")
        _make_settings(tmp_path, "{}")
        monkeypatch.chdir(tmp_path)

        cfg = ConfigManager.instance()
        with pytest.raises(ConfigError):
            cfg.get("EMPTY_KEY")
        with pytest.raises(ConfigError):
            cfg.get("TOTALLY_ABSENT_KEY")


# ── Sensitive key masking ─────────────────────────────────────────────────────

class TestSensitiveKeyMasking:
    def test_config_entry_repr_masks_sensitive_value(self):
        entry = ConfigEntry(
            key="ANTHROPIC_API_KEY",
            value="real-secret-value",
            source="env",
            source_file=".env",
            is_sensitive=True,
        )
        assert "real-secret-value" not in repr(entry)
        assert "***" in repr(entry)

    def test_config_entry_repr_shows_non_sensitive_value(self):
        entry = ConfigEntry(
            key="embedding.model",
            value="text-embedding-3-small",
            source="yaml",
            source_file="config/settings.yaml",
            is_sensitive=False,
        )
        assert "text-embedding-3-small" in repr(entry)
        assert "***" not in repr(entry)

    def test_manager_repr_masks_api_key(self, tmp_path, monkeypatch):
        _make_env(tmp_path, "OPENAI_API_KEY=sk-should-be-masked\n")
        _make_settings(tmp_path, "{}")
        monkeypatch.chdir(tmp_path)

        cfg = ConfigManager.instance()
        assert "sk-should-be-masked" not in repr(cfg)
        assert "***" in repr(cfg)

    def test_manager_repr_does_not_mask_non_sensitive(self, tmp_path, monkeypatch):
        _make_env(tmp_path, "")
        _make_settings(tmp_path, "embedding:\n  model: text-embedding-3-small\n")
        monkeypatch.chdir(tmp_path)

        cfg = ConfigManager.instance()
        assert "text-embedding-3-small" in repr(cfg)

    def test_sensitive_detection_covers_required_terms(self):
        sensitive_keys = [
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY",
            "LANGFUSE_SECRET_KEY", "LANGFUSE_PUBLIC_KEY",
            "SUPABASE_SERVICE_KEY", "QDRANT_API_KEY",
            "MY_PASSWORD", "AUTH_TOKEN",
        ]
        for key in sensitive_keys:
            entry = ConfigEntry(key=key, value="v", source="env", source_file=".env", is_sensitive=True)
            assert "***" in repr(entry), f"Expected {key} to be masked"


# ── get_optional ──────────────────────────────────────────────────────────────

class TestGetOptional:
    def test_returns_default_when_key_absent(self, tmp_path, monkeypatch):
        _make_env(tmp_path, "")
        _make_settings(tmp_path, "{}")
        monkeypatch.chdir(tmp_path)

        cfg = ConfigManager.instance()
        assert cfg.get_optional("MISSING_KEY", default="fallback") == "fallback"

    def test_default_is_empty_string_when_unspecified(self, tmp_path, monkeypatch):
        _make_env(tmp_path, "")
        _make_settings(tmp_path, "{}")
        monkeypatch.chdir(tmp_path)

        cfg = ConfigManager.instance()
        assert cfg.get_optional("MISSING_KEY") == ""

    def test_returns_value_when_key_present(self, tmp_path, monkeypatch):
        _make_env(tmp_path, "EXISTING_KEY=found-it\n")
        _make_settings(tmp_path, "{}")
        monkeypatch.chdir(tmp_path)

        cfg = ConfigManager.instance()
        assert cfg.get_optional("EXISTING_KEY", default="fallback") == "found-it"


# ── get_typed ─────────────────────────────────────────────────────────────────

class TestGetTyped:
    def test_casts_to_int(self, tmp_path, monkeypatch):
        _make_env(tmp_path, "")
        _make_settings(tmp_path, "qdrant:\n  port: 6333\n")
        monkeypatch.chdir(tmp_path)

        cfg = ConfigManager.instance()
        result = cfg.get_typed("qdrant.port", int)
        assert result == 6333
        assert isinstance(result, int)

    def test_raises_config_error_on_cast_failure(self, tmp_path, monkeypatch):
        _make_env(tmp_path, "BAD_PORT=not-a-number\n")
        _make_settings(tmp_path, "{}")
        monkeypatch.chdir(tmp_path)

        cfg = ConfigManager.instance()
        with pytest.raises(ConfigError):
            cfg.get_typed("BAD_PORT", int)
