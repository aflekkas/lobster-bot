"""Lightweight cron scheduler — runs as an asyncio task alongside the bot."""
import asyncio
import json
import logging
import fcntl
from datetime import datetime
from pathlib import Path

from croniter import croniter

from core.bridge import send_message

logger = logging.getLogger(__name__)

LOCK_PATH = Path("/tmp/lobster-bot.lock")
SCHEDULES_PATH = Path("user/schedules.json")
STATE_PATH = Path("user/.schedule_state.json")
CHECK_INTERVAL = 60  # seconds


def acquire_lock() -> int | None:
    """Try to acquire the file lock. Returns fd on success, None if already locked."""
    try:
        fd = open(LOCK_PATH, "w")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except (OSError, IOError):
        return None


def release_lock(fd) -> None:
    """Release the file lock."""
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()
    except Exception:
        pass


def _load_schedules(project_dir: str) -> list[dict]:
    path = Path(project_dir) / SCHEDULES_PATH
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return [s for s in data if s.get("enabled", True)]
    except Exception:
        logger.exception("Failed to load schedules")
        return []


def _load_state(project_dir: str) -> dict:
    path = Path(project_dir) / STATE_PATH
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _save_state(project_dir: str, state: dict) -> None:
    path = Path(project_dir) / STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def is_due(schedule: dict, state: dict) -> bool:
    """Check if a schedule is due to run right now."""
    name = schedule["name"]
    cron_expr = schedule["cron"]
    last_run = state.get(name)

    now = datetime.now()

    if last_run:
        last_dt = datetime.fromisoformat(last_run)
    else:
        # Never run before — use 1 minute ago as baseline
        last_dt = now.replace(second=0, microsecond=0)
        from datetime import timedelta
        last_dt = last_dt - timedelta(minutes=1)

    cron = croniter(cron_expr, last_dt)
    next_run = cron.get_next(datetime)

    return next_run <= now


def get_next_run(schedule: dict, state: dict) -> datetime:
    """Get the next run time for a schedule."""
    name = schedule["name"]
    cron_expr = schedule["cron"]
    last_run = state.get(name)

    if last_run:
        base = datetime.fromisoformat(last_run)
    else:
        base = datetime.now()

    cron = croniter(cron_expr, base)
    return cron.get_next(datetime)


async def _run_task(schedule: dict, project_dir: str, bot) -> None:
    """Execute a scheduled task via the bridge and send the result."""
    name = schedule["name"]
    chat_id = int(schedule["chat_id"])
    prompt = schedule["prompt"]

    logger.info("Scheduler: running task '%s' for chat %s", name, chat_id)

    lock_fd = acquire_lock()
    if lock_fd is None:
        logger.info("Scheduler: skipping '%s' — Claude is busy (locked)", name)
        return

    try:
        response = await send_message(
            f"[scheduled:{name}] {prompt}",
            project_dir=project_dir,
            chat_id=chat_id,
        )

        if response.is_error:
            logger.warning("Scheduler: task '%s' failed — %s", name, response.text)
            return

        # Send result to the user
        text = response.text
        while text:
            chunk, text = text[:4096], text[4096:]
            await bot.send_message(chat_id, chunk)

    except Exception:
        logger.exception("Scheduler: task '%s' crashed", name)
    finally:
        release_lock(lock_fd)


async def scheduler_loop(project_dir: str, bot) -> None:
    """Main scheduler loop — checks for due tasks every CHECK_INTERVAL seconds."""
    logger.info("Scheduler: started (checking every %ds)", CHECK_INTERVAL)

    while True:
        await asyncio.sleep(CHECK_INTERVAL)

        try:
            schedules = _load_schedules(project_dir)
            if not schedules:
                continue

            state = _load_state(project_dir)

            for schedule in schedules:
                if not is_due(schedule, state):
                    continue

                await _run_task(schedule, project_dir, bot)

                # Mark as run
                state[schedule["name"]] = datetime.now().isoformat()
                _save_state(project_dir, state)

        except Exception:
            logger.exception("Scheduler: loop error")


def list_schedules(project_dir: str) -> str:
    """Return a human-readable list of all schedules and their next run times."""
    path = Path(project_dir) / SCHEDULES_PATH
    if not path.exists():
        return "no schedules configured\n\nedit user/schedules.json to add some"

    try:
        schedules = json.loads(path.read_text())
    except Exception:
        return "failed to read schedules.json"

    if not schedules:
        return "no schedules configured\n\nedit user/schedules.json to add some"

    state = _load_state(project_dir)
    lines = []

    for s in schedules:
        name = s.get("name", "unnamed")
        enabled = s.get("enabled", True)
        status = "on" if enabled else "off"
        cron_expr = s.get("cron", "?")

        if enabled:
            try:
                next_dt = get_next_run(s, state)
                next_str = next_dt.strftime("%b %d %H:%M")
            except Exception:
                next_str = "invalid cron"
        else:
            next_str = "disabled"

        lines.append(f"{name} [{status}] — {cron_expr}\n  next: {next_str}")

    return "\n\n".join(lines)
