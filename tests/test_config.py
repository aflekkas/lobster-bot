import os
import tempfile
from pathlib import Path

import pytest

from core.config import load_config, ConfigError


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(content)
    return p


def test_load_valid_config(tmp_path):
    cfg_path = _write_yaml(tmp_path, """
telegram:
  token: "123:ABC"
  allowed_users:
    - 111
    - 222
""")
    cfg = load_config(cfg_path)
    assert cfg["telegram"]["token"] == "123:ABC"
    assert cfg["telegram"]["allowed_users"] == [111, 222]


def test_load_config_missing_file():
    with pytest.raises(ConfigError, match="not found"):
        load_config(Path("/nonexistent/config.yaml"))


def test_load_config_missing_telegram_token(tmp_path):
    cfg_path = _write_yaml(tmp_path, """
telegram:
  allowed_users: [111]
""")
    with pytest.raises(ConfigError, match="token"):
        load_config(cfg_path)


def test_load_config_missing_allowed_users(tmp_path):
    cfg_path = _write_yaml(tmp_path, """
telegram:
  token: "123:ABC"
""")
    with pytest.raises(ConfigError, match="allowed_users"):
        load_config(cfg_path)


def test_load_config_from_env(tmp_path, monkeypatch):
    cfg_path = _write_yaml(tmp_path, """
telegram:
  token: "123:ABC"
  allowed_users: [111]
""")
    monkeypatch.setenv("LOBSTERBOT_CONFIG", str(cfg_path))
    cfg = load_config()
    assert cfg["telegram"]["token"] == "123:ABC"
