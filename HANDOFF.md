# AI Usage Widget — Mac Setup Handoff

Use this document in **Claude Code terminal on the user's Mac** to install, verify, and troubleshoot the AI Usage Widget (Claude + Codex CLI auth).

**Goal:** Widget running locally, reading credentials from open `claude` and `codex` CLI sessions (keychain/keyring), showing usage on `http://127.0.0.1:9113`.

---

## Context

- Repo: `https://github.com/siperdudeuk/claude-usage-widget`
- Feature branch: `cursor/ai-usage-codex-8618`
- Widget UI: macOS app (`ClaudeWidget.app`) + Python backend (`macos/claude-usage.py`)
- Auth sources (no Chrome required if CLI logged in):
  - **Claude:** `claude login` → OS keychain (`Claude Code-credentials`) or `~/.claude/.credentials.json`
  - **Codex:** `codex login` → OS keyring or `~/.codex/auth.json`

---

## Phase 0 — Preconditions (user should already have)

- [ ] macOS with Xcode CLI tools (`xcode-select --install` if needed)
- [ ] `claude` CLI installed and logged in (`claude login` done at least once)
- [ ] `codex` CLI installed and logged in (`codex login` done at least once)
- [ ] Both may be open in Terminal — that's fine and helps keep tokens fresh

**Quick credential check:**

```bash
# Claude — at least one should succeed on macOS
security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null | head -c 80 && echo "..."
test -f ~/.claude/.credentials.json && echo "Claude file: OK"

# Codex — keyring or file
test -f ~/.codex/auth.json && echo "Codex auth.json: OK"
test -f ~/.codex/config.toml && grep -i credentials_store ~/.codex/config.toml || true
```

If Codex config shows `cli_auth_credentials_store = "ephemeral"`, change it to `"file"` or `"auto"`, then re-run `codex login`.

---

## Phase 1 — Get the code

```bash
REPO_DIR="$HOME/claude-usage-widget"
BRANCH="cursor/ai-usage-codex-8618"

if [ -d "$REPO_DIR/.git" ]; then
  cd "$REPO_DIR"
  git fetch origin
  git checkout "$BRANCH"
  git pull origin "$BRANCH"
else
  git clone -b "$BRANCH" https://github.com/siperdudeuk/claude-usage-widget.git "$REPO_DIR"
  cd "$REPO_DIR"
fi

cd macos
pwd
git log -1 --oneline
```

Expected: latest commit mentions CLI OAuth / keyring support.

---

## Phase 2 — Install Python deps

```bash
cd "$HOME/claude-usage-widget/macos"
/usr/bin/python3 -m pip install --user -r requirements.txt
/usr/bin/python3 -c "import cryptography, curl_cffi, keyring; print('deps OK')"
```

---

## Phase 3 — Verify auth modules before launching widget

```bash
cd "$HOME/claude-usage-widget/macos"
/usr/bin/python3 << 'PY'
import sys, json
sys.path.insert(0, "../common")
from claude_auth import get_claude_auth_status, load_claude_credentials
from codex_auth import get_codex_auth_status, load_codex_credentials

print("=== Claude auth status ===")
print(json.dumps(get_claude_auth_status(), indent=2))
try:
    c = load_claude_credentials()
    print("Claude token prefix:", c["access_token"][:20], "...")
except Exception as e:
    print("Claude load error:", e)

print("\n=== Codex auth status ===")
print(json.dumps(get_codex_auth_status(), indent=2))
try:
    t, a = load_codex_credentials()
    print("Codex token prefix:", t[:20], "...")
    print("Codex account_id:", a)
except Exception as e:
    print("Codex load error:", e)
PY
```

**Pass criteria:**
- `has_claude_cli_auth: true`
- `has_codex_auth: true`

If either is false, fix CLI login before continuing.

---

## Phase 4 — Build and start widget

```bash
cd "$HOME/claude-usage-widget/macos"
./stop.sh 2>/dev/null || true
./start.sh
```

Wait ~15 seconds for backend API.

---

## Phase 5 — API verification

```bash
echo "=== /api/status ==="
curl -s http://127.0.0.1:9113/api/status | python3 -m json.tool

echo ""
echo "=== /api/usage (truncated) ==="
curl -s http://127.0.0.1:9113/api/usage | python3 -m json.tool | head -60
```

**Pass criteria:**

| Field | Expected |
|---|---|
| `has_claude_cli_auth` | `true` |
| `has_codex_auth` | `true` |
| `last_claude_error` | `null` |
| `last_codex_error` | `null` |
| `usage.claude.error` | `null` |
| `usage.codex.error` | `null` |
| `usage.claude.auth_source` | `"cli"` |
| `usage.claude.five_hour` | object with `utilization` |
| `usage.codex.five_hour` | object with `utilization` |

Widget UI should show **⚡ AI Usage** with **All / Claude / Codex** tabs. Footer example: `Updated … • Claude (CLI) + Codex (plus)`.

---

## Phase 6 — If backend fails to start

```bash
cd "$HOME/claude-usage-widget/macos"
pkill -f 'claude-usage.py' 2>/dev/null || true
/usr/bin/python3 claude-usage.py
```

Run in foreground briefly to read errors, then Ctrl+C and retry `./start.sh`.

Check log if using install.sh launcher:

```bash
tail -50 ~/claude-usage-widget/macos/claude-usage.log 2>/dev/null || true
```

---

## Troubleshooting matrix

| Symptom | Likely cause | Fix |
|---|---|---|
| `has_claude_cli_auth: false` | Not logged into Claude Code CLI | `claude login` |
| `has_codex_auth: false` | Not logged into Codex CLI | `codex login` |
| `codex_ephemeral: true` | Ephemeral credential mode | Set `cli_auth_credentials_store = "file"` in `~/.codex/config.toml`, re-login |
| `curl_cffi not installed` | Missing Python dep | `pip3 install curl_cffi` |
| Claude keychain read fails from app | Backend not in GUI session | Launch via `./start.sh` / open `ClaudeWidget.app` (not detached nohup) |
| `Claude OAuth HTTP 429` | Rate limit on usage API | Wait and retry; keep CLI session open |
| Chrome fallback errors only | CLI auth not found | Fix Phase 3 first; Chrome is fallback only |

---

## Report back to cloud agent

Paste this output bundle:

```bash
{
  echo "=== git ==="
  cd "$HOME/claude-usage-widget" && git log -1 --oneline
  echo "=== status ==="
  curl -s http://127.0.0.1:9113/api/status | python3 -m json.tool
  echo "=== usage errors only ==="
  curl -s http://127.0.0.1:9113/api/usage | python3 -c "import sys,json; d=json.load(sys.stdin); print('claude:', d.get('claude',{}).get('error')); print('codex:', d.get('codex',{}).get('error'))"
}
```

Redact any tokens if manually copying credential debug output.

---

## Prompt for Claude Code (copy-paste)

```
You are setting up the AI Usage Widget on this Mac. Follow HANDOFF.md in the
repo step by step (Phases 0–5). Do not skip verification steps. If Phase 3
shows missing CLI auth, run claude login / codex login as needed. After Phase 5,
summarize pass/fail and paste the "Report back" bundle. Do not expose full tokens
in output — only prefixes and error messages.
```

Repo path after clone: `~/claude-usage-widget/HANDOFF.md`
