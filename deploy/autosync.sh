#!/bin/bash
# lobster-bot autosync — commit and push any changes every 5 min via cron
# Install: crontab -e → */5 * * * * /path/to/lobster-bot/deploy/autosync.sh >> /path/to/lobster-bot/logs/autosync.log 2>&1
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

# Check for local changes
if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    exit 0  # nothing to sync
fi

# Stage and commit
git add -A
git commit -m "autosync: $(date -u +%Y-%m-%d\ %H:%M:%S\ UTC)" --no-gpg-sign 2>/dev/null || exit 0

# Push to origin
git push origin main 2>/dev/null || true
