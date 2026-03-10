#!/bin/bash
# Send a Telegram message. Usage: send.sh <chat_id> <message>
# Token is read from TELEGRAM_TOKEN env var or .env file.

CHAT_ID="$1"
MESSAGE="$2"

if [ -z "$CHAT_ID" ] || [ -z "$MESSAGE" ]; then
    echo "Usage: send.sh <chat_id> <message>"
    exit 1
fi

# Load token from env or .env
TOKEN="${TELEGRAM_TOKEN}"
if [ -z "$TOKEN" ]; then
    ENV_FILE="$(dirname "$0")/../../.env"
    if [ -f "$ENV_FILE" ]; then
        TOKEN=$(grep '^TELEGRAM_TOKEN=' "$ENV_FILE" | cut -d'=' -f2)
    fi
fi

if [ -z "$TOKEN" ]; then
    echo "Error: TELEGRAM_TOKEN not set"
    exit 1
fi

curl -s -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
    -d chat_id="$CHAT_ID" \
    -d text="$MESSAGE" \
    > /dev/null 2>&1

echo "sent"
