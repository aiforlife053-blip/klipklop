import json
import os
import secrets
import shutil
import uuid
from pathlib import Path

from auth_store import AuthStore


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
LEGACY_USER_ID = "00000000-0000-4000-8000-000000000001"


def migrate():
    store = AuthStore(DATA / "auth.sqlite3")
    if store.user_count():
        raise SystemExit("Accounts already exist; migration not repeated")
    credentials = []
    for index in range(1, 6):
        user_id = LEGACY_USER_ID if index == 1 else str(uuid.uuid4())
        email = f"akun{index}@klipklop.local"
        password = secrets.token_urlsafe(18)
        store.add_user(email, password, user_id)
        folder = DATA / user_id
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        if index > 1:
            source_config = DATA / LEGACY_USER_ID / "config.json"
            if source_config.is_file():
                shutil.copy2(source_config, folder / "config.json")
        credentials.append({"account": index, "email": email, "password": password, "user_id": user_id})
    target = DATA / "initial-credentials.json"
    target.write_text(json.dumps(credentials, indent=2), encoding="utf-8")
    os.chmod(target, 0o600)
    print(target)


if __name__ == "__main__":
    migrate()