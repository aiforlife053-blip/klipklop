import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("web_klip_job_manager_m4", ROOT / "job_manager.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def make_clip(tmp_path, clip_id="clip", status="ready_to_schedule", **extra):
    clip = tmp_path / "output" / "run" / clip_id
    clip.mkdir(parents=True)
    (clip / "master.mp4").write_bytes(b"final")
    metadata = {"clip_id": clip_id, "status": status, "title": "Judul", "description": "Desc", **extra}
    path = clip / "data.json"
    path.write_text(json.dumps(metadata), encoding="utf-8")
    return path


def wib_after(minutes):
    return (datetime.now(ZoneInfo("Asia/Jakarta")) + timedelta(minutes=minutes)).replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")


def test_schedule_rejects_less_than_ten_minutes(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    make_clip(tmp_path)
    result = manager.schedule_clip_upload({"clip_id": "clip", "scheduled_at": wib_after(5), "title": "Judul"})
    assert result == {"status": "error", "message": "Jadwal minimal 10 menit dari sekarang (WIB)"}


def test_schedule_accepts_more_than_ten_minutes_as_utc(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    path = make_clip(tmp_path)
    result = manager.schedule_clip_upload({"clip_id": "clip", "scheduled_at": wib_after(15), "title": "Judul"})
    assert result["status"] == "scheduled"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["status"] == "scheduled"
    assert saved["youtube_upload"]["scheduled_at"].endswith("+00:00")


def test_immediate_upload_is_disabled(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    make_clip(tmp_path)
    result = manager.upload_clip_now({"clip_id": "clip"})
    assert result["status"] == "error"
    assert "10 menit" in result["message"]


def test_hook_edit_queues_locked_rerender(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    path = make_clip(tmp_path)
    calls = []
    monkeypatch.setattr(manager, "render_clip", lambda payload, preview=False: calls.append((payload, preview)) or {"status": "render_queued"})
    result = manager.update_hook_text({"clip_id": "clip", "hook_text": "Ini Hook Baru Yang Sangat Kuat"})
    assert result["status"] == "render_queued"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["hook_text"] == "Ini Hook Baru\nYang Sangat Kuat"
    assert saved["status"] == "needs_edit"
    assert calls == [({"clip_id": "clip", "hook_text": "Ini Hook Baru\nYang Sangat Kuat"}, False)]


def test_hook_edit_rejects_more_than_eight_words(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    path = make_clip(tmp_path)
    monkeypatch.setattr(manager, "render_clip", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not render")))
    result = manager.update_hook_text({"clip_id": "clip", "hook_text": "satu dua tiga empat lima enam tujuh delapan sembilan"})
    assert result == {"status": "error", "message": "Hook maksimal 8 kata"}
    assert "hook_text" not in json.loads(path.read_text(encoding="utf-8"))


def test_cancel_active_clip_persists_cancelled(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    path = make_clip(tmp_path, status="render_queued")
    result = manager.cancel_clip_process({"clip_id": "clip"})
    assert result["status"] == "cancelled"
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "cancelled"


def test_upload_retry_returns_to_schedule_with_text(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    path = make_clip(tmp_path, status="upload_error", youtube_upload={"title": "Retry", "description": "Tetap"})
    result = manager.retry_clip_upload({"clip_id": "clip", "upload_now": True})
    assert result["status"] == "ready"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["status"] == "ready_to_schedule"
    assert saved["pending_youtube_upload"] == {"title": "Retry", "description": "Tetap"}
    assert "youtube_upload" not in saved
