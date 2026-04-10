# Claude Usage Widget

A lightweight desktop widget that shows your Claude.ai usage limits in real time. Always-on-top, draggable, with a built-in setup wizard.

Available for **macOS** and **Windows**.

![macOS](https://img.shields.io/badge/macOS-supported-blue) ![Windows](https://img.shields.io/badge/Windows-supported-blue) ![License](https://img.shields.io/badge/license-MIT-green)

## What it shows

- **5-Hour usage** — rolling short-term limit with reset countdown
- **7-Day usage** — weekly limit with reset countdown
- **Per-model breakdown** — Opus and Sonnet usage (when available)
- **Extra credits** — overuse billing status and spend

Bars change colour as you approach limits: purple -> yellow -> red.

## How it works

1. A Python backend reads your Chrome session cookies directly from disk — **no browser tab needed**, no API keys, no tokens to copy
2. It polls the usage endpoint every 60 seconds and serves the data on `localhost:9113`
3. A native widget reads from that local API and renders a floating always-on-top overlay
4. On first launch, a **setup wizard** guides you through any missing steps

---

## macOS

### Requirements

- macOS (tested on Sonoma / Sequoia)
- Google Chrome — logged into `claude.ai` (doesn't need to be open/running)
- Xcode Command Line Tools (`xcode-select --install`)
- Python 3 (included with macOS)
- A Claude Pro or Max subscription

### Quick start

```bash
git clone https://github.com/siperdudeuk/claude-usage-widget.git
cd claude-usage-widget/macos
./start.sh
```

This installs dependencies, builds the Swift widget (first run only), and starts everything.

### Install as an app

```bash
cd macos
./install.sh
```

Creates `Claude Usage Widget.app` in `~/Applications` — launch from Spotlight or set to open at login.

### Stop

```bash
cd macos
./stop.sh
```

### Menu bar

Look for the ⚡ icon in your menu bar:
- **Show/Hide** — toggle the widget overlay
- **Pin on Top** — keep the widget above all windows
- **Quit** — stop the widget and backend

### Permissions

On first run, macOS may ask you to grant Chrome automation permissions (only used as a fallback). Go to **System Settings > Privacy & Security > Automation** and allow the terminal/app to control Chrome.

---

## Windows

### Requirements

- Windows 10 or 11
- Google Chrome — logged into `claude.ai`
- Python 3.8+ (install from [python.org](https://python.org), check "Add to PATH")
- A Claude Pro or Max subscription

### Quick start

```cmd
git clone https://github.com/siperdudeuk/claude-usage-widget.git
cd claude-usage-widget\windows
start.bat
```

This installs dependencies and launches the widget.

### Install

```cmd
cd windows
install.bat
```

Creates a Start Menu shortcut so you can search "Claude Usage Widget" to launch it.

### Stop

```cmd
stop.bat
```

---

## Configuration

All settings are via environment variables (set before launching):

| Variable | Default | Description |
|---|---|---|
| `CLAUDE_ORG_ID` | auto-detected | Your Claude organisation UUID |
| `CLAUDE_POLL_INTERVAL` | `60` | Seconds between usage polls |
| `CLAUDE_WIDGET_PORT` | `9113` | Local API port |

If `CLAUDE_ORG_ID` is not set, the backend auto-detects it from your Chrome session on first launch.

## License

MIT

## Support

If you find this useful, consider buying me a coffee!

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-support-yellow?style=flat&logo=buy-me-a-coffee)](https://buymeacoffee.com/nathanbb)
