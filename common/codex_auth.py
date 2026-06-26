"""Load Codex CLI credentials from auth.json or the OS keyring."""

import base64
import hashlib
import json
import os
import re
import subprocess
import sys

KEYRING_SERVICE = "Codex Auth"


def get_codex_home():
    return os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")


def _auth_file_path(codex_home=None):
    return os.path.join(codex_home or get_codex_home(), "auth.json")


def _compute_keyring_account(codex_home):
    canonical = os.path.realpath(codex_home)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"cli|{digest[:16]}"


def _read_credentials_store_mode(codex_home):
    config_path = os.path.join(codex_home, "config.toml")
    if not os.path.exists(config_path):
        return "auto"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                match = re.match(
                    r'^\s*cli_auth_credentials_store\s*=\s*"?(file|keyring|auto|ephemeral)"?',
                    line,
                )
                if match:
                    return match.group(1)
    except OSError:
        pass
    return "auto"


def _decode_jwt_payload(token):
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload + padding))
    except Exception:
        return {}


def _extract_credentials(auth):
    auth_mode = auth.get("auth_mode")
    tokens = auth.get("tokens") or {}

    if auth_mode == "api" and not tokens:
        raise Exception("Codex is using API key auth — run `codex login` with ChatGPT for usage limits")

    access_token = tokens.get("access_token")
    if not access_token:
        raise Exception("No Codex access token found — run `codex login`")

    account_id = tokens.get("account_id")
    if not account_id:
        id_token = tokens.get("id_token")
        if isinstance(id_token, str) and id_token:
            claims = _decode_jwt_payload(id_token)
            auth_claims = claims.get("https://api.openai.com/auth", {})
            account_id = auth_claims.get("chatgpt_account_id") or auth_claims.get("user_id")

    return access_token, account_id


def _load_from_file(codex_home):
    auth_path = _auth_file_path(codex_home)
    if not os.path.exists(auth_path):
        return None, None
    with open(auth_path, "r", encoding="utf-8") as f:
        return json.load(f), "file"


def _load_from_keyring(codex_home):
    account = _compute_keyring_account(codex_home)

    try:
        import keyring

        value = keyring.get_password(KEYRING_SERVICE, account)
        if value:
            return json.loads(value), "keyring"
    except Exception:
        pass

    if sys.platform == "darwin":
        result = subprocess.run(
            ["security", "find-generic-password", "-s", KEYRING_SERVICE, "-a", account, "-w"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip()), "keyring"

    return None, None


def load_codex_auth_record():
    """Return (auth_dict, source) where source is 'file', 'keyring', or None."""
    codex_home = get_codex_home()
    mode = _read_credentials_store_mode(codex_home)

    if mode == "file":
        return _load_from_file(codex_home)
    if mode == "keyring":
        return _load_from_keyring(codex_home)

    auth, source = _load_from_keyring(codex_home)
    if auth:
        return auth, source
    return _load_from_file(codex_home)


def load_codex_credentials():
    auth, _source = load_codex_auth_record()
    if not auth:
        raise Exception(
            "Codex auth not found — run `codex login` (credentials may be in the OS keyring or ~/.codex/auth.json)"
        )
    return _extract_credentials(auth)


def has_codex_credentials():
    try:
        load_codex_credentials()
        return True
    except Exception:
        return False


def get_codex_auth_status():
    codex_home = get_codex_home()
    mode = _read_credentials_store_mode(codex_home)
    auth, source = load_codex_auth_record()
    status = {
        "has_codex_auth": auth is not None,
        "codex_auth_source": source,
        "codex_home": codex_home,
        "codex_credentials_store": mode,
    }
    if mode == "ephemeral":
        status["codex_ephemeral"] = True
    return status
