from pathlib import Path
import os

import yaml


class ConfigError(Exception):
    pass


_DEFAULT_PATH = Path("user/config.yaml")


def load_config(path: Path | None = None) -> dict:
    if path is None:
        env = os.environ.get("LOBSTERBOT_CONFIG")
        path = Path(env) if env else _DEFAULT_PATH

    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    with open(path) as f:
        cfg = yaml.safe_load(f)

    tg = cfg.get("telegram", {})
    if not tg.get("token"):
        raise ConfigError("telegram.token is required in config")
    if not tg.get("allowed_users"):
        raise ConfigError("telegram.allowed_users is required in config")

    return cfg
