#!/bin/bash
# Stop the backend and widget
pkill -f 'claude-usage.py' 2>/dev/null && echo "Backend stopped." || echo "Backend not running."
pkill -f 'ClaudeWidget' 2>/dev/null && echo "Widget stopped." || echo "Widget not running."
