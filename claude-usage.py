#!/usr/bin/env python3
"""
Claude Usage Monitor — Backend
Polls claude.ai usage via Chrome AppleScript bridge.
Serves usage data via local HTTP on port 9113.
"""

import subprocess
import json
import threading
import time
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

ORG_ID = os.environ.get("CLAUDE_ORG_ID", "")
POLL_INTERVAL = int(os.environ.get("CLAUDE_POLL_INTERVAL", "60"))
PORT = int(os.environ.get("CLAUDE_WIDGET_PORT", "9113"))

usage_data = {"error": "Starting up...", "timestamp": None}
usage_lock = threading.Lock()


def fetch_via_chrome(url):
    """Use AppleScript to run fetch() inside an existing claude.ai tab.
    Writes result to document.title and reads it back."""
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


def detect_org_id():
    """Try to detect the org ID from an existing claude.ai tab."""
    script = '''
    tell application "Google Chrome"
        set foundTab to null
        repeat with w in windows
            repeat with t in tabs of w
                if URL of t starts with "https://claude.ai" then
                    set foundTab to t
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
        set jsCode to "fetch('/api/organizations', {credentials:'include'}).then(r=>r.text()).then(t=>{document.title='FETCHOK:'+t.substring(0,8000)}).catch(e=>{document.title='FETCHERR:'+e.message})"
        execute foundTab javascript jsCode
        delay 4
        set resultTitle to name of foundTab
        execute foundTab javascript "document.title='" & origTitle & "'"
        return resultTitle
    end tell
    '''
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=30,
    )
    output = result.stdout.strip()
    if output.startswith("FETCHOK:"):
        orgs = json.loads(output[8:])
        if orgs and len(orgs) > 0:
            return orgs[0].get("uuid") or orgs[0].get("id")
    return None


def collect_usage():
    """Fetch usage data from claude.ai."""
    url = f"https://claude.ai/api/organizations/{ORG_ID}/usage"
    raw = fetch_via_chrome(url)
    data = json.loads(raw)
    data["timestamp"] = datetime.utcnow().isoformat() + "Z"
    data["error"] = None
    return data


def polling_loop():
    global usage_data
    while True:
        try:
            data = collect_usage()
            with usage_lock:
                usage_data = data
        except Exception as e:
            with usage_lock:
                usage_data["error"] = str(e)
                usage_data["timestamp"] = datetime.utcnow().isoformat() + "Z"
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
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def main():
    global ORG_ID

    if not ORG_ID:
        print("No CLAUDE_ORG_ID set. Attempting auto-detection from Chrome...")
        detected = detect_org_id()
        if detected:
            ORG_ID = detected
            print(f"  Detected org: {ORG_ID}")
        else:
            print("ERROR: Could not detect org ID.")
            print("Set CLAUDE_ORG_ID environment variable or ensure claude.ai is open in Chrome.")
            sys.exit(1)

    print(f"Claude Usage Monitor starting...")
    print(f"  Org:  {ORG_ID}")
    print(f"  Poll: {POLL_INTERVAL}s")
    print(f"  API:  http://localhost:{PORT}/api/usage")
    print()

    t = threading.Thread(target=polling_loop, daemon=True)
    t.start()

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
