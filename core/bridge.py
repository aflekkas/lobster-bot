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
        "--permission-mode", "allowedTools",
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
