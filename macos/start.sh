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

# Launch the widget. The app spawns the Python backend as its OWN child, so
# the backend stays inside the GUI login session and keeps Keychain access
# (the cookie path must read "Chrome Safe Storage" from the Keychain — a
# detached/nohup'd backend that reparents to launchd cannot, which silently
# breaks usage fetching). The app also supervises and respawns it if it dies.
echo "Starting widget (it launches and supervises the backend in-session)..."
open ClaudeWidget.app

echo "Waiting for backend API..."
READY=0
for _ in $(seq 1 25); do
    if /usr/bin/curl -fsS --max-time 2 "http://127.0.0.1:9113/api/status" >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 1
done

if [ "$READY" -ne 1 ]; then
    echo "  Backend API: not ready yet — the widget will keep retrying."
else
    echo "  Backend API: Ready"
fi

echo ""
echo "Done! Claude Usage Widget is running — check your Dock."
