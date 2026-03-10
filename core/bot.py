import asyncio
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from telegram import BotCommand, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from core.bridge import cancel_chat, send_message
from core.commands import (
    cmd_agents,
    cmd_cancel,
    cmd_help,
    cmd_history,
    cmd_logs,
    cmd_memory,
    cmd_new,
    cmd_repo,
    cmd_restart,
    cmd_status,
    cmd_tools,
    handle_callback,
)
from core.config import load_config
from core.session import SessionManager

logger = logging.getLogger(__name__)

_config: dict = {}
_sessions: SessionManager | None = None
_project_dir: str = "."

# Daily cost alert thresholds (already warned)
_cost_alerts_sent: set[str] = set()
DAILY_BUDGET = 5.00  # USD — change this to your preferred daily limit
ALERT_THRESHOLDS = [0.5, 0.8, 1.0]  # 50%, 80%, 100%

# Per-chat message queue: if claude is busy, queue messages and feed them after
_chat_locks: dict[int, asyncio.Lock] = {}
_chat_queues: dict[int, list[str]] = {}


def _media_dir(chat_id: int) -> Path:
    d = Path(_project_dir) / "media" / str(chat_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_authorized(user_id: int, allowed: list[int]) -> bool:
    return user_id in allowed


def _auth_wrap(handler_fn, **extra_kw):
    """Wrap a command handler with auth check and inject project_dir/sessions."""
    async def wrapper(update: Update, context):
        if not is_authorized(update.effective_user.id, _config["telegram"]["allowed_users"]):
            await update.message.reply_text("You are not authorized to use this bot.")
            return
        await handler_fn(update, context, project_dir=_project_dir, sessions=_sessions, **extra_kw)
    return wrapper


async def _keep_typing(chat, stop_event: asyncio.Event) -> None:
    """Send typing indicator every 4s until stop_event is set."""
    while not stop_event.is_set():
        try:
            await chat.send_action(ChatAction.TYPING)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=4)
        except asyncio.TimeoutError:
            pass


async def _check_cost_alert(chat_id: int, bot) -> None:
    """Send cost alert if daily spending crosses a threshold."""
    usage = _sessions.get_usage()
    today_cost = usage["today"]["cost_usd"]
    today_key = datetime.now().strftime("%Y-%m-%d")

    for threshold in ALERT_THRESHOLDS:
        alert_key = f"{today_key}:{threshold}"
        if alert_key in _cost_alerts_sent:
            continue
        if today_cost >= DAILY_BUDGET * threshold:
            _cost_alerts_sent.add(alert_key)
            pct = int(threshold * 100)
            await bot.send_message(
                chat_id,
                f"cost alert: ${today_cost:.2f} spent today ({pct}% of ${DAILY_BUDGET:.2f} budget)"
            )


async def _process_and_respond(update: Update, text: str) -> None:
    """Send a message to claude. Queues if claude is already busy for this chat."""
    chat_id = update.effective_chat.id

    # Get or create per-chat lock
    if chat_id not in _chat_locks:
        _chat_locks[chat_id] = asyncio.Lock()
        _chat_queues[chat_id] = []

    lock = _chat_locks[chat_id]

    # If claude is already busy, queue the message and return
    if lock.locked():
        _chat_queues[chat_id].append(text)
        _sessions.log_chat(chat_id, "user", text)
        logger.info("Chat %s: queued message (claude busy), queue size: %d", chat_id, len(_chat_queues[chat_id]))
        return

    async with lock:
        await _send_to_claude(update, chat_id, text)

        # Process any queued messages that came in while claude was working
        while _chat_queues[chat_id]:
            queued = _chat_queues[chat_id]
            _chat_queues[chat_id] = []
            combined = "\n\n".join(queued)
            logger.info("Chat %s: processing %d queued message(s)", chat_id, len(queued))
            await _send_to_claude(update, chat_id, combined, already_logged=True)


async def _send_to_claude(update: Update, chat_id: int, text: str, already_logged: bool = False) -> None:
    """Actually send a message to claude and handle the response."""
    if not already_logged:
        _sessions.log_chat(chat_id, "user", text)

    session_id = _sessions.get_session(chat_id)

    # Keep typing indicator alive while claude works
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(update.message.chat, stop_typing))

    try:
        response = await send_message(
            text, session_id=session_id, project_dir=_project_dir, chat_id=chat_id,
        )
    finally:
        stop_typing.set()
        await typing_task

    # Don't send "cancelled" as a reply
    if response.is_error and response.text == "cancelled":
        _sessions.log_chat(chat_id, "assistant", "(cancelled)")
        return

    if response.session_id:
        _sessions.set_session(chat_id, response.session_id)

    usage = response.usage or {}
    _sessions.log_usage(
        chat_id,
        cost_usd=response.cost_usd,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
    )

    _sessions.log_chat(chat_id, "assistant", response.text)

    # Split long messages (Telegram 4096 char limit)
    reply_text = response.text
    while reply_text:
        chunk, reply_text = reply_text[:4096], reply_text[4096:]
        await update.message.reply_text(chunk)

    # Check cost alerts after responding
    await _check_cost_alert(chat_id, update.get_bot())


async def _save_file(update: Update, context) -> tuple[Path, str] | None:
    """Download a photo or document from Telegram. Returns (path, description)."""
    chat_id = update.effective_chat.id
    msg = update.message
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if msg.photo:
        photo = msg.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        name = f"photo_{ts}.jpg"
        desc = "photo"
    elif msg.document:
        doc = msg.document
        file = await context.bot.get_file(doc.file_id)
        name = doc.file_name or f"doc_{ts}"
        desc = f"document ({doc.mime_type or 'unknown type'})"
    elif msg.voice:
        voice = msg.voice
        file = await context.bot.get_file(voice.file_id)
        name = f"voice_{ts}.ogg"
        desc = f"voice message ({voice.duration}s)"
    elif msg.video:
        video = msg.video
        file = await context.bot.get_file(video.file_id)
        name = video.file_name or f"video_{ts}.mp4"
        desc = f"video ({video.duration}s)"
    elif msg.audio:
        audio = msg.audio
        file = await context.bot.get_file(audio.file_id)
        name = audio.file_name or f"audio_{ts}.mp3"
        desc = f"audio ({audio.duration}s)"
    else:
        return None

    path = _media_dir(chat_id) / name
    await file.download_to_drive(str(path))
    logger.info("Saved %s to %s", desc, path)
    return path, desc


async def handle_message(update: Update, context) -> None:
    if not is_authorized(update.effective_user.id, _config["telegram"]["allowed_users"]):
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    try:
        await _process_and_respond(update, update.message.text)
    except Exception:
        logger.exception("Error handling message from %s", update.effective_user.id)
        await update.message.reply_text("something broke on my end, check the logs")


async def handle_media(update: Update, context) -> None:
    if not is_authorized(update.effective_user.id, _config["telegram"]["allowed_users"]):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    try:
        result = await _save_file(update, context)
        if not result:
            await update.message.reply_text("Unsupported file type.")
            return

        path, desc = result
        caption = update.message.caption or ""

        prompt = f"The user sent a {desc}, saved at: {path}"
        if caption:
            prompt += f"\nCaption: {caption}"
        prompt += "\nPlease look at/process this file and respond."

        await _process_and_respond(update, prompt)
    except Exception:
        logger.exception("Error handling media from %s", update.effective_user.id)
        await update.message.reply_text("something broke on my end, check the logs")


async def _heartbeat(project_dir: str, interval: int = 300) -> None:
    """Pull from origin every 5 min."""
    while True:
        await asyncio.sleep(interval)
        try:
            result = await asyncio.to_thread(
                subprocess.run, ["git", "pull", "--ff-only", "origin", "main"],
                cwd=project_dir, capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and "Already up to date" not in result.stdout:
                logger.info("Heartbeat: pulled from origin")
            elif result.returncode != 0:
                logger.warning("Heartbeat: pull failed — %s", result.stderr.strip())
        except Exception:
            logger.exception("Heartbeat failed")


def main():
    global _config, _sessions, _project_dir

    _project_dir = str(Path(__file__).resolve().parent.parent)
    _config = load_config()
    _sessions = SessionManager(Path(_project_dir) / "sessions.db")

    (Path(_project_dir) / "memory" / "daily").mkdir(parents=True, exist_ok=True)

    token = _config["telegram"]["token"]
    app = Application.builder().token(token).concurrent_updates(True).build()

    allowed = _config["telegram"]["allowed_users"]

    async def post_init(application):
        application.create_task(_heartbeat(_project_dir))
        await application.bot.set_my_commands([
            BotCommand("new", "New conversation"),
            BotCommand("cancel", "Cancel current request"),
            BotCommand("history", "Recent conversations"),
            BotCommand("memory", "Browse memory files"),
            BotCommand("tools", "Browse tools"),
            BotCommand("agents", "List agents"),
            BotCommand("logs", "View logs"),
            BotCommand("status", "Session info"),
            BotCommand("repo", "Git repo info"),
            BotCommand("restart", "Restart the bot"),
            BotCommand("help", "Show commands"),
        ])
        for user_id in allowed:
            try:
                await application.bot.send_message(user_id, "i'm back online 🦞")
            except Exception:
                logger.warning("Could not send startup message to %s", user_id)
    app.post_init = post_init

    # Slash commands — all handled directly, no Claude
    app.add_handler(CommandHandler("new", _auth_wrap(cmd_new)))
    app.add_handler(CommandHandler("cancel", _auth_wrap(cmd_cancel)))
    app.add_handler(CommandHandler("history", _auth_wrap(cmd_history)))
    app.add_handler(CommandHandler("memory", _auth_wrap(cmd_memory)))
    app.add_handler(CommandHandler("tools", _auth_wrap(cmd_tools)))
    app.add_handler(CommandHandler("agents", _auth_wrap(cmd_agents)))
    app.add_handler(CommandHandler("logs", _auth_wrap(cmd_logs)))
    app.add_handler(CommandHandler("status", _auth_wrap(cmd_status)))
    app.add_handler(CommandHandler("repo", _auth_wrap(cmd_repo)))
    app.add_handler(CommandHandler("restart", _auth_wrap(cmd_restart)))
    app.add_handler(CommandHandler("help", _auth_wrap(cmd_help)))
    app.add_handler(CommandHandler("start", _auth_wrap(cmd_help)))

    # Inline keyboard callbacks
    async def _cb_handler(update, context):
        await handle_callback(update, context, _project_dir, allowed, sessions=_sessions)
    app.add_handler(CallbackQueryHandler(_cb_handler))

    # Regular messages → Claude
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(
        filters.PHOTO | filters.Document.ALL | filters.VOICE | filters.VIDEO | filters.AUDIO,
        handle_media,
    ))

    logger.info("Bot starting — allowed users: %s", allowed)
    app.run_polling()
