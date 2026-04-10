# Claude Usage Widget

A lightweight macOS desktop widget that shows your Claude.ai usage limits in real time. Always-on-top, draggable, and lives in your menu bar.

![macOS](https://img.shields.io/badge/macOS-only-blue) ![License](https://img.shields.io/badge/license-MIT-green)

## What it shows

- **5-Hour usage** — rolling short-term limit with reset countdown
- **7-Day usage** — weekly limit with reset countdown
- **Per-model breakdown** — Opus and Sonnet usage (when available)
- **Extra credits** — overuse billing status and spend

Bars change colour as you approach limits: purple → yellow → red.

## How it works

1. A Python backend reads your Chrome session cookies directly from disk — **no browser tab needed**, no API keys, no tokens to copy
2. It polls the usage endpoint every 60 seconds and serves the data on `localhost:9113`
3. A native Swift widget reads from that local API and renders a floating overlay

If direct cookie extraction isn't available, it falls back to an AppleScript bridge that uses an open `claude.ai` Chrome tab.

## Requirements

- macOS (tested on Sonoma / Sequoia)
- Google Chrome — logged into `claude.ai` (doesn't need to be open/running)
- Xcode Command Line Tools (`xcode-select --install`)
- Python 3 (included with macOS)
- A Claude Pro or Max subscription

## Quick start

```bash
git clone https://github.com/siperdudeuk/claude-usage-widget.git
cd claude-usage-widget
./start.sh
```

This builds the Swift widget (first run only) and starts both the backend and the overlay.

## Install as an app

```bash
./install.sh
```

This creates `Claude Usage Widget.app` in `~/Applications` so you can launch it from Spotlight or set it to open at login.

## Stop

```bash
./stop.sh
```

## Configuration

All settings are via environment variables (set them before running `start.sh`):

| Variable | Default | Description |
|---|---|---|
| `CLAUDE_ORG_ID` | auto-detected | Your Claude organisation UUID |
| `CLAUDE_POLL_INTERVAL` | `60` | Seconds between usage polls |
| `CLAUDE_WIDGET_PORT` | `9113` | Local API port |

If `CLAUDE_ORG_ID` is not set, the backend will auto-detect it from your Chrome session on first launch.

## Menu bar

Look for the ⚡ icon in your menu bar:
- **Show/Hide** — toggle the widget overlay
- **Pin on Top** — keep the widget above all windows
- **Quit** — stop the widget and backend

## Permissions

On first run, macOS will ask you to grant Chrome automation permissions. Go to **System Settings → Privacy & Security → Automation** and allow the terminal/app to control Chrome.

## License

MIT

## Support

If you find this useful, consider buying me a coffee!

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-support-yellow?style=flat&logo=buy-me-a-coffee)](https://buymeacoffee.com/nathanbb)
