import json
import os
import secrets
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

ROOT = Path(__file__).resolve().parent
TOKEN_DIR = ROOT / "data"
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_STATE_TTL = 600
_states = {}
_auth_lock = threading.Lock()


def _require_user(user_id):
    import uuid
    return str(uuid.UUID(str(user_id)))


def _client_config():
    client_id = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    callback = os.environ.get("YOUTUBE_REDIRECT_URI", "").strip()
    if not client_id or not client_secret or not callback.startswith("https://"):
        raise RuntimeError("YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and HTTPS YOUTUBE_REDIRECT_URI are required")
    return client_id, client_secret, callback


def _fernet():
    key = os.environ.get("TOKEN_ENCRYPTION_KEY", "").encode()
    if not key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is required")
    try:
        return Fernet(key)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc


def _token_file(user_id):
    user_id = _require_user(user_id)
    folder = TOKEN_DIR / user_id / "config"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "youtube_token.enc"


def _save_credentials(user_id, creds):
    target = _token_file(user_id)
    target.write_bytes(_fernet().encrypt(creds.to_json().encode()))


def _load_credentials(user_id):
    target = _token_file(user_id)
    try:
        raw = _fernet().decrypt(target.read_bytes()).decode()
    except FileNotFoundError:
        return None
    except InvalidToken as exc:
        raise RuntimeError("Stored YouTube credentials cannot be decrypted") from exc
    return Credentials.from_authorized_user_info(json.loads(raw), SCOPES)


def _exchange_code(code, redirect_uri, client_id, client_secret):
    body = urllib.parse.urlencode({"code": code, "client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri, "grant_type": "authorization_code"}).encode()
    request = urllib.request.Request(TOKEN_ENDPOINT, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def start_youtube_oauth(user_id):
    user_id = _require_user(user_id)
    client_id, _, callback = _client_config()
    state = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _auth_lock:
        for key, transaction in list(_states.items()):
            if transaction["expires"] <= now:
                _states.pop(key, None)
        _states[state] = {"user_id": user_id, "expires": now + _STATE_TTL, "status": "waiting", "error": None}
    params = urllib.parse.urlencode({"client_id": client_id, "redirect_uri": callback, "response_type": "code", "scope": " ".join(SCOPES), "access_type": "offline", "include_granted_scopes": "true", "prompt": "consent", "state": state})
    return {"status": "waiting", "auth_url": f"{AUTH_ENDPOINT}?{params}"}


def finish_youtube_oauth(state, code=None, error=None):
    with _auth_lock:
        transaction = _states.pop(str(state), None)
    if not transaction or transaction["expires"] <= time.monotonic():
        raise ValueError("Invalid or expired OAuth state")
    user_id = transaction["user_id"]
    if error or not code:
        raise ValueError(str(error or "Missing OAuth code"))
    client_id, client_secret, callback = _client_config()
    token = _exchange_code(code, callback, client_id, client_secret)
    creds = Credentials(token=token.get("access_token"), refresh_token=token.get("refresh_token"), token_uri=TOKEN_ENDPOINT, client_id=client_id, client_secret=client_secret, scopes=SCOPES)
    _save_credentials(user_id, creds)
    return user_id


def check_youtube_oauth_status(user_id):
    user_id = _require_user(user_id)
    now = time.monotonic()
    with _auth_lock:
        waiting = any(item["user_id"] == user_id and item["expires"] > now for item in _states.values())
    return {"status": "waiting" if waiting else ("connected" if is_youtube_connected(user_id)["connected"] else "idle"), "error": None}


def get_youtube_credentials(user_id):
    creds = _load_credentials(user_id)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(user_id, creds)
        return creds
    raise FileNotFoundError("Token tidak ditemukan atau expired. Silakan Connect ulang.")


def delete_youtube_token(user_id):
    _token_file(user_id).unlink(missing_ok=True)


def is_youtube_connected(user_id):
    try:
        creds = _load_credentials(user_id)
        connected = bool(creds and creds.refresh_token)
        result = {"connected": connected, "expired": bool(creds and creds.expired)}
        if connected:
            try:
                from googleapiclient.discovery import build
                response = build("youtube", "v3", credentials=get_youtube_credentials(user_id), cache_discovery=False).channels().list(part="snippet", mine=True).execute()
                channel = next(iter(response.get("items", [])), {})
                result["channel_id"] = channel.get("id", "")
                result["channel_title"] = channel.get("snippet", {}).get("title", "")
            except Exception:
                pass
        return result
    except Exception:
        return {"connected": False}
