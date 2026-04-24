#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="ClaudeWidget"
APP_BUNDLE="$APP_NAME.app"
CONTENTS="$APP_BUNDLE/Contents"
MACOS_DIR="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"

echo "Building $APP_NAME..."

# Compile binary
swiftc ClaudeWidget.swift \
    -framework Cocoa \
    -framework WebKit \
    -o "$APP_NAME" \
    -O

# Generate icon if needed
if [ ! -f "$APP_NAME.icns" ]; then
    echo "Generating app icon..."
    /usr/bin/python3 generate-icon.py 2>/dev/null || true
fi

# Create .app bundle
rm -rf "$APP_BUNDLE"
mkdir -p "$MACOS_DIR" "$RESOURCES"

mv "$APP_NAME" "$MACOS_DIR/$APP_NAME"

# Copy icon
if [ -f "$APP_NAME.icns" ]; then
    cp "$APP_NAME.icns" "$RESOURCES/$APP_NAME.icns"
fi

# Bundle the local backend so the app can self-start even when opened directly.
cp claude-usage.py "$RESOURCES/claude-usage.py"

# Create Info.plist
cat > "$CONTENTS/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Claude Usage</string>
    <key>CFBundleDisplayName</key>
    <string>Claude Usage</string>
    <key>CFBundleIdentifier</key>
    <string>com.siperdudeuk.claude-usage-widget</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundlePackagetype</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>ClaudeWidget</string>
    <key>CFBundleIconFile</key>
    <string>ClaudeWidget</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSAppTransportSecurity</key>
    <dict>
        <key>NSAllowsLocalNetworking</key>
        <true/>
    </dict>
</dict>
</plist>
PLIST

# Keep a symlink so existing scripts still work
ln -sf "$APP_BUNDLE/Contents/MacOS/$APP_NAME" "$APP_NAME"

echo "Build complete: $SCRIPT_DIR/$APP_BUNDLE"
