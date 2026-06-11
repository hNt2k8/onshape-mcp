"""Offline tests for config precedence and validation."""

import pytest

from onshape_mcp.config import Config, ConfigError, load_config

ALL_VARS = (
    "ONSHAPE_ACCESS_KEY",
    "ONSHAPE_SECRET_KEY",
    "ONSHAPE_BASE_URL",
    "ONSHAPE_API_VERSION",
    "ONSHAPE_AUTH",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ALL_VARS:
        monkeypatch.delenv(var, raising=False)


def write_env(tmp_path, **vals):
    env_file = tmp_path / ".env"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in vals.items()))
    return env_file


def test_loads_from_file(tmp_path):
    env_file = write_env(
        tmp_path, ONSHAPE_ACCESS_KEY="file_access", ONSHAPE_SECRET_KEY="file_secret"
    )
    config = load_config(env_file)
    assert config.access_key == "file_access"
    assert config.secret_key == "file_secret"
    assert config.api_root == "https://cad.onshape.com/api/v10"
    assert config.auth == "hmac"


def test_process_env_overrides_file(tmp_path, monkeypatch):
    env_file = write_env(
        tmp_path, ONSHAPE_ACCESS_KEY="file_access", ONSHAPE_SECRET_KEY="file_secret"
    )
    monkeypatch.setenv("ONSHAPE_ACCESS_KEY", "env_access")
    config = load_config(env_file)
    assert config.access_key == "env_access"
    assert config.secret_key == "file_secret"


def test_empty_env_var_falls_through_to_file(tmp_path, monkeypatch):
    env_file = write_env(
        tmp_path, ONSHAPE_ACCESS_KEY="file_access", ONSHAPE_SECRET_KEY="file_secret"
    )
    monkeypatch.setenv("ONSHAPE_ACCESS_KEY", "")
    config = load_config(env_file)
    assert config.access_key == "file_access"


def test_whitespace_only_env_var_falls_through_to_file(tmp_path, monkeypatch):
    env_file = write_env(
        tmp_path, ONSHAPE_ACCESS_KEY="file_access", ONSHAPE_SECRET_KEY="file_secret"
    )
    monkeypatch.setenv("ONSHAPE_ACCESS_KEY", "   ")
    config = load_config(env_file)
    assert config.access_key == "file_access"


def test_whitespace_only_base_url_falls_back_to_default(tmp_path, monkeypatch):
    env_file = write_env(
        tmp_path, ONSHAPE_ACCESS_KEY="a", ONSHAPE_SECRET_KEY="s"
    )
    monkeypatch.setenv("ONSHAPE_BASE_URL", "  ")
    config = load_config(env_file)
    assert config.api_root == "https://cad.onshape.com/api/v10"


def test_missing_keys_raises_with_setup_hint(tmp_path):
    env_file = write_env(tmp_path, ONSHAPE_ACCESS_KEY="only_access")
    with pytest.raises(ConfigError, match="setup"):
        load_config(env_file)


def test_missing_file_raises_with_setup_hint(tmp_path):
    with pytest.raises(ConfigError, match="setup"):
        load_config(tmp_path / "nonexistent.env")


def test_optional_overrides(tmp_path):
    env_file = write_env(
        tmp_path,
        ONSHAPE_ACCESS_KEY="a",
        ONSHAPE_SECRET_KEY="s",
        ONSHAPE_BASE_URL="https://example.onshape.com/",
        ONSHAPE_API_VERSION="v6",
        ONSHAPE_AUTH="basic",
    )
    config = load_config(env_file)
    assert config.api_root == "https://example.onshape.com/api/v6"
    assert config.auth == "basic"


def test_invalid_auth_rejected(tmp_path):
    env_file = write_env(
        tmp_path, ONSHAPE_ACCESS_KEY="a", ONSHAPE_SECRET_KEY="s", ONSHAPE_AUTH="oauth"
    )
    with pytest.raises(ConfigError, match="ONSHAPE_AUTH"):
        load_config(env_file)


def test_secrets_not_in_repr():
    config = Config(access_key="SUPERSECRETACCESS", secret_key="SUPERSECRETKEY")
    assert "SUPERSECRET" not in repr(config)


def test_with_auth_returns_new_config():
    config = Config(access_key="a", secret_key="s")
    basic = config.with_auth("basic")
    assert basic.auth == "basic"
    assert config.auth == "hmac"
    with pytest.raises(ConfigError):
        config.with_auth("digest")
