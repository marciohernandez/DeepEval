import pytest
from unittest.mock import MagicMock

# Safe credential stubs for all M1 .env keys
_STUB_ENV = {
    "LANGFUSE_HOST": "http://localhost:3000",
    "LANGFUSE_PUBLIC_KEY": "test-langfuse-public-key",
    "LANGFUSE_SECRET_KEY": "test-langfuse-secret-key",
    "QDRANT_HOST": "localhost",
    "QDRANT_API_KEY": "test-qdrant-api-key",
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_SERVICE_KEY": "test-supabase-service-key",
    "DATABASE_URL": "postgresql://postgres:test@localhost:5432/postgres",
    "OPENAI_API_KEY": "test-openai-api-key",
    "ANTHROPIC_API_KEY": "test-anthropic-api-key",
    "OPENROUTER_API_KEY": "test-openrouter-api-key",
}

# Stub values for YAML dot-notation keys from config/settings.yaml
_STUB_YAML = {
    "embedding.model": "text-embedding-3-small",
    "embedding.dimensions": "1536",
    "qdrant.port": "6333",
    "openai.default_model": "gpt-4o",
    "anthropic.default_model": "claude-sonnet-4-6",
    "openrouter.default_model": "openai/gpt-4o",
}

_STUB_ALL = {**_STUB_ENV, **_STUB_YAML}


@pytest.fixture
def mock_env(monkeypatch):
    """Patch os.environ with safe credential stubs for all M1 keys."""
    for key, value in _STUB_ENV.items():
        monkeypatch.setenv(key, value)
    return _STUB_ENV.copy()


@pytest.fixture
def mock_config(mocker):
    """Pre-configured stub ConfigManager instance for unit tests.

    Patches ConfigManager.instance() so all modules receive deterministic
    test values without requiring a real .env or config/*.yaml on disk.
    """
    config = MagicMock()
    config.get.side_effect = lambda key: _STUB_ALL[key]
    config.get_optional.side_effect = lambda key, default="": _STUB_ALL.get(key, default)
    config.get_typed.side_effect = lambda key, t: t(_STUB_ALL[key])
    mocker.patch(
        "deepeval.config.config_manager.ConfigManager.instance",
        return_value=config,
    )
    return config


@pytest.fixture(autouse=True, scope="function")
def reset_config_singleton():
    """Reset ConfigManager singleton state after every test to prevent leakage."""
    yield
    try:
        from deepeval.config.config_manager import ConfigManager
        ConfigManager._instance = None
        ConfigManager._loaded = False
    except ImportError:
        pass
