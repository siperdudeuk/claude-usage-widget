#!/usr/bin/env python3
"""
Claude Usage Monitor — Backend
Fetches claude.ai usage data and serves it via local HTTP on port 9113.

Auth methods (tried in order):
  1. Direct cookie extraction from Chrome's cookie store (no browser tab needed)
  2. AppleScript bridge via an open claude.ai Chrome tab (fallback)
"""

import subprocess
import json
import threading
import time
import os
import sys
import sqlite3
import shutil
import tempfile
import hashlib
import uuid
import base64
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

ORG_ID = os.environ.get("CLAUDE_ORG_ID", "")
POLL_INTERVAL = int(os.environ.get("CLAUDE_POLL_INTERVAL", "60"))
PORT = int(os.environ.get("CLAUDE_WIDGET_PORT", "9113"))
UPDATE_CHECK_INTERVAL = 3600  # once per hour
GITHUB_REPO = "siperdudeuk/claude-usage-widget"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)  # parent of macos/

usage_data = {"error": "Starting up...", "timestamp": None}
usage_lock = threading.Lock()

version_info = {
    "current": None,
    "latest": None,
    "update_available": False,
    "latest_message": None,
    "checked_at": None,
}
version_lock = threading.Lock()

# Which fetch method is currently working
_fetch_method = None  # "cookies" or "applescript"
_session_cookie = None
_cookie_last_refreshed = 0
COOKIE_REFRESH_INTERVAL = 300  # re-read cookies every 5 minutes


# ---------------------------------------------------------------------------
# Method 1: Direct cookie extraction from Chrome's cookie store
# ---------------------------------------------------------------------------

def _get_chrome_encryption_key():
    """Get Chrome's cookie encryption key from the macOS Keychain."""
    result = subprocess.run(
        ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise Exception("Could not read Chrome Safe Storage key from Keychain")
    return result.stdout.strip()


def _decrypt_chrome_cookie(encrypted_value, key):
    """Decrypt a Chrome cookie value on macOS."""
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding
        from cryptography.hazmat.backends import default_backend
    except ImportError:
        raise Exception("cryptography package not installed — run: pip3 install cryptography")

    if encrypted_value[:3] == b"v10":
        encrypted_value = encrypted_value[3:]
    else:
        # Not encrypted or unknown format
        return encrypted_value.decode("utf-8", errors="replace")

    derived_key = hashlib.pbkdf2_hmac("sha1", key.encode("utf-8"), b"saltysalt", 1003, dklen=16)
    iv = b" " * 16
    cipher = Cipher(algorithms.AES(derived_key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(encrypted_value) + decryptor.finalize()

    # Remove PKCS7 padding
    unpadder = padding.PKCS7(128).unpadder()
    decrypted = unpadder.update(decrypted) + unpadder.finalize()
    # Chrome 127+ prepends a 32-byte SHA256 origin-binding hash before the
    # plaintext to prevent cross-origin cookie replay. Strip it when present.
    if len(decrypted) >= 32:
        tail = decrypted[32:]
        try:
            return tail.decode("utf-8")
        except UnicodeDecodeError:
            pass
    return decrypted.decode("utf-8")


def get_chrome_cookies():
    """Extract claude.ai session cookies directly from Chrome's cookie store."""
    cookie_paths = [
        os.path.expanduser("~/Library/Application Support/Google/Chrome/Default/Cookies"),
        os.path.expanduser("~/Library/Application Support/Google/Chrome/Profile 1/Cookies"),
    ]

    cookie_db = None
    for p in cookie_paths:
        if os.path.exists(p):
            cookie_db = p
            break

    if not cookie_db:
        raise Exception("Chrome cookie database not found")

    key = _get_chrome_encryption_key()

    # Copy the DB to a temp file (Chrome may have it locked)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    shutil.copy2(cookie_db, tmp.name)

    try:
        conn = sqlite3.connect(tmp.name)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, encrypted_value FROM cookies WHERE host_key LIKE '%claude.ai%'"
        )
        cookies = {}
        for name, encrypted_value in cursor.fetchall():
            try:
                cookies[name] = _decrypt_chrome_cookie(encrypted_value, key)
            except Exception:
                continue
        conn.close()
    finally:
        os.unlink(tmp.name)

    if not cookies:
        raise Exception("No claude.ai cookies found in Chrome — are you logged in?")

    return cookies


_cookie_dict = None


def fetch_via_cookies(url):
    """Make an authenticated request to claude.ai using extracted cookies.

    claude.ai sits behind Cloudflare bot management, which fingerprints TLS
    and HTTP/2 settings. Plain urllib gets a 403 JS challenge. curl_cffi
    impersonates Chrome's fingerprint so the request passes.
    """
    global _cookie_dict, _cookie_last_refreshed

    try:
        from curl_cffi import requests as _cc
    except ImportError:
        raise Exception("curl_cffi not installed — run: /usr/bin/python3 -m pip install --user curl_cffi")

    now = time.time()
    if _cookie_dict is None or (now - _cookie_last_refreshed) > COOKIE_REFRESH_INTERVAL:
        _cookie_dict = get_chrome_cookies()
        _cookie_last_refreshed = now

    resp = _cc.get(url, cookies=_cookie_dict, impersonate="chrome", timeout=15)
    if resp.status_code == 401:
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)
    if resp.status_code >= 400:
        raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.text


def detect_org_id_via_cookies():
    """Detect org ID using cookie-based auth."""
    raw = fetch_via_cookies("https://claude.ai/api/organizations")
    orgs = json.loads(raw)
    if orgs and len(orgs) > 0:
        return orgs[0].get("uuid") or orgs[0].get("id")
    return None


# ---------------------------------------------------------------------------
# Method 2: AppleScript Chrome tab bridge (fallback)
# ---------------------------------------------------------------------------

def _is_chrome_running():
    """Check whether Chrome is currently running, without launching it."""
    result = subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to (name of processes) contains "Google Chrome"'],
        capture_output=True, text=True, timeout=5,
    )
    return result.stdout.strip().lower() == "true"


def fetch_via_chrome_tab(url):
    """Use AppleScript to run fetch() inside an existing claude.ai tab."""
    if not _is_chrome_running():
        raise Exception("Please open Chrome and go to claude.ai")
    script = '''
    tell application "Google Chrome"
        set foundTab to null
        set foundWindow to null
        set tabIdx to 0
        repeat with w in windows
            set ti to 0
            repeat with t in tabs of w
                set ti to ti + 1
                if URL of t starts with "https://claude.ai" then
                    set foundTab to t
                    set foundWindow to w
                    set tabIdx to ti
                    exit repeat
                end if
            end repeat
            if foundTab is not null then exit repeat
        end repeat
        if foundTab is null then
            return "ERROR:No claude.ai tab open in Chrome"
        end if

        tell foundTab to reload
        delay 4

        set origTitle to name of foundTab
        set jsCode to "fetch('" & "URL_PLACEHOLDER" & "', {credentials:'include'}).then(r=>r.text()).then(t=>{document.title='FETCHOK:'+t.substring(0,8000)}).catch(e=>{document.title='FETCHERR:'+e.message})"
        execute foundTab javascript jsCode
        delay 4
        set resultTitle to name of foundTab
        execute foundTab javascript "document.title='" & origTitle & "'"
        return resultTitle
    end tell
    '''.replace("URL_PLACEHOLDER", url)
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=30,
    )
    output = result.stdout.strip()
    if output.startswith("ERROR:"):
        raise Exception(output[6:])
    if output.startswith("FETCHERR:"):
        raise Exception(output[9:])
    if output.startswith("FETCHOK:"):
        return output[8:]
    return output


def detect_org_id_via_applescript():
    """Detect org ID using AppleScript Chrome tab."""
    raw = fetch_via_chrome_tab("https://claude.ai/api/organizations")
    orgs = json.loads(raw)
    if orgs and len(orgs) > 0:
        return orgs[0].get("uuid") or orgs[0].get("id")
    return None


# ---------------------------------------------------------------------------
# Unified fetch with automatic method selection
# ---------------------------------------------------------------------------

def fetch_url(url):
    """Fetch a URL from claude.ai, trying cookies first, then AppleScript."""
    global _fetch_method

    if _fetch_method == "cookies":
        return fetch_via_cookies(url)
    elif _fetch_method == "applescript":
        return fetch_via_chrome_tab(url)

    # Auto-detect: try cookies first
    try:
        result = fetch_via_cookies(url)
        _fetch_method = "cookies"
        print("  Using direct cookie extraction (no browser tab needed)")
        return result
    except Exception as e:
        print(f"  Cookie method unavailable: {e}")

    # Fall back to AppleScript
    try:
        result = fetch_via_chrome_tab(url)
        _fetch_method = "applescript"
        print("  Using AppleScript Chrome tab bridge (fallback)")
        return result
    except Exception as e2:
        raise Exception(f"All fetch methods failed. Cookies: {e} | AppleScript: {e2}")


def detect_org_id():
    """Detect org ID, trying cookies first, then AppleScript."""
    try:
        org = detect_org_id_via_cookies()
        if org:
            return org
    except Exception:
        pass

    try:
        org = detect_org_id_via_applescript()
        if org:
            return org
    except Exception:
        pass

    return None


def collect_usage():
    """Fetch usage data from claude.ai."""
    url = f"https://claude.ai/api/organizations/{ORG_ID}/usage"
    raw = fetch_url(url)
    data = json.loads(raw)
    data["timestamp"] = datetime.utcnow().isoformat() + "Z"
    data["error"] = None
    return data


# ---------------------------------------------------------------------------
# Version / update check
# ---------------------------------------------------------------------------

def _get_current_commit():
    """Get the current git commit SHA of the installation."""
    try:
        result = subprocess.run(
            ["git", "-C", REPO_DIR, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _get_latest_commit_from_github():
    """Query GitHub API for the latest commit on main."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Claude-Usage-Widget/1.0",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return {
        "sha": data.get("sha"),
        "message": (data.get("commit", {}).get("message") or "").split("\n")[0],
    }


def check_for_updates():
    """Compare current commit to the latest commit on GitHub."""
    global version_info
    current = _get_current_commit()
    try:
        latest = _get_latest_commit_from_github()
    except Exception as e:
        with version_lock:
            version_info["checked_at"] = datetime.utcnow().isoformat() + "Z"
        return

    with version_lock:
        version_info["current"] = current
        version_info["latest"] = latest["sha"]
        version_info["latest_message"] = latest["message"]
        version_info["update_available"] = (
            current is not None
            and latest["sha"] is not None
            and current != latest["sha"]
        )
        version_info["checked_at"] = datetime.utcnow().isoformat() + "Z"


def update_check_loop():
    while True:
        try:
            check_for_updates()
        except Exception:
            pass
        time.sleep(UPDATE_CHECK_INTERVAL)


def run_update():
    """Run the update script and return output."""
    update_script = os.path.join(SCRIPT_DIR, "update.sh")
    if not os.path.exists(update_script):
        return {"success": False, "error": "update.sh not found"}
    try:
        result = subprocess.run(
            ["bash", update_script],
            capture_output=True, text=True, timeout=120, cwd=SCRIPT_DIR,
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def polling_loop():
    global usage_data, _fetch_method, _session_cookie, ORG_ID
    while True:
        try:
            if not ORG_ID:
                detected = detect_org_id()
                if detected:
                    ORG_ID = detected
                    print(f"  Detected org: {ORG_ID}")
                else:
                    raise Exception("Please open Chrome and go to claude.ai")
            data = collect_usage()
            with usage_lock:
                usage_data = data
        except Exception as e:
            with usage_lock:
                usage_data["error"] = str(e)
                usage_data["timestamp"] = datetime.utcnow().isoformat() + "Z"
            # If cookies failed mid-run, reset so next poll retries detection
            if _fetch_method == "cookies" and "HTTP Error 401" in str(e):
                print("  Cookie auth expired, will re-extract next poll...")
                _session_cookie = None
                _cookie_last_refreshed = 0
        time.sleep(POLL_INTERVAL)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/usage":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with usage_lock:
                self.wfile.write(json.dumps(usage_data).encode())
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            status = {
                "method": _fetch_method,
                "org_id": ORG_ID or None,
                "has_cryptography": _has_cryptography(),
                "has_chrome_cookies": _has_chrome_cookies(),
            }
            self.wfile.write(json.dumps(status).encode())
        elif self.path == "/api/version":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with version_lock:
                self.wfile.write(json.dumps(version_info).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/update":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            result = run_update()
            self.wfile.write(json.dumps(result).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def _has_cryptography():
    try:
        import cryptography
        return True
    except ImportError:
        return False


def _has_chrome_cookies():
    paths = [
        os.path.expanduser("~/Library/Application Support/Google/Chrome/Default/Cookies"),
        os.path.expanduser("~/Library/Application Support/Google/Chrome/Profile 1/Cookies"),
    ]
    return any(os.path.exists(p) for p in paths)


# ---------------------------------------------------------------------------
# Anonymous usage ping (daily, no personal data)
# ---------------------------------------------------------------------------

_PING_URL = base64.b64decode("aHR0cHM6Ly93d3cuc21hcnR0ZW5hbnQuY28udWsvd3QvcGluZw==").decode()
_PING_ID_FILE = os.path.join(SCRIPT_DIR, ".widget-id")


def _get_widget_id():
    if os.path.exists(_PING_ID_FILE):
        with open(_PING_ID_FILE, "r") as f:
            return f.read().strip()
    wid = str(uuid.uuid4())
    with open(_PING_ID_FILE, "w") as f:
        f.write(wid)
    return wid


def send_usage_ping():
    try:
        wid = _get_widget_id()
        commit = _get_current_commit() or "unknown"
        payload = json.dumps({"id": wid, "os": "macos", "v": commit[:8]}).encode()
        req = urllib.request.Request(_PING_URL, data=payload, headers={
            "Content-Type": "application/json",
            "User-Agent": "Claude-Usage-Widget/1.0",
        })
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def ping_loop():
    send_usage_ping()
    while True:
        time.sleep(86400)
        send_usage_ping()


def main():
    global ORG_ID

    print("Claude Usage Monitor starting...")
    print()

    if not ORG_ID:
        print("No CLAUDE_ORG_ID set. Attempting auto-detection...")
        detected = detect_org_id()
        if detected:
            ORG_ID = detected
            print(f"  Detected org: {ORG_ID}")
        else:
            print("  Org not detected yet — will retry from polling loop.")
            with usage_lock:
                usage_data["error"] = "Please open Chrome and go to claude.ai"
                usage_data["timestamp"] = datetime.utcnow().isoformat() + "Z"

    print(f"  Org:  {ORG_ID or '(pending)'}")
    print(f"  Poll: {POLL_INTERVAL}s")
    print(f"  API:  http://localhost:{PORT}/api/usage")
    print()

    t = threading.Thread(target=polling_loop, daemon=True)
    t.start()

    # Start version check thread (runs once immediately, then hourly)
    v = threading.Thread(target=update_check_loop, daemon=True)
    v.start()

    # Anonymous usage ping (daily)
    p = threading.Thread(target=ping_loop, daemon=True)
    p.start()

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
