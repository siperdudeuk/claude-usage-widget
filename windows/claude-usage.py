#!/usr/bin/env python3
"""
Claude Usage Monitor — Backend (Windows)
Fetches claude.ai usage data and serves it via local HTTP on port 9113.

Auth method: Direct cookie extraction from Chrome's cookie store using DPAPI.
"""

import json
import threading
import time
import os
import sys
import sqlite3
import shutil
import subprocess
import tempfile
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
REPO_DIR = os.path.dirname(SCRIPT_DIR)

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

_fetch_method = None
_session_cookie = None
_cookie_last_refreshed = 0
COOKIE_REFRESH_INTERVAL = 300


# ---------------------------------------------------------------------------
# Chrome cookie extraction on Windows (DPAPI + AES-256-GCM)
# ---------------------------------------------------------------------------

def _get_chrome_encryption_key():
    """Get Chrome's AES encryption key from Local State, decrypted via DPAPI."""
    import ctypes
    import ctypes.wintypes

    local_state_path = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Google", "Chrome", "User Data", "Local State"
    )
    if not os.path.exists(local_state_path):
        raise Exception("Chrome Local State not found")

    with open(local_state_path, "r", encoding="utf-8") as f:
        local_state = json.loads(f.read())

    encrypted_key_b64 = local_state["os_crypt"]["encrypted_key"]
    encrypted_key = base64.b64decode(encrypted_key_b64)

    # Remove "DPAPI" prefix (first 5 bytes)
    encrypted_key = encrypted_key[5:]

    # Decrypt using Windows DPAPI
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", ctypes.wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    blob_in = DATA_BLOB(len(encrypted_key), ctypes.create_string_buffer(encrypted_key, len(encrypted_key)))
    blob_out = DATA_BLOB()

    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise Exception("DPAPI decryption failed — are you running as the correct user?")

    key = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return key


def _decrypt_chrome_cookie(encrypted_value, key):
    """Decrypt a Chrome cookie value on Windows (AES-256-GCM)."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise Exception("cryptography package not installed — run: pip install cryptography")

    if encrypted_value[:3] == b"v10" or encrypted_value[:3] == b"v11":
        # v10/v11: AES-256-GCM
        nonce = encrypted_value[3:15]
        ciphertext = encrypted_value[15:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
    else:
        # Old DPAPI-only encryption (pre-v80)
        import ctypes
        import ctypes.wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", ctypes.wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char)),
            ]

        blob_in = DATA_BLOB(len(encrypted_value), ctypes.create_string_buffer(encrypted_value, len(encrypted_value)))
        blob_out = DATA_BLOB()

        if ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        ):
            result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
            return result.decode("utf-8")
        raise Exception("DPAPI cookie decryption failed")


def get_chrome_cookies():
    """Extract claude.ai session cookies from Chrome's cookie store on Windows."""
    chrome_user_data = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Google", "Chrome", "User Data"
    )
    cookie_paths = [
        os.path.join(chrome_user_data, "Default", "Network", "Cookies"),
        os.path.join(chrome_user_data, "Default", "Cookies"),
        os.path.join(chrome_user_data, "Profile 1", "Network", "Cookies"),
        os.path.join(chrome_user_data, "Profile 1", "Cookies"),
    ]

    cookie_db = None
    for p in cookie_paths:
        if os.path.exists(p):
            cookie_db = p
            break

    if not cookie_db:
        raise Exception("Chrome cookie database not found")

    key = _get_chrome_encryption_key()

    # Copy the DB to a temp file (Chrome locks it)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(tmp_fd)
    shutil.copy2(cookie_db, tmp_path)

    try:
        conn = sqlite3.connect(tmp_path)
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
        os.unlink(tmp_path)

    if not cookies:
        raise Exception("No claude.ai cookies found in Chrome — are you logged in?")

    return cookies


def fetch_via_cookies(url):
    """Make an authenticated request to claude.ai using extracted cookies."""
    global _session_cookie, _cookie_last_refreshed

    now = time.time()
    if _session_cookie is None or (now - _cookie_last_refreshed) > COOKIE_REFRESH_INTERVAL:
        cookies = get_chrome_cookies()
        cookie_parts = [f"{k}={v}" for k, v in cookies.items()]
        _session_cookie = "; ".join(cookie_parts)
        _cookie_last_refreshed = now

    req = urllib.request.Request(url, headers={
        "Cookie": _session_cookie,
        "User-Agent": "Claude-Usage-Widget/1.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def detect_org_id():
    """Detect org ID using cookie-based auth."""
    raw = fetch_via_cookies("https://claude.ai/api/organizations")
    orgs = json.loads(raw)
    if orgs and len(orgs) > 0:
        return orgs[0].get("uuid") or orgs[0].get("id")
    return None


def collect_usage():
    """Fetch usage data from claude.ai."""
    url = f"https://claude.ai/api/organizations/{ORG_ID}/usage"
    raw = fetch_via_cookies(url)
    data = json.loads(raw)
    data["timestamp"] = datetime.utcnow().isoformat() + "Z"
    data["error"] = None
    return data


# ---------------------------------------------------------------------------
# Version / update check
# ---------------------------------------------------------------------------

def _get_current_commit():
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
    global version_info
    current = _get_current_commit()
    try:
        latest = _get_latest_commit_from_github()
    except Exception:
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
    update_script = os.path.join(SCRIPT_DIR, "update.bat")
    if not os.path.exists(update_script):
        return {"success": False, "error": "update.bat not found"}
    try:
        result = subprocess.run(
            [update_script],
            capture_output=True, text=True, timeout=120, cwd=SCRIPT_DIR, shell=True,
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def polling_loop():
    global usage_data, _session_cookie, _cookie_last_refreshed
    while True:
        try:
            data = collect_usage()
            with usage_lock:
                usage_data = data
        except Exception as e:
            with usage_lock:
                usage_data["error"] = str(e)
                usage_data["timestamp"] = datetime.utcnow().isoformat() + "Z"
            if "HTTP Error 401" in str(e):
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
                "method": "cookies" if _session_cookie else None,
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
    chrome_user_data = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Google", "Chrome", "User Data"
    )
    paths = [
        os.path.join(chrome_user_data, "Default", "Network", "Cookies"),
        os.path.join(chrome_user_data, "Default", "Cookies"),
    ]
    return any(os.path.exists(p) for p in paths)


def main():
    global ORG_ID

    print("Claude Usage Monitor starting...")
    print()

    if not ORG_ID:
        print("No CLAUDE_ORG_ID set. Attempting auto-detection...")
        try:
            detected = detect_org_id()
            if detected:
                ORG_ID = detected
                print(f"  Detected org: {ORG_ID}")
            else:
                print("ERROR: Could not detect org ID.")
                print("Options:")
                print("  1. Set CLAUDE_ORG_ID environment variable")
                print("  2. Make sure you're logged into claude.ai in Chrome")
                print("  3. Install 'cryptography' package: pip install cryptography")
                sys.exit(1)
        except Exception as e:
            print(f"ERROR: {e}")
            print("Make sure Chrome is closed or you're logged into claude.ai.")
            sys.exit(1)

    print(f"  Org:  {ORG_ID}")
    print(f"  Poll: {POLL_INTERVAL}s")
    print(f"  API:  http://localhost:{PORT}/api/usage")
    print()

    t = threading.Thread(target=polling_loop, daemon=True)
    t.start()

    v = threading.Thread(target=update_check_loop, daemon=True)
    v.start()

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
