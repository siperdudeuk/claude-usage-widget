#!/bin/bash
# Quick start — builds, installs, and launches Claude Usage Widget
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Install Python dependencies if needed
if ! python3 -c "import cryptography" 2>/dev/null; then
    echo "Installing dependencies..."
    pip3 install -q -r requirements.txt
fi

# Build if needed
if [ ! -d ClaudeWidget.app ]; then
    echo "First run — building widget..."
    bash build.sh
fi

# Install to ~/Applications so it shows in Launchpad/Spotlight
mkdir -p ~/Applications
if [ -d ClaudeWidget.app ]; then
    rm -rf ~/Applications/ClaudeWidget.app
    cp -R ClaudeWidget.app ~/Applications/ClaudeWidget.app
    echo "Installed to ~/Applications/ClaudeWidget.app"
fi

# Stop any existing instances
pkill -f 'claude-usage.py' 2>/dev/null || true
pkill -f 'ClaudeWidget' 2>/dev/null || true
sleep 1

echo "Starting backend..."
nohup /usr/bin/python3 claude-usage.py > claude-usage.log 2>&1 &
echo $! > claude-usage.pid
echo "  Backend PID: $(cat claude-usage.pid)"

sleep 3

if kill -0 "$(cat claude-usage.pid)" 2>/dev/null; then
    echo "  Backend: Running"
else
    echo "  Backend: FAILED"
    cat claude-usage.log
    exit 1
fi

echo "Starting widget..."
open ClaudeWidget.app
echo ""
echo "Done! Claude Usage Widget is running — check your Dock."
