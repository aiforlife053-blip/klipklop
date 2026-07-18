import hashlib
import hmac
import os
import secrets
import sqlite3
import time
import uuid
from pathlib import Path


class AuthStore:
    def __init__(self, path, session_ttl=86400):
        self.path = Path(path)
        self.session_ttl = int(session_ttl)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self):
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_hash BLOB NOT NULL,
                    password_salt BLOB NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash BLOB PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sessions_expires_at ON sessions(expires_at);
                """
            )
        os.chmod(self.path, 0o600)

    @staticmethod
    def _password_hash(password, salt):
        return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)

    @staticmethod
    def _token_hash(token):
        return hashlib.sha256(token.encode("ascii")).digest()

    def add_user(self, email, password, user_id=None):
        email = str(email or "").strip().lower()
        password = str(password or "")
        if not email or "@" not in email or len(email) > 254:
            raise ValueError("Email tidak valid")
        if len(password) < 12 or len(password.encode("utf-8")) > 1024:
            raise ValueError("Password minimal 12 karakter")
        user_id = str(uuid.UUID(str(user_id))) if user_id else str(uuid.uuid4())
        salt = secrets.token_bytes(16)
        password_hash = self._password_hash(password, salt)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO users(id, email, password_hash, password_salt, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, email, password_hash, salt, int(time.time())),
            )
        return user_id

    def authenticate(self, email, password):
        email = str(email or "").strip().lower()
        password = str(password or "")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, password_hash, password_salt FROM users WHERE email = ?",
                (email,),
            ).fetchone()
        if not row:
            self._password_hash(password, b"\0" * 16)
            return ""
        return row[0] if hmac.compare_digest(row[1], self._password_hash(password, row[2])) else ""

    def create_session(self, user_id):
        user_id = str(uuid.UUID(str(user_id)))
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            connection.execute(
                "INSERT INTO sessions(token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (self._token_hash(token), user_id, now + self.session_ttl, now),
            )
        return token

    def session_user(self, token):
        if not token:
            return ""
        now = int(time.time())
        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_id FROM sessions WHERE token_hash = ? AND expires_at > ?",
                (self._token_hash(token), now),
            ).fetchone()
        return row[0] if row else ""

    def delete_session(self, token):
        if not token:
            return
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (self._token_hash(token),))

    def user_count(self):
        with self._connect() as connection:
            return connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
