# 🦞 lobster-bot

Your self-hosted AI assistant on Telegram. Powered by Claude Code.

It browses the web, remembers your conversations, and runs 24/7 on your own server. Two env vars and you're live.

## Quick Start

```bash
git clone https://github.com/aflekkas/lobster-bot.git
cd lobster-bot
pip install -r requirements.txt
```

Create a `.env`:

```
TELEGRAM_TOKEN=your-token-from-botfather
TELEGRAM_USER_IDS=your-telegram-user-id
```

Run:

```bash
source .env && python run.py
```

## Setup

1. Get a bot token — message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`
2. Get your user ID — message [@userinfobot](https://t.me/userinfobot)
3. Put both in `.env` and run

## What It Can Do

- **Web browsing** — navigates real websites via Playwright, not just search snippets
- **Persistent memory** — remembers facts about you and keeps daily logs
- **Conversations that stick** — sessions persist, so context carries across messages
- **Usage tracking** — know exactly what you're spending with `/usage`
- **Auto-updates** — pulls from git every 5 minutes, push a change and it goes live

## Deploy (VPS)

```bash
git clone https://github.com/aflekkas/lobster-bot.git ~/lobster-bot
cd ~/lobster-bot
pip install -r requirements.txt
npx playwright install --with-deps chromium
```

Create your `.env`, then set up the service:

```bash
cp deploy/systemd/lobster-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now lobster-bot
```

## Requirements

- Python 3.11+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- Node.js (for web browsing)

---

If this is useful to you, a ⭐ on the repo goes a long way.
