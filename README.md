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
