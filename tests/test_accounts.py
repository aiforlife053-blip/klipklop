import json
import os
from pathlib import Path

from auth_store import AuthStore
from job_manager import WebJobManager


def test_sqlite_auth_and_session(tmp_path):
    store = AuthStore(tmp_path / "auth.sqlite3", session_ttl=60)
    user_id = store.add_user("user@example.test", "unique-password-123")
    assert store.authenticate("USER@example.test", "unique-password-123") == user_id
    assert store.authenticate("user@example.test", "wrong-password") == ""
    token = store.create_session(user_id)
    assert store.session_user(token) == user_id
    store.delete_session(token)
    assert store.session_user(token) == ""
    assert oct(os.stat(tmp_path / "auth.sqlite3").st_mode & 0o777) == "0o600"


def _clip(root, index, status="ready_to_schedule"):
    folder = root / "output" / f"run-{index:02d}" / f"clip-{index:02d}"
    folder.mkdir(parents=True)
    (folder / "master.mp4").write_bytes(b"video")
    (folder / "data.json").write_text(json.dumps({
        "clip_id": f"clip-{index:02d}",
        "created_at": f"2026-01-{index:02d}T00:00:00+00:00",
        "status": status,
    }), encoding="utf-8")
    return folder


def test_sixteenth_clip_removes_oldest_safe_clip(tmp_path):
    manager = WebJobManager(tmp_path)
    oldest = _clip(tmp_path, 1, "uploading")
    second = _clip(tmp_path, 2)
    for index in range(3, 17):
        _clip(tmp_path, index)
    manager._enforce_clip_limit()
    assert oldest.exists()
    assert not second.exists()
    assert len(list((tmp_path / "output").glob("*/**/data.json"))) == 15


def test_clip_limit_is_per_account(tmp_path):
    first = WebJobManager(tmp_path / "a")
    second = WebJobManager(tmp_path / "b")
    for index in range(1, 17):
        _clip(first.app_dir, index)
    foreign = _clip(second.app_dir, 1)
    first._enforce_clip_limit()
    assert foreign.exists()