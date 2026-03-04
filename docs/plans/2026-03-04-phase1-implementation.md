# Phase 1: Walking Skeleton — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Working text-based Telegram assistant that bridges messages to Claude Code via subprocess calls and maintains conversation sessions.

**Architecture:** A thin Python async layer (`python-telegram-bot`) receives Telegram messages, looks up or creates a Claude Code session in SQLite, shells out to `claude -p` with `--resume`, and sends the response back. Config lives in YAML, permissions in `.claude/settings.json`.

**Tech Stack:** Python 3.14, python-telegram-bot 21.x, pyyaml, sqlite3 (stdlib), pytest, pytest-asyncio

---

### Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`
- Create: `core/__init__.py`
- Create: `tests/__init__.py`

**Step 1: Create requirements files**

`requirements.txt`:
```
python-telegram-bot>=21.0
pyyaml>=6.0
```

`requirements-dev.txt`:
```
-r requirements.txt
pytest>=8.0
pytest-asyncio>=0.23
```

**Step 2: Create .gitignore**

```gitignore
# Python
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
.venv/
venv/

# Project
user/
memory/
*.db

# OS
.DS_Store
```

**Step 3: Create empty package init files**

`core/__init__.py` — empty file
`tests/__init__.py` — empty file

**Step 4: Install dependencies**

Run: `pip3 install -r requirements-dev.txt`

**Step 5: Commit**

```bash
git add requirements.txt requirements-dev.txt .gitignore core/__init__.py tests/__init__.py
git commit -m "chore: project scaffolding with dependencies and gitignore"
```

---

### Task 2: Config Loader (`core/config.py`)

**Files:**
- Create: `core/config.py`
- Create: `tests/test_config.py`
- Create: `user.example/config.yaml`

**Step 1: Write the failing tests**

`tests/test_config.py`:
```python
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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.config'`

**Step 3: Write minimal implementation**

`core/config.py`:
```python
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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: All 5 tests PASS

**Step 5: Create the example config template**

`user.example/config.yaml`:
```yaml
telegram:
  # Get a token from @BotFather on Telegram
  token: "YOUR_BOT_TOKEN_HERE"

  # Your Telegram user ID(s) — only these users can talk to the bot
  # Find yours by messaging @userinfobot on Telegram
  allowed_users:
    - 123456789
```

**Step 6: Commit**

```bash
git add core/config.py tests/test_config.py user.example/config.yaml
git commit -m "feat: add YAML config loader with validation"
```

---

### Task 3: Claude Code Bridge (`core/bridge.py`)

**Files:**
- Create: `core/bridge.py`
- Create: `tests/test_bridge.py`

**Step 1: Write the failing tests**

`tests/test_bridge.py`:
```python
import json
from unittest.mock import AsyncMock, patch, MagicMock
from dataclasses import asdict

import pytest

from core.bridge import ClaudeResponse, send_message


@pytest.fixture
def mock_claude_success():
    """Simulates successful claude -p JSON output."""
    return json.dumps({
        "type": "result",
        "result": "Hello! How can I help?",
        "session_id": "sess-abc-123",
        "cost_usd": 0.003,
        "usage": {"input_tokens": 50, "output_tokens": 20},
    })


@pytest.fixture
def mock_claude_error():
    return json.dumps({
        "type": "error",
        "error": "Something went wrong",
    })


@pytest.mark.asyncio
async def test_send_message_new_session(mock_claude_success):
    proc = AsyncMock()
    proc.communicate.return_value = (mock_claude_success.encode(), b"")
    proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
        resp = await send_message("Hello", project_dir="/tmp/bot")

    assert resp.text == "Hello! How can I help?"
    assert resp.session_id == "sess-abc-123"
    assert resp.cost_usd == 0.003

    cmd_args = mock_exec.call_args[0]
    assert "--resume" not in cmd_args
    assert "--output-format" in cmd_args
    assert "json" in cmd_args


@pytest.mark.asyncio
async def test_send_message_resume_session(mock_claude_success):
    proc = AsyncMock()
    proc.communicate.return_value = (mock_claude_success.encode(), b"")
    proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
        resp = await send_message("Hi again", session_id="sess-abc-123", project_dir="/tmp/bot")

    cmd_args = mock_exec.call_args[0]
    assert "--resume" in cmd_args
    assert "sess-abc-123" in cmd_args


@pytest.mark.asyncio
async def test_send_message_strips_claudecode_env():
    proc = AsyncMock()
    proc.communicate.return_value = (
        json.dumps({"type": "result", "result": "ok", "session_id": "s1", "cost_usd": 0, "usage": {}}).encode(),
        b"",
    )
    proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
        with patch.dict("os.environ", {"CLAUDECODE": "1", "HOME": "/tmp"}):
            await send_message("test", project_dir="/tmp/bot")

    env = mock_exec.call_args[1].get("env", {})
    assert "CLAUDECODE" not in env


@pytest.mark.asyncio
async def test_send_message_error_response(mock_claude_error):
    proc = AsyncMock()
    proc.communicate.return_value = (mock_claude_error.encode(), b"")
    proc.returncode = 1

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        resp = await send_message("Hello", project_dir="/tmp/bot")

    assert resp.text == "Something went wrong"
    assert resp.is_error is True
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bridge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.bridge'`

**Step 3: Write minimal implementation**

`core/bridge.py`:
```python
import asyncio
import json
import os
from dataclasses import dataclass


@dataclass
class ClaudeResponse:
    text: str
    session_id: str | None = None
    cost_usd: float = 0.0
    usage: dict | None = None
    is_error: bool = False


async def send_message(
    message: str,
    *,
    session_id: str | None = None,
    project_dir: str = ".",
) -> ClaudeResponse:
    cmd = [
        "claude",
        "-p", message,
        "--output-format", "json",
        "--permission-mode", "bypassPermissions",
    ]
    if session_id:
        cmd.extend(["--resume", session_id])

    # Strip CLAUDECODE env var to allow nested subprocess invocation
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=project_dir,
        env=env,
    )
    stdout, stderr = await proc.communicate()

    try:
        data = json.loads(stdout.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ClaudeResponse(
            text=f"Failed to parse Claude response: {stderr.decode()[:500]}",
            is_error=True,
        )

    if data.get("type") == "error":
        return ClaudeResponse(
            text=data.get("error", "Unknown error"),
            is_error=True,
        )

    return ClaudeResponse(
        text=data.get("result", ""),
        session_id=data.get("session_id"),
        cost_usd=data.get("cost_usd", 0.0),
        usage=data.get("usage"),
    )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_bridge.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add core/bridge.py tests/test_bridge.py
git commit -m "feat: add Claude Code subprocess bridge"
```

---

### Task 4: Session Manager (`core/session.py`)

**Files:**
- Create: `core/session.py`
- Create: `tests/test_session.py`

**Step 1: Write the failing tests**

`tests/test_session.py`:
```python
import time
from pathlib import Path

import pytest

from core.session import SessionManager


@pytest.fixture
def sm(tmp_path):
    return SessionManager(tmp_path / "sessions.db")


def test_no_session_initially(sm):
    assert sm.get_session(12345) is None


def test_store_and_retrieve_session(sm):
    sm.set_session(12345, "sess-abc")
    assert sm.get_session(12345) == "sess-abc"


def test_update_session(sm):
    sm.set_session(12345, "sess-old")
    sm.set_session(12345, "sess-new")
    assert sm.get_session(12345) == "sess-new"


def test_clear_session(sm):
    sm.set_session(12345, "sess-abc")
    sm.clear_session(12345)
    assert sm.get_session(12345) is None


def test_archive_stale_sessions(sm):
    sm.set_session(12345, "sess-abc")
    # Manually backdate the updated_at to simulate staleness
    sm._db.execute(
        "UPDATE sessions SET updated_at = updated_at - 90000 WHERE chat_id = ?",
        (12345,),
    )
    sm._db.commit()
    archived = sm.archive_stale(max_age_seconds=86400)
    assert archived == 1
    assert sm.get_session(12345) is None


def test_list_archived_sessions(sm):
    sm.set_session(12345, "sess-abc")
    sm._db.execute(
        "UPDATE sessions SET updated_at = updated_at - 90000 WHERE chat_id = ?",
        (12345,),
    )
    sm._db.commit()
    sm.archive_stale(max_age_seconds=86400)
    history = sm.get_history(12345)
    assert len(history) == 1
    assert history[0]["session_id"] == "sess-abc"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_session.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.session'`

**Step 3: Write minimal implementation**

`core/session.py`:
```python
import sqlite3
import time
from pathlib import Path


class SessionManager:
    def __init__(self, db_path: Path):
        self._db = sqlite3.connect(str(db_path))
        self._db.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                chat_id INTEGER PRIMARY KEY,
                session_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS session_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                session_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                archived_at REAL NOT NULL
            );
        """)

    def get_session(self, chat_id: int) -> str | None:
        row = self._db.execute(
            "SELECT session_id FROM sessions WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        return row["session_id"] if row else None

    def set_session(self, chat_id: int, session_id: str):
        now = time.time()
        self._db.execute(
            """INSERT INTO sessions (chat_id, session_id, created_at, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(chat_id)
               DO UPDATE SET session_id = excluded.session_id, updated_at = excluded.updated_at""",
            (chat_id, session_id, now, now),
        )
        self._db.commit()

    def clear_session(self, chat_id: int):
        self._db.execute("DELETE FROM sessions WHERE chat_id = ?", (chat_id,))
        self._db.commit()

    def touch_session(self, chat_id: int):
        self._db.execute(
            "UPDATE sessions SET updated_at = ? WHERE chat_id = ?",
            (time.time(), chat_id),
        )
        self._db.commit()

    def archive_stale(self, max_age_seconds: int = 86400) -> int:
        cutoff = time.time() - max_age_seconds
        stale = self._db.execute(
            "SELECT * FROM sessions WHERE updated_at < ?", (cutoff,)
        ).fetchall()

        now = time.time()
        for row in stale:
            self._db.execute(
                "INSERT INTO session_history (chat_id, session_id, created_at, archived_at) VALUES (?, ?, ?, ?)",
                (row["chat_id"], row["session_id"], row["created_at"], now),
            )
            self._db.execute("DELETE FROM sessions WHERE chat_id = ?", (row["chat_id"],))

        self._db.commit()
        return len(stale)

    def get_history(self, chat_id: int) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM session_history WHERE chat_id = ? ORDER BY archived_at DESC",
            (chat_id,),
        ).fetchall()
        return [dict(r) for r in rows]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_session.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add core/session.py tests/test_session.py
git commit -m "feat: add SQLite session manager"
```

---

### Task 5: Telegram Bot (`core/bot.py`)

**Files:**
- Create: `core/bot.py`
- Create: `tests/test_bot.py`

**Step 1: Write the failing tests**

`tests/test_bot.py`:
```python
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from core.bot import handle_message, handle_new, is_authorized
from core.bridge import ClaudeResponse


@pytest.fixture
def mock_update():
    update = MagicMock()
    update.effective_user.id = 111
    update.effective_chat.id = 111
    update.message.text = "Hello bot"
    update.message.reply_text = AsyncMock()
    update.message.chat.send_action = AsyncMock()
    return update


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock()
    return ctx


def test_is_authorized_allowed():
    assert is_authorized(111, [111, 222]) is True


def test_is_authorized_denied():
    assert is_authorized(999, [111, 222]) is False


@pytest.mark.asyncio
async def test_handle_message_unauthorized(mock_update, mock_context):
    mock_update.effective_user.id = 999
    with patch("core.bot._config", {"telegram": {"allowed_users": [111]}}):
        await handle_message(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_once()
    assert "not authorized" in mock_update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_handle_message_success(mock_update, mock_context):
    mock_response = ClaudeResponse(text="Hi there!", session_id="sess-1")

    with (
        patch("core.bot._config", {"telegram": {"allowed_users": [111]}}),
        patch("core.bot._sessions") as mock_sm,
        patch("core.bot.send_message", new_callable=AsyncMock, return_value=mock_response),
        patch("core.bot._project_dir", "/tmp/bot"),
    ):
        mock_sm.get_session.return_value = None
        await handle_message(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_once_with("Hi there!")
    mock_sm.set_session.assert_called_once_with(111, "sess-1")


@pytest.mark.asyncio
async def test_handle_message_resumes_session(mock_update, mock_context):
    mock_response = ClaudeResponse(text="Continuing!", session_id="sess-1")

    with (
        patch("core.bot._config", {"telegram": {"allowed_users": [111]}}),
        patch("core.bot._sessions") as mock_sm,
        patch("core.bot.send_message", new_callable=AsyncMock, return_value=mock_response) as mock_send,
        patch("core.bot._project_dir", "/tmp/bot"),
    ):
        mock_sm.get_session.return_value = "sess-1"
        await handle_message(mock_update, mock_context)

    mock_send.assert_called_once_with("Hello bot", session_id="sess-1", project_dir="/tmp/bot")


@pytest.mark.asyncio
async def test_handle_new_clears_session(mock_update, mock_context):
    with (
        patch("core.bot._config", {"telegram": {"allowed_users": [111]}}),
        patch("core.bot._sessions") as mock_sm,
    ):
        await handle_new(mock_update, mock_context)

    mock_sm.clear_session.assert_called_once_with(111)
    mock_update.message.reply_text.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bot.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.bot'`

**Step 3: Write minimal implementation**

`core/bot.py`:
```python
import logging
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from core.bridge import send_message, ClaudeResponse
from core.config import load_config
from core.session import SessionManager

logger = logging.getLogger(__name__)

# Module-level state, initialized in main()
_config: dict = {}
_sessions: SessionManager | None = None
_project_dir: str = "."


def is_authorized(user_id: int, allowed: list[int]) -> bool:
    return user_id in allowed


async def handle_message(update: Update, context) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_authorized(user_id, _config["telegram"]["allowed_users"]):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    session_id = _sessions.get_session(chat_id)
    response = await send_message(
        update.message.text,
        session_id=session_id,
        project_dir=_project_dir,
    )

    if response.session_id:
        _sessions.set_session(chat_id, response.session_id)

    await update.message.reply_text(response.text)


async def handle_new(update: Update, context) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_authorized(user_id, _config["telegram"]["allowed_users"]):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    _sessions.clear_session(chat_id)
    await update.message.reply_text("Started a new conversation.")


async def handle_status(update: Update, context) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_authorized(user_id, _config["telegram"]["allowed_users"]):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    session_id = _sessions.get_session(chat_id)
    status = "Active session" if session_id else "No active session"
    await update.message.reply_text(f"Status: {status}\nSession: {session_id or 'none'}")


async def handle_help(update: Update, context) -> None:
    await update.message.reply_text(
        "/new — Start a new conversation\n"
        "/status — Session info\n"
        "/help — Show this message"
    )


def main():
    global _config, _sessions, _project_dir

    _project_dir = str(Path(__file__).resolve().parent.parent)
    _config = load_config()
    _sessions = SessionManager(Path(_project_dir) / "sessions.db")

    app = Application.builder().token(_config["telegram"]["token"]).build()
    app.add_handler(CommandHandler("new", handle_new))
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CommandHandler("help", handle_help))
    app.add_handler(CommandHandler("start", handle_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_bot.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add core/bot.py tests/test_bot.py
git commit -m "feat: add Telegram bot with message handling and commands"
```

---

### Task 6: Claude Configuration Files

**Files:**
- Create: `CLAUDE.md`
- Create: `.claude/settings.json`

**Step 1: Create CLAUDE.md**

`CLAUDE.md`:
```markdown
# Lobsterbot — Personal Assistant

You are a helpful personal assistant running on Telegram. You have a warm, friendly tone. Keep responses concise — Telegram messages should be easy to read on a phone.

## Guidelines

- Be conversational and natural, not robotic
- Keep responses short unless the user asks for detail
- Use simple formatting — Telegram supports basic markdown (*bold*, _italic_, `code`)
- If you don't know something, say so honestly
- Remember you're chatting on a phone — break up long responses into readable chunks

## Tools Available

- You can search the web using WebSearch and WebFetch
- You can read and write files in the memory/ directory
- You can run basic shell commands (date, python3, curl, etc.)

## Memory

When you learn something important about the user, save it to `memory/facts.md`.
```

**Step 2: Create .claude/settings.json**

`.claude/settings.json`:
```json
{
  "permissions": {
    "allow": [
      "Read",
      "WebSearch",
      "WebFetch(*)",
      "Write(./memory/**)",
      "Edit(./memory/**)",
      "Bash(date*)",
      "Bash(python3*)",
      "Bash(curl -s*)",
      "Bash(ls*)",
      "Bash(cat*)",
      "Bash(head*)",
      "Bash(tail*)",
      "Bash(wc*)",
      "Bash(echo*)"
    ],
    "deny": [
      "Write(./core/**)",
      "Write(./.claude/**)",
      "Edit(./core/**)",
      "Edit(./.claude/**)",
      "Bash(sudo*)",
      "Bash(rm -rf*)",
      "Bash(systemctl*)",
      "Bash(chmod*)",
      "Bash(chown*)",
      "Read(./.env)"
    ]
  }
}
```

**Step 3: Commit**

```bash
git add CLAUDE.md .claude/settings.json
git commit -m "feat: add CLAUDE.md personality and permissions config"
```

---

### Task 7: Entry Point and README

**Files:**
- Create: `run.py`
- Create: `README.md`

**Step 1: Create entry point**

`run.py`:
```python
#!/usr/bin/env python3
import logging
from core.bot import main

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    main()
```

**Step 2: Create README**

`README.md`:
```markdown
# lobsterbot

A 24/7 personal AI assistant on Telegram, powered by Claude Code.

## Quick Start

1. Fork this repo
2. Copy config template: `cp -r user.example user`
3. Edit `user/config.yaml` with your Telegram bot token and user ID
4. Install dependencies: `pip install -r requirements.txt`
5. Run: `python run.py`

## Getting a Telegram Bot Token

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the token into `user/config.yaml`

## Finding Your Telegram User ID

Message [@userinfobot](https://t.me/userinfobot) on Telegram — it will reply with your user ID.

## Requirements

- Python 3.11+
- Claude Code CLI (`claude`) installed and authenticated
- A Telegram bot token

## Commands

- `/new` — Start a new conversation
- `/status` — Session info
- `/help` — Available commands
```

**Step 3: Commit**

```bash
git add run.py README.md
git commit -m "feat: add entry point and README"
```

---

### Task 8: Run All Tests and Verify

**Step 1: Run the full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS (15 total)

**Step 2: Verify the project structure is correct**

Run: `find . -not -path './.git/*' -not -name '.DS_Store' -not -name '__pycache__' | sort`

Expected output matches the Phase 1 design:
```
.
./CLAUDE.md
./.claude
./.claude/settings.json
./.gitignore
./core
./core/__init__.py
./core/bot.py
./core/bridge.py
./core/config.py
./core/session.py
./docs
./docs/plans
./docs/plans/2026-03-04-lobsterbot-design.md
./docs/plans/2026-03-04-phase1-implementation.md
./README.md
./requirements.txt
./requirements-dev.txt
./run.py
./tests
./tests/__init__.py
./tests/test_bot.py
./tests/test_bridge.py
./tests/test_config.py
./tests/test_session.py
./user.example
./user.example/config.yaml
```

**Step 3: Smoke test (manual)**

1. `cp -r user.example user`
2. Edit `user/config.yaml` with a real bot token and your user ID
3. `python run.py`
4. Send a message to your bot on Telegram
5. Verify you get a Claude-powered response back

---

## Summary

| Task | Component | Tests | Lines (approx) |
|------|-----------|-------|-----------------|
| 1 | Scaffolding | — | — |
| 2 | `core/config.py` | 5 | ~35 |
| 3 | `core/bridge.py` | 4 | ~55 |
| 4 | `core/session.py` | 6 | ~75 |
| 5 | `core/bot.py` | 6 | ~95 |
| 6 | CLAUDE.md + settings | — | — |
| 7 | run.py + README | — | — |
| 8 | Full verification | — | — |

**Total:** ~260 lines of Python, ~15 tests, 7 commits
