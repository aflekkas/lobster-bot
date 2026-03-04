import asyncio
import logging
import shutil
import subprocess
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from core.bridge import send_message, ClaudeResponse
from core.config import load_config
from core.formatter import format_for_telegram, plain_text_fallback
from core.media import process_voice, process_photo, process_document, cleanup_old_files
from core.queue import MessageRouter, ProcessLock
from core.session import SessionManager

logger = logging.getLogger(__name__)

# Module-level state, initialized in main()
_config: dict = {}
_sessions: SessionManager | None = None
_project_dir: str = "."
_router: MessageRouter | None = None


def is_authorized(user_id: int, allowed: list[int]) -> bool:
    return user_id in allowed


async def _send_response(chat_id: int, text: str, context) -> None:
    """Send a formatted response, falling back to plain text if formatting fails."""
    chunks = format_for_telegram(text)
    for chunk in chunks:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception:
            # Fall back to plain text if MarkdownV2 parsing fails
            plain_chunks = plain_text_fallback(text)
            for plain in plain_chunks:
                await context.bot.send_message(chat_id=chat_id, text=plain)
            break


async def _process_and_respond(chat_id: int, text: str, context) -> None:
    """Process a message through Claude and send the response."""
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    session_id = _sessions.get_session(chat_id)
    response = await send_message(
        text,
        session_id=session_id,
        project_dir=_project_dir,
    )

    if response.session_id:
        _sessions.set_session(chat_id, response.session_id)

    # Track usage
    usage = response.usage or {}
    _sessions.log_usage(
        chat_id,
        cost_usd=response.cost_usd,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
    )

    await _send_response(chat_id, response.text, context)


async def handle_message(update: Update, context) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_authorized(user_id, _config["telegram"]["allowed_users"]):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    async def handler(cid: int, text: str):
        await _process_and_respond(cid, text, context)

    await _router.enqueue(chat_id, update.message.text, handler)


async def handle_voice(update: Update, context) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_authorized(user_id, _config["telegram"]["allowed_users"]):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    transcript = await process_voice(update.message.voice)

    async def handler(cid: int, text: str):
        await _process_and_respond(cid, text, context)

    await _router.enqueue(chat_id, f"[Voice message]: {transcript}", handler)


async def handle_photo(update: Update, context) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_authorized(user_id, _config["telegram"]["allowed_users"]):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    photo = update.message.photo[-1]  # Highest resolution
    prompt, path = await process_photo(photo, caption=update.message.caption or "")

    async def handler(cid: int, text: str):
        await _process_and_respond(cid, text, context)

    await _router.enqueue(chat_id, prompt, handler)


async def handle_document(update: Update, context) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_authorized(user_id, _config["telegram"]["allowed_users"]):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    prompt, path = await process_document(
        update.message.document, caption=update.message.caption or ""
    )

    async def handler(cid: int, text: str):
        await _process_and_respond(cid, text, context)

    await _router.enqueue(chat_id, prompt, handler)


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


async def handle_facts(update: Update, context) -> None:
    user_id = update.effective_user.id

    if not is_authorized(user_id, _config["telegram"]["allowed_users"]):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    facts_path = Path(_project_dir) / "memory" / "facts.md"
    if facts_path.exists():
        content = facts_path.read_text().strip()
        await update.message.reply_text(content or "No facts saved yet.")
    else:
        await update.message.reply_text("No facts file found.")


async def handle_today(update: Update, context) -> None:
    user_id = update.effective_user.id

    if not is_authorized(user_id, _config["telegram"]["allowed_users"]):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    from datetime import date
    today_path = Path(_project_dir) / "memory" / "daily" / f"{date.today()}.md"
    if today_path.exists():
        content = today_path.read_text().strip()
        await update.message.reply_text(content or "Nothing logged today yet.")
    else:
        await update.message.reply_text("No log for today yet.")


async def handle_usage(update: Update, context) -> None:
    user_id = update.effective_user.id

    if not is_authorized(user_id, _config["telegram"]["allowed_users"]):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    usage = _sessions.get_usage()
    today = usage["today"]
    total = usage["total"]

    def _fmt_tokens(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}k"
        return str(n)

    lines = [
        "📊 Usage Stats",
        "",
        "Today:",
        f"  ${today['cost_usd']:.4f} spent",
        f"  {today['messages']} messages",
        f"  {_fmt_tokens(today['input_tokens'])} in / {_fmt_tokens(today['output_tokens'])} out",
        "",
        "All time:",
        f"  ${total['cost_usd']:.4f} spent",
        f"  {total['messages']} messages",
        f"  {_fmt_tokens(total['input_tokens'])} in / {_fmt_tokens(total['output_tokens'])} out",
    ]
    await update.message.reply_text("\n".join(lines))


async def handle_help(update: Update, context) -> None:
    await update.message.reply_text(
        "/new — Start a new conversation\n"
        "/status — Session info\n"
        "/usage — Usage stats and costs\n"
        "/facts — Show saved facts about you\n"
        "/today — Show today's daily log\n"
        "/help — Show this message"
    )


async def _heartbeat(project_dir: str, interval: int = 300) -> None:
    """Periodically pull upstream changes. Runs every `interval` seconds (default 5 min).

    Tries upstream remote first (fork workflow), falls back to origin.
    If fast-forward fails (merge conflict), aborts and logs to memory/merge-conflicts.md.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            # Determine which remote to pull from
            remotes_result = await asyncio.to_thread(
                subprocess.run,
                ["git", "remote"],
                cwd=project_dir,
                capture_output=True, text=True, timeout=10,
            )
            remotes = remotes_result.stdout.strip().split("\n")
            remote = "upstream" if "upstream" in remotes else "origin"

            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "pull", "--ff-only", remote, "main"],
                cwd=project_dir,
                capture_output=True, text=True, timeout=30,
            )

            if result.returncode == 0 and "Already up to date" not in result.stdout:
                logger.info("Heartbeat: pulled from %s — %s", remote, result.stdout.strip())
            elif result.returncode != 0:
                # Fast-forward failed — likely a merge conflict
                logger.warning("Heartbeat: pull from %s failed — %s", remote, result.stderr.strip())

                # Log conflict for user review
                from datetime import datetime
                conflict_file = Path(project_dir) / "memory" / "merge-conflicts.md"
                conflict_file.parent.mkdir(parents=True, exist_ok=True)
                with open(conflict_file, "a") as f:
                    f.write(f"\n## {datetime.now().isoformat()}\n")
                    f.write(f"Failed to pull from `{remote}` (fast-forward only).\n")
                    f.write(f"```\n{result.stderr.strip()}\n```\n")
                    f.write("**Action needed:** manually resolve in the instance directory.\n")

                logger.warning("Heartbeat: conflict logged to memory/merge-conflicts.md")
        except Exception:
            logger.exception("Heartbeat: pull failed")


def _setup_data_dir(source_dir: Path, data_dir: Path) -> None:
    """Copy Claude config files into a separate data directory."""
    data_dir.mkdir(parents=True, exist_ok=True)

    # Copy Claude config files (these define the bot's personality and permissions)
    for item in ["CLAUDE.md", ".claude", ".mcp.json"]:
        src = source_dir / item
        dst = data_dir / item
        if src.exists() and not dst.exists():
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

    logger.info("Data directory: %s", data_dir)


def main(data_dir: str | None = None):
    global _config, _sessions, _project_dir, _router

    source_dir = Path(__file__).resolve().parent.parent
    _config = load_config()

    # If data_dir is set, Claude Code works in a separate directory
    # so it doesn't modify the source repo
    if data_dir:
        _project_dir = str(Path(data_dir).resolve())
        _setup_data_dir(source_dir, Path(_project_dir))
    else:
        _project_dir = str(source_dir)

    _sessions = SessionManager(Path(_project_dir) / "sessions.db")

    lock = ProcessLock(Path(_project_dir) / ".claude_lock")
    _router = MessageRouter(process_lock=lock)

    # Ensure memory directories exist
    for subdir in ["daily", "chats"]:
        (Path(_project_dir) / "memory" / subdir).mkdir(parents=True, exist_ok=True)

    app = Application.builder().token(_config["telegram"]["token"]).build()

    # Start heartbeat (auto-pull upstream every 5 min)
    async def post_init(application):
        application.create_task(_heartbeat(_project_dir))

    app.post_init = post_init

    # Commands
    app.add_handler(CommandHandler("new", handle_new))
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CommandHandler("usage", handle_usage))
    app.add_handler(CommandHandler("facts", handle_facts))
    app.add_handler(CommandHandler("today", handle_today))
    app.add_handler(CommandHandler("help", handle_help))
    app.add_handler(CommandHandler("start", handle_help))

    # Message types
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
