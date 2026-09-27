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

# Compile a universal binary (arm64 + x86_64). This is essential, not cosmetic:
# the app spawns the Python usage backend, which inherits the app's CPU arch, and
# that backend's fetch library (curl_cffi) ships arch-specific compiled wheels. An
# x86_64-only app forces the whole stack under Rosetta and demands x86_64 wheels;
# a universal binary runs natively on Apple Silicon (and Intel), so a normal wheel
# for the host arch just works — regardless of the arch this build itself runs as.
COMMON_FLAGS=(-framework Cocoa -framework WebKit -O)

SLICES=()
if swiftc ClaudeWidget.swift "${COMMON_FLAGS[@]}" -target arm64-apple-macosx11.0 -o "$APP_NAME-arm64"; then
    SLICES+=("$APP_NAME-arm64")
fi
if swiftc ClaudeWidget.swift "${COMMON_FLAGS[@]}" -target x86_64-apple-macosx11.0 -o "$APP_NAME-x86_64"; then
    SLICES+=("$APP_NAME-x86_64")
fi

if [ ${#SLICES[@]} -eq 0 ]; then
    echo "ERROR: Swift compile failed for all architectures" >&2
    exit 1
elif [ ${#SLICES[@]} -eq 1 ]; then
    mv "${SLICES[0]}" "$APP_NAME"
    echo "Built single-arch binary: ${SLICES[0]#$APP_NAME-}"
else
    lipo -create "${SLICES[@]}" -o "$APP_NAME"
    rm -f "${SLICES[@]}"
    echo "Built universal binary (arm64 + x86_64)"
fi

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
cp ../common/codex_auth.py "$RESOURCES/codex_auth.py"
cp ../common/claude_auth.py "$RESOURCES/claude_auth.py"

# Create Info.plist
cat > "$CONTENTS/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>AI Usage Widget</string>
    <key>CFBundleDisplayName</key>
    <string>AI Usage Widget</string>
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
