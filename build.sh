#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Building ClaudeWidget..."
swiftc ClaudeWidget.swift \
    -framework Cocoa \
    -framework WebKit \
    -o ClaudeWidget \
    -O

echo "Build complete: $SCRIPT_DIR/ClaudeWidget"
