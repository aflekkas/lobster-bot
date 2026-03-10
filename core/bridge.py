import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Track running processes per chat so we can cancel them
_active_procs: dict[int, asyncio.subprocess.Process] = {}


@dataclass
class ClaudeResponse:
    text: str
    session_id: str | None = None
    cost_usd: float = 0.0
    usage: dict | None = None
    is_error: bool = False


def _sanitize_unicode(text: str) -> str:
    """Strip unpaired surrogates that crash Telegram's API."""
    return re.sub(r"[\ud800-\udfff]", "", text)


def cancel_chat(chat_id: int) -> bool:
    """Kill the running Claude process for a chat. Returns True if something was cancelled."""
    proc = _active_procs.get(chat_id)
    if proc and proc.returncode is None:
        proc.kill()
        return True
    return False


async def send_message(
    message: str,
    *,
    session_id: str | None = None,
    project_dir: str = ".",
    chat_id: int | None = None,
) -> ClaudeResponse:
    cmd = [
        "claude",
        "-p", message,
        "--output-format", "json",
        "--permission-mode", "dontAsk",
    ]
    if session_id:
        cmd.extend(["--resume", session_id])

    # Prepend chat_id so Claude can send live Telegram updates
    if chat_id is not None:
        cmd[2] = f"[chat_id={chat_id}] {message}"

    # Strip CLAUDECODE env var to allow nested subprocess invocation
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    runtime_file = None
    if chat_id is not None:
        runtime_file = _write_runtime_context(project_dir, chat_id)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=project_dir,
        env=env,
    )

    # Track the process so /cancel can kill it
    if chat_id is not None:
        _active_procs[chat_id] = proc

    try:
        stdout, stderr = await proc.communicate()
    finally:
        if chat_id is not None:
            _active_procs.pop(chat_id, None)
        if runtime_file is not None:
            try:
                runtime_file.unlink(missing_ok=True)
            except Exception:
                pass

    # Process was cancelled
    if proc.returncode is not None and proc.returncode < 0:
        return ClaudeResponse(text="cancelled", is_error=True)

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

    result_text = _sanitize_unicode(data.get("result", ""))

    _append_daily_log(project_dir, message, result_text)

    return ClaudeResponse(
        text=result_text,
        session_id=data.get("session_id"),
        cost_usd=data.get("cost_usd", 0.0),
        usage=data.get("usage"),
    )


def _append_daily_log(project_dir: str, user_msg: str, assistant_msg: str) -> None:
    try:
        log_path = Path(project_dir) / "memory" / "daily" / f"{date.today()}.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now().strftime("%H:%M")
        entry = f"\n## {now}\n\n**user:** {user_msg[:1500]}\n\n**bot:** {assistant_msg[:2000]}\n"
        with log_path.open("a") as f:
            f.write(entry)
    except Exception:
        logger.exception("Failed to write daily log")


def _write_runtime_context(project_dir: str, chat_id: int) -> Path:
    runtime_dir = Path(project_dir) / "runtime"
    runtime_dir.mkdir(exist_ok=True)
    p = runtime_dir / f"{chat_id}.json"
    p.write_text(json.dumps({"chat_id": chat_id, "started_at": time.time()}))
    return p
