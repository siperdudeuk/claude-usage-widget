#!/bin/bash
# Quick start — runs the backend + widget without installing as an app
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Build if needed
if [ ! -f ClaudeWidget ]; then
    echo "First run — building widget..."
    bash build.sh
fi

# Stop any existing instances
pkill -f 'claude-usage.py' 2>/dev/null || true
pkill -f 'ClaudeWidget' 2>/dev/null || true
sleep 1

echo "Starting backend..."
nohup /usr/bin/python3 claude-usage.py > claude-usage.log 2>&1 &
echo $! > claude-usage.pid
echo "  Backend PID: $(cat claude-usage.pid)"

sleep 6

if kill -0 "$(cat claude-usage.pid)" 2>/dev/null; then
    echo "  Backend: Running"
    curl -s http://localhost:${CLAUDE_WIDGET_PORT:-9113}/api/usage | python3 -m json.tool 2>&1 | head -15
else
    echo "  Backend: FAILED"
    cat claude-usage.log
    exit 1
fi

echo "Starting widget..."
nohup ./ClaudeWidget > /dev/null 2>&1 &
echo $! > claude-widget.pid
echo "  Widget PID: $(cat claude-widget.pid)"
echo ""
echo "Done! Look for the ⚡ icon in your menu bar."
