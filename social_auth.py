import os
import json
import socket
import secrets
import threading
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

ROOT = Path(__file__).resolve().parent
CLIENT_SECRET_FILE = str(ROOT / "client_secret.json")
TOKEN_FILE = str(ROOT / "token_youtube.json")
TOKEN_DIR = ROOT / "tokens"
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

# Non-blocking OAuth state
_auth_state = {"status": "idle", "auth_url": None, "error": None}
_auth_lock = threading.Lock()

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


def _token_file(user_key=None):
    if not user_key:
        return TOKEN_FILE
    safe = ''.join(ch if ch.isalnum() else '_' for ch in str(user_key).lower()).strip('_')[:120] or 'user'
    TOKEN_DIR.mkdir(exist_ok=True)
    return str(TOKEN_DIR / f"youtube_{safe}.json")


def _load_client_config():
    with open(CLIENT_SECRET_FILE, "r") as f:
        data = json.load(f)
    wc = data.get("web") or data.get("installed")
    if not wc:
        raise ValueError("client_secret.json format tidak dikenali")
    return wc


def _find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("localhost", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _CallbackHandler(BaseHTTPRequestHandler):
    auth_code = None
    error = None
    expected_state = None

    def do_GET(self):
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        state = params.get("state", [""])[0]
        if not secrets.compare_digest(state, _CallbackHandler.expected_state or ""):
            _CallbackHandler.error = "invalid_state"
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body><h2>Invalid OAuth state. Please reconnect.</h2></body></html>")
        elif "code" in params:
            _CallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body><h2>YouTube connected! You can close this tab.</h2></body></html>")
        elif "error" in params:
            _CallbackHandler.error = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<html><body><h2>Error: {_CallbackHandler.error}</h2></body></html>".encode())
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, fmt, *args):
        return


def _exchange_code(code, redirect_uri, client_id, client_secret):
    import urllib.request
    body = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(TOKEN_ENDPOINT, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def start_youtube_oauth(user_key=None) -> dict:
    """Generate OAuth URL and start local callback server in background. Returns immediately."""
    with _auth_lock:
        if _auth_state.get("status") == "waiting":
            return {"status": "waiting", "auth_url": _auth_state["auth_url"]}

    wc = _load_client_config()
    client_id = wc["client_id"]
    client_secret = wc["client_secret"]
    port = _find_free_port()
    redirect_uri = f"http://localhost:{port}/"

    oauth_state = secrets.token_urlsafe(24)
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": oauth_state,
    })
    auth_url = f"{AUTH_ENDPOINT}?{params}"

    with _auth_lock:
        _auth_state["status"] = "waiting"
        _auth_state["auth_url"] = auth_url
        _auth_state["error"] = None

    def _run():
        server = None
        try:
            _CallbackHandler.auth_code = None
            _CallbackHandler.error = None
            _CallbackHandler.expected_state = oauth_state
            server = HTTPServer(("localhost", port), _CallbackHandler)
            server.timeout = 1
            deadline = time.monotonic() + 120
            while _CallbackHandler.auth_code is None and _CallbackHandler.error is None and time.monotonic() < deadline:
                server.handle_request()

            if _CallbackHandler.error or not _CallbackHandler.auth_code:
                with _auth_lock:
                    _auth_state["status"] = "error"
                    _auth_state["error"] = _CallbackHandler.error or "OAuth timeout. Silakan connect ulang."
                return

            token_data = _exchange_code(_CallbackHandler.auth_code, redirect_uri, client_id, client_secret)
            creds = Credentials(
                token=token_data.get("access_token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri=TOKEN_ENDPOINT,
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES,
            )
            token_file = _token_file(user_key)
            with open(token_file, "w") as f:
                f.write(creds.to_json())
            print(f"Token disimpan di {token_file}")
            with _auth_lock:
                _auth_state["status"] = "connected"
        except Exception as e:
            with _auth_lock:
                _auth_state["status"] = "error"
                _auth_state["error"] = str(e)
        finally:
            if server:
                server.server_close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"status": "waiting", "auth_url": auth_url}


def check_youtube_oauth_status() -> dict:
    with _auth_lock:
        return {"status": _auth_state["status"], "error": _auth_state.get("error")}


def get_youtube_credentials(user_key=None) -> Credentials:
    creds = None
    token_file = _token_file(user_key)
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_file, "w") as f:
            f.write(creds.to_json())
        return creds
    raise FileNotFoundError("Token tidak ditemukan atau expired. Silakan Connect ulang.")


def delete_youtube_token(user_key=None):
    token_file = _token_file(user_key)
    if os.path.exists(token_file):
        os.remove(token_file)


def is_youtube_connected(user_key=None) -> dict:
    token_file = _token_file(user_key)
    if not os.path.exists(token_file):
        return {"connected": False}
    try:
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        return {"connected": bool(creds.refresh_token), "expired": bool(creds.expired)}
    except Exception as e:
        return {"connected": False, "error": str(e)}


if __name__ == "__main__":
    print("Menghubungkan ke YouTube...")
    creds = get_youtube_credentials()
    print("Berhasil! Token tersimpan.")
