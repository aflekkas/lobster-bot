#!/usr/bin/env bash
# Stop hook — stamps session end time in today's daily log.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TODAY=$(date +%Y-%m-%d)
NOW=$(date +%H:%M)
LOG="$PROJECT_DIR/memory/daily/$TODAY.md"

mkdir -p "$(dirname "$LOG")"
printf "\n---\n_session ended %s_\n" "$NOW" >> "$LOG"

exit 0
