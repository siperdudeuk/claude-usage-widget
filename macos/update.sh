#!/bin/bash
# Pulls latest version from GitHub, rebuilds, and restarts the widget.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

echo "Pulling latest changes..."
git pull --ff-only

cd "$SCRIPT_DIR"

# Reinstall deps if requirements changed
if ! python3 -c "import cryptography" 2>/dev/null; then
    echo "Installing new dependencies..."
    pip3 install -q -r requirements.txt
fi

echo "Rebuilding widget..."
bash build.sh

# Install to ~/Applications
mkdir -p ~/Applications
rm -rf ~/Applications/ClaudeWidget.app
cp -R ClaudeWidget.app ~/Applications/ClaudeWidget.app

# Restart: kill old processes, start new ones
echo "Restarting..."
pkill -f 'claude-usage.py' 2>/dev/null || true
pkill -f 'ClaudeWidget' 2>/dev/null || true
sleep 1

nohup /usr/bin/python3 claude-usage.py > claude-usage.log 2>&1 &
echo $! > claude-usage.pid
sleep 3
open ClaudeWidget.app

echo "Update complete."
