"""Integration tests for ConfigManager — exercises the full file-loading pipeline
with real files on disk (no mocking of I/O)."""

import pytest
from deepeval.config.config_manager import ConfigManager


def _setup(tmp_path, env_content: str, yaml_content: str):
    (tmp_path / ".env").write_text(env_content)
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "settings.yaml").write_text(yaml_content)


class TestRealFileLoading:
    def test_real_env_file_loaded_end_to_end(self, tmp_path, monkeypatch):
        _setup(
            tmp_path,
            env_content="OPENAI_API_KEY=integration-test-key\n",
            yaml_content="embedding:\n  model: test-model\n",
        )
        monkeypatch.chdir(tmp_path)

        cfg = ConfigManager.instance()
        assert cfg.get("OPENAI_API_KEY") == "integration-test-key"

    def test_real_settings_yaml_loaded_via_dot_notation(self, tmp_path, monkeypatch):
        _setup(
            tmp_path,
            env_content="",
            yaml_content=(
                "embedding:\n"
                "  model: text-embedding-3-small\n"
                "  dimensions: 1536\n"
                "qdrant:\n"
                "  port: 6333\n"
            ),
        )
        monkeypatch.chdir(tmp_path)

        cfg = ConfigManager.instance()
        assert cfg.get("embedding.model") == "text-embedding-3-small"
        assert cfg.get("embedding.dimensions") == "1536"
        assert cfg.get("qdrant.port") == "6333"

    def test_singleton_stable_across_import_statements(self, tmp_path, monkeypatch):
        """Importing ConfigManager from different paths in the same process must return
        the same object — verifies the Singleton is bound to the class, not the import."""
        _setup(
            tmp_path,
            env_content="OPENAI_API_KEY=stable-test-key\n",
            yaml_content="embedding:\n  model: test-model\n",
        )
        monkeypatch.chdir(tmp_path)

        from deepeval.config.config_manager import ConfigManager as CM1
        from deepeval.config import ConfigManager as CM2

        instance1 = CM1.instance()
        instance2 = CM2.instance()

        assert instance1 is instance2

    def test_env_and_yaml_both_loaded_in_same_instance(self, tmp_path, monkeypatch):
        _setup(
            tmp_path,
            env_content="OPENAI_API_KEY=env-key\n",
            yaml_content="embedding:\n  model: yaml-model\n",
        )
        monkeypatch.chdir(tmp_path)

        cfg = ConfigManager.instance()
        assert cfg.get("OPENAI_API_KEY") == "env-key"
        assert cfg.get("embedding.model") == "yaml-model"
