import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass

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

    return ClaudeResponse(
        text=result_text,
        session_id=data.get("session_id"),
        cost_usd=data.get("cost_usd", 0.0),
        usage=data.get("usage"),
    )
