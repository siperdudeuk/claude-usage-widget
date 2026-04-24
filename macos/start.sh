#!/bin/bash
# Quick start — builds, installs, and launches Claude Usage Widget
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Always use the system Python on modern macOS. The user's PATH may still
# point at an ancient /usr/local Python shim that gets killed on launch.
PYTHON_BIN="/usr/bin/python3"
PIP_BIN="/usr/bin/pip3"

# Install Python dependencies if needed
if ! "$PYTHON_BIN" -c "import cryptography" 2>/dev/null; then
    echo "Installing dependencies..."
    "$PIP_BIN" install -q -r requirements.txt
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
nohup "$PYTHON_BIN" claude-usage.py > claude-usage.log 2>&1 &
echo $! > claude-usage.pid
echo "  Backend PID: $(cat claude-usage.pid)"

if kill -0 "$(cat claude-usage.pid)" 2>/dev/null; then
    echo "  Backend: Running"
else
    echo "  Backend: FAILED"
    cat claude-usage.log
    exit 1
fi

echo "Waiting for backend API..."
READY=0
for _ in $(seq 1 20); do
    if /usr/bin/curl -fsS --max-time 2 "http://127.0.0.1:9113/api/status" >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 1
done

if [ "$READY" -ne 1 ]; then
    echo "  Backend API: FAILED"
    cat claude-usage.log
    exit 1
fi

echo "  Backend API: Ready"

echo "Starting widget..."
open ClaudeWidget.app
echo ""
echo "Done! Claude Usage Widget is running — check your Dock."
