#!/usr/bin/env python3
"""lobster-bot — run this and everything just works."""
import logging
import os
import shutil
import subprocess
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def bootstrap():
    """Install everything needed on first run."""
    missing = []

    # Python deps
    try:
        import telegram  # noqa: F401
    except ImportError:
        print("Installing Python dependencies...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"])

    # Claude Code CLI
    if not shutil.which("claude"):
        missing.append("Claude Code CLI — install: npm i -g @anthropic-ai/claude-code")

    # .env check
    if not os.environ.get("TELEGRAM_TOKEN"):
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        os.environ.setdefault(key.strip(), value.strip())

    if not os.environ.get("TELEGRAM_TOKEN"):
        missing.append("TELEGRAM_TOKEN — create a .env file (see README)")
    if not os.environ.get("TELEGRAM_USER_IDS"):
        missing.append("TELEGRAM_USER_IDS — create a .env file (see README)")

    if missing:
        print("\nMissing requirements:")
        for m in missing:
            print(f"  - {m}")
        print()
        sys.exit(1)


if __name__ == "__main__":
    bootstrap()

    # Create logs directory
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)

    # Rotating file handler (5MB per file, 3 backups)
    file_handler = RotatingFileHandler(
        log_dir / "bot.log", maxBytes=5_000_000, backupCount=3,
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[logging.StreamHandler(), file_handler],
    )

    # Silence noisy HTTP logging
    logging.getLogger("httpx").setLevel(logging.WARNING)

    from core.bot import main
    main()
