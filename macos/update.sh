#!/bin/bash
# Pulls latest version from GitHub, rebuilds, and restarts the widget.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

PYTHON_BIN="/usr/bin/python3"

echo "Pulling latest changes..."
git pull --ff-only

cd "$SCRIPT_DIR"

# Ensure Python deps are present and arch-correct. curl_cffi (and cryptography)
# ship compiled wheels per-arch; the widget now builds a universal app that runs
# native arm64 on Apple Silicon, so force arm64 wheels even if this updater is
# itself invoked under Rosetta (e.g. spawned by an older x86_64 build).
PIP_ARCH=""
if sysctl -n hw.optional.arm64 2>/dev/null | grep -q '^1$'; then
    PIP_ARCH="arch -arm64"
fi
echo "Ensuring Python dependencies..."
$PIP_ARCH "$PYTHON_BIN" -m pip install -q --user -r requirements.txt \
    || "$PYTHON_BIN" -m pip install -q --user -r requirements.txt \
    || echo "WARN: dependency install failed; usage fetch may be degraded" >&2

echo "Rebuilding widget..."
bash build.sh

# Install to ~/Applications
mkdir -p ~/Applications
rm -rf ~/Applications/ClaudeWidget.app
cp -R ClaudeWidget.app ~/Applications/ClaudeWidget.app

# Restart: kill old processes, then relaunch the app, which spawns the backend
# as its own in-session child (keeps Keychain access; no detached nohup orphan).
echo "Restarting..."
pkill -f 'claude-usage.py' 2>/dev/null || true
pkill -f 'ClaudeWidget' 2>/dev/null || true
sleep 1

open ClaudeWidget.app

echo "Update complete."
