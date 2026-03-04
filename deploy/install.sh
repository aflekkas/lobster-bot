#!/usr/bin/env bash
set -euo pipefail

# lobster-bot — Quick VPS setup
# Usage: ./deploy/install.sh

REPO_DIR="${LOBSTERBOT_DIR:-$HOME/lobster-bot}"
PYTHON="${PYTHON:-python3}"

echo "=== lobster-bot Installer ==="
echo ""

# Check prerequisites
command -v git >/dev/null 2>&1 || { echo "Error: git is required"; exit 1; }
command -v "$PYTHON" >/dev/null 2>&1 || { echo "Error: $PYTHON is required"; exit 1; }
command -v claude >/dev/null 2>&1 || { echo "Error: Claude Code CLI is required. Install from https://docs.anthropic.com/en/docs/claude-code"; exit 1; }

# Check Python version
PY_VERSION=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
    echo "Error: Python 3.11+ required (found $PY_VERSION)"
    exit 1
fi

echo "Prerequisites OK (Python $PY_VERSION)"
echo ""

# Clone or update repo
if [ -d "$REPO_DIR" ]; then
    echo "Updating existing installation at $REPO_DIR..."
    cd "$REPO_DIR"
    git pull --ff-only
else
    echo "Cloning lobster-bot to $REPO_DIR..."
    git clone https://github.com/aflekkas/lobster-bot.git "$REPO_DIR"
    cd "$REPO_DIR"
fi

# Install dependencies
echo "Installing Python dependencies..."
$PYTHON -m pip install -r requirements.txt --quiet

# Install Playwright browser for web browsing
echo "Installing Playwright Chromium..."
npx playwright install --with-deps chromium

# Create .env if missing
if [ ! -f "$REPO_DIR/.env" ]; then
    echo ""
    echo "Creating .env template..."
    cat > "$REPO_DIR/.env" << 'EOF'
TELEGRAM_TOKEN=your-bot-token-here
TELEGRAM_USER_IDS=your-user-id-here
EOF
    echo "IMPORTANT: Edit $REPO_DIR/.env with your:"
    echo "  1. Telegram bot token (from @BotFather)"
    echo "  2. Your Telegram user ID (from @userinfobot)"
else
    echo ".env already exists, skipping."
fi

# Set up systemd service (Linux only)
if command -v systemctl >/dev/null 2>&1; then
    echo ""
    echo "Setting up systemd service..."
    sudo cp "$REPO_DIR/deploy/systemd/lobster-bot.service" /etc/systemd/system/

    # Replace paths and user
    sudo sed -i "s|/root/lobster-bot|$REPO_DIR|g" /etc/systemd/system/lobster-bot.service
    sudo sed -i "s|User=root|User=$(whoami)|g" /etc/systemd/system/lobster-bot.service

    sudo systemctl daemon-reload
    echo "Service installed. Enable with:"
    echo "  sudo systemctl enable --now lobster-bot"
fi

echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit $REPO_DIR/.env with your Telegram token and user ID"
echo "  2. Run: cd $REPO_DIR && source .env && $PYTHON run.py"
echo ""
