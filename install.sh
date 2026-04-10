#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Build the widget
bash build.sh

# Create .app bundle
APP_DIR="$HOME/Applications/ClaudeUsageWidget.app"
echo "Installing to $APP_DIR..."

mkdir -p "$APP_DIR/Contents/MacOS"

cat > "$APP_DIR/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>ClaudeUsageWidget</string>
    <key>CFBundleDisplayName</key><string>Claude Usage Widget</string>
    <key>CFBundleIdentifier</key><string>com.github.claude-usage-widget</string>
    <key>CFBundleVersion</key><string>1.0.0</string>
    <key>CFBundleExecutable</key><string>launch</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSUIElement</key><true/>
</dict>
</plist>
PLIST

cat > "$APP_DIR/Contents/MacOS/launch" << LAUNCHER
#!/bin/bash
cd "$SCRIPT_DIR"
pkill -f 'claude-usage.py' 2>/dev/null || true
pkill -f 'ClaudeWidget' 2>/dev/null || true
sleep 1
nohup /usr/bin/python3 "$SCRIPT_DIR/claude-usage.py" > "$SCRIPT_DIR/claude-usage.log" 2>&1 &
echo \$! > "$SCRIPT_DIR/claude-usage.pid"
sleep 6
nohup "$SCRIPT_DIR/ClaudeWidget" > /dev/null 2>&1 &
echo \$! > "$SCRIPT_DIR/claude-widget.pid"
LAUNCHER
chmod +x "$APP_DIR/Contents/MacOS/launch"

echo ""
echo "Installed! You can now:"
echo "  1. Open 'Claude Usage Widget' from ~/Applications"
echo "  2. Or run: open $APP_DIR"
echo ""
echo "Make sure you have a claude.ai tab open in Chrome first."
