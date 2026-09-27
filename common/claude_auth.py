"""Load Claude Code CLI credentials and fetch usage via OAuth API."""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

KEYCHAIN_SERVICE = "Claude Code-credentials"
OAUTH_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"


class ClaudeRateLimitError(Exception):
    """The usage endpoint answered 429. `retry_after` is seconds (or None)."""

    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


def _parse_retry_after(headers):
    """Return Retry-After as seconds, accepting delta-seconds or an HTTP-date."""
    if not headers:
        return None
    value = headers.get("Retry-After") or headers.get("retry-after")
    if not value:
        return None
    value = value.strip()
    try:
        return max(0, int(float(value)))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime

        when = parsedate_to_datetime(value)
        return max(0, int(when.timestamp() - time.time()))
    except Exception:
        return None


def _raise_for_http_error(e, suffix=""):
    body = e.read().decode(errors="replace")[:200]
    if e.code == 429:
        raise ClaudeRateLimitError(
            f"Claude OAuth HTTP 429: {body}", _parse_retry_after(e.headers)
        ) from e
    raise Exception(f"Claude OAuth HTTP {e.code}: {body}{suffix}") from e


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
        import getpass

        try:
            login_user = getpass.getuser()
        except Exception:
            login_user = None

        # Several generic-password items can share this service name — e.g. an
        # "claude-code-user" account that only holds mcpOAuth tokens sitting
        # alongside the real login item (stored under the macOS username). A
        # bare lookup returns an arbitrary match, so probe candidate accounts
        # and prefer the record that actually carries the claudeAiOauth token.
        fallback = None
        for account in (login_user, "claude-code-user", None):
            cmd = ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE]
            if account:
                cmd += ["-a", account]
            cmd += ["-w"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode != 0 or not result.stdout.strip():
                continue
            try:
                record = json.loads(result.stdout.strip())
            except (ValueError, TypeError):
                continue
            if isinstance(record, dict) and record.get("claudeAiOauth"):
                return record, "keychain"
            if fallback is None:
                fallback = record
        if fallback is not None:
            return fallback, "keychain"

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


def load_claude_credentials():
    record, _source = load_claude_credentials_record()
    if not record:
        raise Exception(
            "Claude CLI auth not found — run `claude login` (uses OS keychain or ~/.claude/.credentials.json)"
        )

    creds = _parse_credentials_record(record)
    if _token_is_expired(creds):
        # Active CLI sessions refresh the keychain/file in the background. Re-read
        # before failing — do not refresh here (refresh tokens are single-use and
        # would race with a running `claude` session).
        record, _ = load_claude_credentials_record()
        if record:
            creds = _parse_credentials_record(record)
        if _token_is_expired(creds):
            raise Exception(
                "Claude token expired — keep your CLI session open or run `claude login` again"
            )
    return creds


def has_claude_credentials():
    record, _ = load_claude_credentials_record()
    if not record:
        return False
    try:
        _parse_credentials_record(record)
        return True
    except Exception:
        return False


def get_claude_auth_status():
    record, source = load_claude_credentials_record()
    status = {
        "has_claude_cli_auth": record is not None,
        "claude_auth_source": source,
        "claude_config_dir": get_claude_config_dir(),
    }
    if record:
        try:
            creds = _parse_credentials_record(record)
            expires_at = creds.get("expires_at") or 0
            if expires_at:
                status["claude_token_expires_at"] = expires_at
                status["claude_token_expired"] = _token_is_expired(creds)
            status["claude_subscription"] = creds.get("subscription_type")
        except Exception:
            pass
    return status


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
                "Content-Type": "application/json",
                "anthropic-beta": "oauth-2025-04-20",
                "User-Agent": "ai-usage-widget/1.0",
            },
            method="GET",
        )

    try:
        with urllib.request.urlopen(_request(creds["access_token"]), timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code not in (401, 403):
            _raise_for_http_error(e)
        # The CLI may have rotated the token since we read it; re-read once.
        record, _ = load_claude_credentials_record()
        if not record:
            _raise_for_http_error(e)
        creds = _parse_credentials_record(record)
        try:
            with urllib.request.urlopen(_request(creds["access_token"]), timeout=15) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e2:
            _raise_for_http_error(e2, " — keep your CLI session open")

    data["timestamp"] = datetime.utcnow().isoformat() + "Z"
    data["error"] = None
    data["auth_source"] = "cli"
    if creds.get("subscription_type") and not data.get("plan_type"):
        data["plan_type"] = creds["subscription_type"]
    return data
