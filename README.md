# 🦞 lobster-bot

Your self-hosted AI assistant on Telegram. Powered by Claude Code.

It searches the web, remembers your conversations, handles photos and documents, and runs 24/7 on your own server.

## What It Can Do

- **Web search** — finds and summarizes info from the web
- **Photos & documents** — send images, PDFs, files — it can see and read them
- **Persistent memory** — remembers facts about you and keeps daily logs
- **Conversations that stick** — sessions persist, context carries across messages
- **Live progress updates** — sends you updates while working on long tasks
- **Message queuing** — send multiple messages while it's thinking, they all get processed
- **Cost alerts** — warns you at 50%, 80%, 100% of your daily budget
- **Auto-updates** — pulls from git every 5 minutes, push a change and it goes live
- **Autosync** — automatically commits and pushes local changes (via cron)
- **Startup notification** — messages you when it comes back online

## Full Setup Guide

This is a step-by-step guide. If you're an AI agent setting this up for your user, follow every step.

### 1. Get a Telegram Bot Token

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Choose a name (e.g. "My Assistant") and a username (e.g. `my_lobster_bot`)
4. BotFather gives you a token like `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz` — save this

### 2. Get Your Telegram User ID

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. It replies with your user ID — a number like `8574346253` — save this

### 3. Get a VPS

Any Ubuntu VPS works. Recommended: [Hostinger](https://www.hostinger.com/vps-hosting) ($4-6/mo), [DigitalOcean](https://www.digitalocean.com/) ($6/mo), or any provider with Ubuntu 22.04+.

You need:
- Ubuntu 22.04 or newer
- At least 1 GB RAM
- SSH access (root or sudo)

### 4. SSH Into Your Server

```bash
ssh root@your-server-ip
```

Enter your password when prompted. If this is your first time connecting, type `yes` to accept the fingerprint.

### 5. Run the Installer

```bash
curl -sSL https://raw.githubusercontent.com/agent-lab-skool/lobster-bot/main/deploy/install.sh | bash
```

This automatically installs:
- Python 3 + pip (if missing)
- Node.js (if missing)
- Claude Code CLI
- Clones the repo to `~/lobster-bot`
- Installs Python dependencies
- Creates a `.env` template
- Sets up the systemd service

### 6. Authenticate Claude Code

This is a one-time step. Run:

```bash
claude
```

It will show a URL — open it in your browser and log in with your Anthropic account. Once authenticated, type `/exit` to quit Claude.

**Note:** If the OAuth gives an error, try again — it can be flaky. Or use an API key instead:

```bash
claude config set apiKey YOUR_ANTHROPIC_API_KEY
```

(Get an API key from https://console.anthropic.com/settings/keys)

### 7. Set Your Secrets

```bash
nano ~/lobster-bot/.env
```

Replace the placeholder values with your real token and user ID:

```
TELEGRAM_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_USER_IDS=8574346253
```

Multiple users? Comma-separate them: `TELEGRAM_USER_IDS=111,222,333`

Save: `Ctrl+O`, `Enter`, `Ctrl+X`

### 8. Start the Bot

```bash
systemctl enable --now lobster-bot
```

You should get a "i'm back online 🦞" message on Telegram. Send it a message to test.

### 9. Set Up Autosync (Optional)

Autosync commits and pushes any local changes every 5 minutes — keeps your memory, config, and customizations backed up to git.

```bash
crontab -e
```

Add this line:

```
*/5 * * * * /root/lobster-bot/deploy/autosync.sh >> /root/lobster-bot/logs/autosync.log 2>&1
```

### 10. You're Done

The bot:
- Runs 24/7 as a systemd service
- Restarts automatically if it crashes or the server reboots
- Auto-pulls updates from git every 5 minutes
- Logs everything to `logs/bot.log`

## Using the Bot

Just message it on Telegram like you'd text a friend. It's Claude — it can do anything Claude can do, but through Telegram.

**Things you can do:**
- Ask it anything — it searches the web if it doesn't know
- Send photos — it can see and describe images, read text in screenshots
- Send documents — PDFs, code files, spreadsheets, whatever
- Send voice messages — it receives the audio file
- Ask it to remember things — it saves facts about you between conversations
- Ask it to run commands on your server — it has full root access
- Paste API keys or credentials — it'll save them wherever you need
- Ask it to install software, edit configs, set up services on your VPS

**Commands:**
- `/new` — Start a fresh conversation (clears session context)
- `/cancel` — Stop a running request
- `/history` — Browse recent conversations and resume past sessions
- `/memory` — View saved facts and daily logs
- `/tools` — Browse installed tools
- `/agents` — List configured agents
- `/logs` — View bot logs and filter errors
- `/status` — Check current session ID
- `/repo` — Git repo info (status, commits, branches)
- `/restart` — Restart the bot service
- `/help` — List commands

**Tips:**
- If the bot seems confused or stuck on old context, send `/new` to reset
- Send `/cancel` if a request is taking too long or you changed your mind
- Long responses get split into chunks automatically (Telegram limit)
- The bot remembers you across conversations via `memory/facts.md`
- It keeps a daily log at `memory/daily/` — you can ask "what did we talk about yesterday?"
- If you send messages while it's busy, they queue up and get processed next

## Debugging

### Check if the bot is running

```bash
systemctl status lobster-bot
```

You want to see `active (running)`. If it says `failed`, check the logs.

### View logs

```bash
# Live stream
journalctl -u lobster-bot -f

# Or read the log file directly
tail -100 ~/lobster-bot/logs/bot.log
```

### View recent logs

```bash
journalctl -u lobster-bot --since "5 minutes ago"
```

### Common issues

**"Failed to parse Claude response"**
Claude Code returned an error. Check the full log with `journalctl`. Common causes:
- Claude Code not authenticated — run `claude` to login
- Permission denied — check `.claude/settings.json`
- Network issue — check internet connectivity

**Bot not responding at all**
```bash
systemctl status lobster-bot
```
If it's not running:
```bash
systemctl restart lobster-bot
journalctl -u lobster-bot --since "1 minute ago"
```

**"Not authorized" reply**
Your Telegram user ID in `.env` doesn't match. Check it:
```bash
cat ~/lobster-bot/.env
```
Compare with what [@userinfobot](https://t.me/userinfobot) says.

**Bot takes too long to respond**
Claude Code is running in the background — give it 10-30 seconds. If it's consistently slow, check server resources:
```bash
htop
```

**OAuth "Invalid code_challenge_method" error**
Known issue with Claude Code OAuth. Try:
1. Run `claude` again — sometimes it works on retry
2. Use API key instead: `claude config set apiKey YOUR_KEY`

### Restart the bot

```bash
systemctl restart lobster-bot
```

### Stop the bot

```bash
systemctl stop lobster-bot
```

### Update to latest version

```bash
cd ~/lobster-bot && git pull && systemctl restart lobster-bot
```

Or just wait — the bot auto-pulls every 5 minutes.

### Check disk usage

```bash
du -sh ~/lobster-bot/media/
du -sh ~/lobster-bot/memory/
```

### Clear media files

```bash
rm -rf ~/lobster-bot/media/*
```

Or ask the bot to do it via Telegram — it has permission.

## Architecture

```
Telegram → python-telegram-bot → claude -p --output-format json → Telegram
```

- `core/bot.py` — Telegram handlers, typing indicator, message queuing, cost alerts
- `core/bridge.py` — Claude Code subprocess wrapper with cancel support
- `core/commands.py` — Slash commands with inline keyboard UI
- `core/session.py` — SQLite session, usage, and chat log tracking
- `core/config.py` — Loads env vars
- `run.py` — Entry point with rotating log file setup
- `.claude/settings.json` — Tool permissions (allow/deny)
- `CLAUDE.md` — Bot personality and behavior instructions
- `tools/telegram/send.sh` — Send live updates to Telegram from Claude
- `deploy/autosync.sh` — Cron-based git commit + push
- `memory/` — Facts, daily logs (written by the bot)
- `media/{chat_id}/` — Downloaded photos, docs, voice messages

## Customization

### Change the bot's personality

Edit `CLAUDE.md` — this is the system prompt Claude sees every conversation.

### Change what the bot can do

Edit `.claude/settings.json` — add or remove tools from the allow/deny lists.

### Change the daily cost budget

Edit `DAILY_BUDGET` in `core/bot.py` (default: $5.00/day).

### Add more users

Edit `.env` and add comma-separated user IDs:

```
TELEGRAM_USER_IDS=111,222,333
```

Then restart: `systemctl restart lobster-bot`

---

Built by [Agent Lab](https://skool.com/agent-lab) — a community where we teach people how to build with AI. Come hang out.

If this is useful to you, a ⭐ on the repo goes a long way.
