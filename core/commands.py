"""Telegram slash commands — handled directly, no Claude involved."""
import logging
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

logger = logging.getLogger(__name__)


def _btn(text, data):
    return InlineKeyboardButton(text, callback_data=data)


def _truncate(text, limit=4000):
    if len(text) > limit:
        return text[:limit] + "\n...(truncated)"
    return text


# -- /memory ------------------------------------------------------------------

async def cmd_memory(update, context, project_dir, **kw):
    kb = InlineKeyboardMarkup([
        [_btn("Facts", "mem:facts")],
        [_btn("Today's log", "mem:today"), _btn("Yesterday", "mem:yesterday")],
        [_btn("List daily logs", "mem:list")],
    ])
    await update.message.reply_text("Memory", reply_markup=kb)


async def cb_memory(query, data, project_dir, **kw):
    mem = Path(project_dir) / "memory"

    if data == "mem:facts":
        path = mem / "facts.md"
        text = path.read_text().strip() if path.exists() else "no facts saved yet"
    elif data == "mem:today":
        path = mem / "daily" / f"{date.today()}.md"
        text = path.read_text().strip() if path.exists() else "no log for today yet"
    elif data == "mem:yesterday":
        path = mem / "daily" / f"{date.today() - timedelta(days=1)}.md"
        text = path.read_text().strip() if path.exists() else "no log for yesterday"
    elif data == "mem:list":
        daily = mem / "daily"
        if daily.exists():
            files = sorted(daily.glob("*.md"), reverse=True)[:10]
            text = "\n".join(f.stem for f in files) if files else "no daily logs yet"
        else:
            text = "no daily logs yet"
    else:
        text = "unknown"

    await query.edit_message_text(_truncate(text))


# -- /tools -------------------------------------------------------------------

async def cmd_tools(update, context, project_dir, **kw):
    tools_dir = Path(project_dir) / "tools"
    if not tools_dir.exists():
        await update.message.reply_text("no tools directory")
        return

    dirs = sorted(d.name for d in tools_dir.iterdir() if d.is_dir())
    if not dirs:
        await update.message.reply_text("no tools found")
        return

    rows = [[_btn(d, f"tool:{d}")] for d in dirs]
    await update.message.reply_text("Tools", reply_markup=InlineKeyboardMarkup(rows))


async def cb_tools(query, data, project_dir, **kw):
    tool_name = data.split(":", 1)[1]

    if tool_name.endswith(":readme"):
        tool_name = tool_name.replace(":readme", "")
        readme = Path(project_dir) / "tools" / tool_name / "README.md"
        text = readme.read_text().strip() if readme.exists() else "no README found"
        await query.edit_message_text(_truncate(text))
        return

    if tool_name.endswith(":scripts"):
        tool_name = tool_name.replace(":scripts", "")
        tool_dir = Path(project_dir) / "tools" / tool_name
        scripts = sorted(f.name for f in tool_dir.glob("*.js")) + sorted(f.name for f in tool_dir.glob("*.py"))
        text = "\n".join(scripts) if scripts else "no scripts found"
        await query.edit_message_text(text)
        return

    tool_dir = Path(project_dir) / "tools" / tool_name
    scripts = sorted(f.name for f in tool_dir.glob("*.js")) + sorted(f.name for f in tool_dir.glob("*.py"))
    has_readme = (tool_dir / "README.md").exists()

    text = f"{tool_name}\n{len(scripts)} scripts"
    buttons = []
    if has_readme:
        buttons.append(_btn("README", f"tool:{tool_name}:readme"))
    buttons.append(_btn("List scripts", f"tool:{tool_name}:scripts"))

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([buttons]))


# -- /logs --------------------------------------------------------------------

async def cmd_logs(update, context, project_dir, **kw):
    log_dir = Path(project_dir) / "logs"
    log_files = sorted(log_dir.glob("*.log")) if log_dir.exists() else []

    if not log_files:
        await update.message.reply_text("no logs yet")
        return

    rows = [[_btn(f.name, f"log:{f.stem}")] for f in log_files]
    rows.append([_btn("Errors only", "log:errors")])
    await update.message.reply_text("Logs", reply_markup=InlineKeyboardMarkup(rows))


async def cb_logs(query, data, project_dir, **kw):
    log_dir = Path(project_dir) / "logs"
    key = data.split(":", 1)[1]

    if key == "errors":
        bot_log = log_dir / "bot.log"
        if not bot_log.exists():
            await query.edit_message_text("no logs yet")
            return
        lines = [l for l in bot_log.read_text().splitlines() if "ERROR" in l or "WARNING" in l]
        text = "\n".join(lines[-30:]) if lines else "no errors found"
    else:
        log_path = log_dir / f"{key}.log"
        if not log_path.exists():
            await query.edit_message_text(f"{key}.log not found")
            return
        lines = log_path.read_text().strip().splitlines()
        text = "\n".join(lines[-30:])

    if len(text) > 4000:
        text = text[-4000:]
    await query.edit_message_text(text or "empty log")


# -- /agents ------------------------------------------------------------------

async def cmd_agents(update, context, project_dir, **kw):
    agents_dir = Path(project_dir) / ".claude" / "agents"
    if not agents_dir.exists():
        await update.message.reply_text("no agents configured")
        return

    agent_files = sorted(agents_dir.glob("*.md"))
    if not agent_files:
        await update.message.reply_text("no agents found")
        return

    rows = []
    for f in agent_files:
        name = f.stem
        desc = _agent_desc(f)
        rows.append([_btn(f"{name} — {desc[:30]}", f"agent:{name}")])
    await update.message.reply_text("Agents", reply_markup=InlineKeyboardMarkup(rows))


def _agent_desc(path):
    in_fm = False
    for line in path.read_text().splitlines():
        if line.strip() == "---":
            in_fm = not in_fm
            continue
        if in_fm or not line.strip():
            continue
        return line.strip().lstrip("# ")
    return "no description"


async def cb_agents(query, data, project_dir, **kw):
    name = data.split(":", 1)[1]
    path = Path(project_dir) / ".claude" / "agents" / f"{name}.md"
    if not path.exists():
        await query.edit_message_text(f"agent {name} not found")
        return
    text = path.read_text().strip()
    await query.edit_message_text(_truncate(text))


# -- /cancel ------------------------------------------------------------------

async def cmd_cancel(update, context, **kw):
    from core.bridge import cancel_chat
    chat_id = update.effective_chat.id
    if cancel_chat(chat_id):
        await update.message.reply_text("cancelled")
    else:
        await update.message.reply_text("nothing running to cancel")


# -- /history -----------------------------------------------------------------

async def cmd_history(update, context, sessions, **kw):
    kb = InlineKeyboardMarkup([
        [_btn("Today", "hist:today"), _btn("Yesterday", "hist:yesterday")],
        [_btn("Last 7 days", "hist:week")],
        [_btn("Past sessions", "hist:sessions")],
    ])
    await update.message.reply_text("History", reply_markup=kb)


async def cb_history(query, data, project_dir, sessions=None, **kw):
    if sessions is None:
        await query.edit_message_text("session manager not available")
        return

    chat_id = query.from_user.id

    if data == "hist:sessions":
        history = sessions.get_history(chat_id)
        if not history:
            await query.edit_message_text("no past sessions")
            return
        rows = []
        for h in history[:5]:
            ts = datetime.fromtimestamp(h["created_at"]).strftime("%m/%d %H:%M")
            rows.append([_btn(f"Resume {ts}", f"hist:resume:{h['session_id']}")])
        await query.edit_message_text(
            "Past sessions (tap to resume):",
            reply_markup=InlineKeyboardMarkup(rows) if rows else None,
        )
        return

    if data.startswith("hist:resume:"):
        session_id = data.replace("hist:resume:", "")
        sessions.set_session(chat_id, session_id)
        await query.edit_message_text(f"resumed session {session_id[:8]}...")
        return

    # Chat log history
    from datetime import date as dt_date

    if data == "hist:today":
        start = datetime.combine(dt_date.today(), datetime.min.time()).timestamp()
        label = "Today"
    elif data == "hist:yesterday":
        yday = dt_date.today() - timedelta(days=1)
        start = datetime.combine(yday, datetime.min.time()).timestamp()
        label = "Yesterday"
    elif data == "hist:week":
        start = datetime.combine(dt_date.today() - timedelta(days=7), datetime.min.time()).timestamp()
        label = "Last 7 days"
    else:
        await query.edit_message_text("unknown")
        return

    rows = sessions._db.execute(
        "SELECT timestamp, role, text FROM chat_log WHERE chat_id = ? AND timestamp >= ? ORDER BY timestamp DESC LIMIT 20",
        (chat_id, start),
    ).fetchall()

    if not rows:
        await query.edit_message_text(f"{label}: no messages")
        return

    lines = []
    for r in reversed(rows):
        ts = datetime.fromtimestamp(r["timestamp"]).strftime("%H:%M")
        role = "you" if r["role"] == "user" else "bot"
        msg = r["text"][:80]
        lines.append(f"[{ts}] {role}: {msg}")

    text = f"{label}\n\n" + "\n".join(lines)
    await query.edit_message_text(_truncate(text))


# -- /status ------------------------------------------------------------------

async def cmd_status(update, context, sessions, **kw):
    sid = sessions.get_session(update.effective_chat.id)
    await update.message.reply_text(f"Session: {sid or 'none'}")


# -- /new ---------------------------------------------------------------------

async def cmd_new(update, context, sessions, **kw):
    sessions.clear_session(update.effective_chat.id)
    await update.message.reply_text("Started a new conversation.")


# -- /repo --------------------------------------------------------------------

async def cmd_repo(update, context, project_dir, **kw):
    kb = InlineKeyboardMarkup([
        [_btn("Status", "repo:status"), _btn("Recent commits", "repo:log")],
        [_btn("Branch", "repo:branch"), _btn("Remotes", "repo:remote")],
        [_btn("Diff (staged)", "repo:diff")],
    ])
    await update.message.reply_text("Repo", reply_markup=kb)


async def cb_repo(query, data, project_dir, **kw):
    key = data.split(":", 1)[1]

    cmd_map = {
        "status": ["git", "status", "--short"],
        "log": ["git", "log", "--oneline", "-15"],
        "branch": ["git", "branch", "-a"],
        "remote": ["git", "remote", "-v"],
        "diff": ["git", "diff", "--cached", "--stat"],
    }

    cmd = cmd_map.get(key)
    if not cmd:
        await query.edit_message_text("unknown")
        return

    try:
        result = subprocess.run(
            cmd, cwd=project_dir, capture_output=True, text=True, timeout=10,
        )
        text = result.stdout.strip() or result.stderr.strip() or "nothing to show"
    except Exception as e:
        text = f"error: {e}"

    await query.edit_message_text(_truncate(text))


# -- /restart -----------------------------------------------------------------

async def cmd_restart(update, context, **kw):
    await update.message.reply_text("restarting...")
    logger.info("Restart requested by user %s", update.effective_user.id)
    subprocess.Popen(["systemctl", "restart", "lobster-bot"])


# -- /help --------------------------------------------------------------------

async def cmd_help(update, context, **kw):
    await update.message.reply_text(
        "/new — New conversation\n"
        "/cancel — Cancel current request\n"
        "/history — Recent conversations\n"
        "/memory — Browse memory files\n"
        "/tools — Browse tools\n"
        "/agents — List agents\n"
        "/logs — View logs\n"
        "/status — Session info\n"
        "/repo — Git repo info\n"
        "/restart — Restart the bot\n"
        "/help — This message"
    )


# -- Callback router ----------------------------------------------------------

CALLBACK_HANDLERS = {
    "mem:": cb_memory,
    "tool:": cb_tools,
    "log:": cb_logs,
    "agent:": cb_agents,
    "hist:": cb_history,
    "repo:": cb_repo,
}


async def handle_callback(update, context, project_dir, allowed_users, sessions=None):
    query = update.callback_query
    if query.from_user.id not in allowed_users:
        await query.answer("not authorized")
        return

    await query.answer()
    data = query.data

    for prefix, handler in CALLBACK_HANDLERS.items():
        if data.startswith(prefix):
            await handler(query, data, project_dir, sessions=sessions)
            return

    await query.edit_message_text("unknown action")
