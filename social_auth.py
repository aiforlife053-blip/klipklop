import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_FILE = "token_youtube.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def get_youtube_credentials() -> Credentials:
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(creds)
        return creds

    if not os.path.exists(CLIENT_SECRET_FILE):
        raise FileNotFoundError(f"{CLIENT_SECRET_FILE} tidak ditemukan. Download dari Google Cloud Console dulu.")

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    creds = flow.run_local_server(port=0, timeout_seconds=10)
    _save_token(creds)
    return creds


def _save_token(creds: Credentials):
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    print(f"Token disimpan di {TOKEN_FILE}")


def is_youtube_connected() -> dict:
    if not os.path.exists(TOKEN_FILE):
        return {"connected": False}
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        return {"connected": bool(creds.refresh_token), "expired": bool(creds.expired)}
    except Exception as e:
        return {"connected": False, "error": str(e)}


if __name__ == "__main__":
    print("Menghubungkan ke YouTube...")
    creds = get_youtube_credentials()
    print("Berhasil! Token tersimpan.")
