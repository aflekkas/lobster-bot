#!/usr/bin/env bash
# PostToolUse hook — sends a live Telegram notification when Claude uses a tool.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RUNTIME_DIR="$PROJECT_DIR/runtime"

# Parse tool info from stdin (JSON from Claude Code)
HOOK_DATA=$(cat)
TOOL_NAME=$(echo "$HOOK_DATA" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name','unknown'))" 2>/dev/null || echo "unknown")

# Find active chat_id from runtime files (one per active chat, safe due to per-chat locks)
CHAT_ID=""
if [ -d "$RUNTIME_DIR" ]; then
    for f in "$RUNTIME_DIR"/*.json; do
        [ -f "$f" ] || continue
        CHAT_ID=$(python3 -c "import json; print(json.load(open('$f'))['chat_id'])" 2>/dev/null || echo "")
        [ -n "$CHAT_ID" ] && break
    done
fi
[ -z "$CHAT_ID" ] && exit 0

# Build a short, human message per tool
case "$TOOL_NAME" in
    Bash)
        CMD=$(echo "$HOOK_DATA" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command','')[:80])" 2>/dev/null || echo "")
        MSG="running: $CMD"
        ;;
    WebSearch)
        Q=$(echo "$HOOK_DATA" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('query','')[:80])" 2>/dev/null || echo "")
        MSG="searching: $Q"
        ;;
    WebFetch)
        URL=$(echo "$HOOK_DATA" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('url','')[:80])" 2>/dev/null || echo "")
        MSG="fetching: $URL"
        ;;
    Edit|Write)
        FP=$(echo "$HOOK_DATA" | python3 -c "import sys,json; d=json.load(sys.stdin).get('tool_input',{}); print(d.get('file_path', d.get('path',''))[-60:])" 2>/dev/null || echo "")
        MSG="writing: $FP"
        ;;
    *)
        MSG="using: $TOOL_NAME"
        ;;
esac

# Load token (same pattern as tools/telegram/send.sh)
TOKEN="${TELEGRAM_TOKEN:-}"
if [ -z "$TOKEN" ] && [ -f "$PROJECT_DIR/.env" ]; then
    TOKEN=$(grep '^TELEGRAM_TOKEN=' "$PROJECT_DIR/.env" | cut -d'=' -f2)
fi
[ -z "$TOKEN" ] && exit 0

curl -s -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
    -d "chat_id=$CHAT_ID" \
    -d "text=$MSG" > /dev/null 2>&1 || true

exit 0
