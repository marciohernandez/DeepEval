"""Configuration contract tests for the Synthetic Dataset Generator (M4.1, T001).

Asserts config/settings.yaml carries all synthetic.* settings and exporter dotted
classes, .env.example gains only the SUPABASE_ANON_KEY credential, and no
SYNTHETIC_* environment keys are introduced (Constitution Principle V).
"""
from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_settings() -> dict:
    settings_path = _REPO_ROOT / "config" / "settings.yaml"
    with open(settings_path) as fh:
        return yaml.safe_load(fh) or {}


def _load_env_example_text() -> str:
    return (_REPO_ROOT / ".env.example").read_text()


class TestSyntheticSettingsYaml:
    def test_synthetic_section_present(self):
        settings = _load_settings()
        assert "synthetic" in settings

    def test_docs_dir_configured(self):
        synthetic = _load_settings()["synthetic"]
        assert isinstance(synthetic.get("docs_dir"), str) and synthetic["docs_dir"]

    def test_output_dir_configured(self):
        synthetic = _load_settings()["synthetic"]
        assert isinstance(synthetic.get("output_dir"), str) and synthetic["output_dir"]

    def test_goldens_per_persona_configured(self):
        synthetic = _load_settings()["synthetic"]
        assert isinstance(synthetic.get("goldens_per_persona"), int)
        assert synthetic["goldens_per_persona"] > 0

    def test_conversations_per_persona_configured(self):
        synthetic = _load_settings()["synthetic"]
        assert isinstance(synthetic.get("conversations_per_persona"), int)
        assert synthetic["conversations_per_persona"] > 0

    def test_max_conversation_turns_configured(self):
        synthetic = _load_settings()["synthetic"]
        assert isinstance(synthetic.get("max_conversation_turns"), int)
        assert synthetic["max_conversation_turns"] > 0

    def test_json_exporter_dotted_class_configured(self):
        exporters = _load_settings()["synthetic"]["exporters"]
        assert exporters["json"] == (
            "deepeval_platform.synthetic.json_dataset_exporter.JsonDatasetExporter"
        )

    def test_csv_exporter_dotted_class_configured(self):
        exporters = _load_settings()["synthetic"]["exporters"]
        assert exporters["csv"] == (
            "deepeval_platform.synthetic.csv_dataset_exporter.CsvDatasetExporter"
        )


class TestEnvExampleCredential:
    def test_supabase_anon_key_present(self):
        text = _load_env_example_text()
        lines = [line.strip() for line in text.splitlines()]
        assert "SUPABASE_ANON_KEY=" in lines

    def test_no_synthetic_prefixed_env_keys(self):
        text = _load_env_example_text()
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            key = stripped.split("=", 1)[0]
            assert not key.startswith("SYNTHETIC_"), (
                f"Found forbidden SYNTHETIC_* environment key: {key!r}. "
                "Synthetic paths/thresholds must live in config/settings.yaml."
            )
