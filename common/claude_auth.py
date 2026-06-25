"""Load Claude Code CLI credentials and fetch usage via OAuth API."""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

KEYCHAIN_SERVICE = "Claude Code-credentials"
OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
OAUTH_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"


def get_claude_config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def _credentials_path():
    return os.path.join(get_claude_config_dir(), ".credentials.json")


def _parse_credentials_record(record):
    oauth = record.get("claudeAiOauth")
    if not oauth:
        raise Exception("No Claude OAuth credentials — run `claude login` in Terminal")

    access_token = oauth.get("accessToken")
    if not access_token:
        raise Exception("No Claude access token — run `claude login`")

    return {
        "access_token": access_token,
        "refresh_token": oauth.get("refreshToken"),
        "expires_at": oauth.get("expiresAt") or 0,
        "subscription_type": oauth.get("subscriptionType"),
        "rate_limit_tier": oauth.get("rateLimitTier"),
        "scopes": oauth.get("scopes") or [],
    }


def _load_from_file():
    path = _credentials_path()
    if not os.path.exists(path):
        return None, None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f), "file"


def _load_from_keychain():
    if sys.platform == "darwin":
        result = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip()), "keychain"

    try:
        import keyring

        for account in ("Claude Code", "default", ""):
            value = keyring.get_password(KEYCHAIN_SERVICE, account)
            if value:
                return json.loads(value), "keyring"
    except Exception:
        pass

    return None, None


def load_claude_credentials_record():
    """Return (record_dict, source) where source is keychain, file, or None."""
    if sys.platform == "darwin":
        record, source = _load_from_keychain()
        if record:
            return record, source

    record, source = _load_from_file()
    if record:
        return record, source

    if sys.platform != "darwin":
        record, source = _load_from_keychain()
        if record:
            return record, source

    return None, None


def _token_is_expired(creds):
    expires_at = creds.get("expires_at") or 0
    return expires_at > 0 and expires_at < int(time.time() * 1000)


def _save_refreshed_tokens(creds, token_response):
    path = _credentials_path()
    record = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            record = json.load(f)

    oauth = dict(record.get("claudeAiOauth") or {})
    oauth["accessToken"] = token_response["access_token"]
    if token_response.get("refresh_token"):
        oauth["refreshToken"] = token_response["refresh_token"]
    expires_in = token_response.get("expires_in")
    if expires_in:
        oauth["expiresAt"] = int(time.time() * 1000) + int(expires_in) * 1000
    record["claudeAiOauth"] = oauth

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass

    creds["access_token"] = oauth["accessToken"]
    creds["refresh_token"] = oauth.get("refreshToken")
    creds["expires_at"] = oauth.get("expiresAt") or 0


def _refresh_access_token(creds):
    refresh_token = creds.get("refresh_token")
    if not refresh_token:
        raise Exception("Claude token expired — run `claude` once to refresh")

    payload = json.dumps({
        "grant_type": "refresh_token",
        "client_id": OAUTH_CLIENT_ID,
        "refresh_token": refresh_token,
    }).encode()
    req = urllib.request.Request(
        OAUTH_TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            token_response = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:200]
        raise Exception(f"Claude token refresh failed — run `claude login` ({body})") from e

    _save_refreshed_tokens(creds, token_response)
    return creds


def load_claude_credentials():
    record, _source = load_claude_credentials_record()
    if not record:
        raise Exception(
            "Claude CLI auth not found — run `claude login` (uses OS keychain or ~/.claude/.credentials.json)"
        )

    creds = _parse_credentials_record(record)
    if _token_is_expired(creds):
        creds = _refresh_access_token(creds)
    return creds


def has_claude_credentials():
    try:
        load_claude_credentials()
        return True
    except Exception:
        return False


def get_claude_auth_status():
    record, source = load_claude_credentials_record()
    return {
        "has_claude_cli_auth": record is not None,
        "claude_auth_source": source,
        "claude_config_dir": get_claude_config_dir(),
    }


def fetch_claude_oauth_usage():
    """Fetch Claude usage via Claude Code OAuth API."""
    from datetime import datetime

    creds = load_claude_credentials()
    scopes = creds.get("scopes") or []
    if scopes and "user:profile" not in scopes:
        raise Exception("Claude token missing user:profile scope — run `claude login` again")

    def _request(token):
        return urllib.request.Request(
            OAUTH_USAGE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "anthropic-beta": "oauth-2025-04-20",
                "anthropic-version": "2023-06-01",
            },
            method="GET",
        )

    req = _request(creds["access_token"])
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401 and creds.get("refresh_token"):
            creds = _refresh_access_token(creds)
            with urllib.request.urlopen(_request(creds["access_token"]), timeout=15) as resp:
                data = json.loads(resp.read().decode())
        else:
            body = e.read().decode(errors="replace")[:200]
            raise Exception(f"Claude OAuth HTTP {e.code}: {body}") from e

    data["timestamp"] = datetime.utcnow().isoformat() + "Z"
    data["error"] = None
    data["auth_source"] = "cli"
    if creds.get("subscription_type") and not data.get("plan_type"):
        data["plan_type"] = creds["subscription_type"]
    return data
