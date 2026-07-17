import importlib.util
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("web_klip_job_manager_m5", ROOT / "job_manager.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

from gaming_layout import validate_roi  # noqa: E402
from layout_modes import validate_facecam_overlap  # noqa: E402


def make_clip(tmp_path, clip_id="clip", status="needs_edit", **extra):
    clip = tmp_path / "output" / "run" / clip_id
    clip.mkdir(parents=True)
    (clip / "source.mp4").write_bytes(b"source")
    if extra.pop("with_master", False) or status in {"ready_to_schedule", "scheduled", "uploaded"}:
        (clip / "master.mp4").write_bytes(b"final")
    metadata = {"clip_id": clip_id, "status": status, "title": "Judul", **extra}
    path = clip / "data.json"
    path.write_text(json.dumps(metadata), encoding="utf-8")
    return path


def test_validate_roi_rejects_non_finite_and_out_of_frame():
    assert validate_roi({"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2}) == {
        "x": 0.1,
        "y": 0.1,
        "width": 0.2,
        "height": 0.2,
    }
    assert validate_roi({"x": math.nan, "y": 0.1, "width": 0.2, "height": 0.2}) is None
    assert validate_roi({"x": 0.1, "y": 0.1, "width": math.inf, "height": 0.2}) is None
    assert validate_roi({"x": 0.9, "y": 0.1, "width": 0.2, "height": 0.2}) is None
    assert validate_roi({"x": -0.1, "y": 0.1, "width": 0.2, "height": 0.2}) is None
    assert validate_roi("bad") is None


def test_submit_facecam_roi_rejects_non_finite(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    make_clip(
        tmp_path,
        status="needs_facecam",
        source_geometry={"width": 1920, "height": 1080, "is_landscape": True},
    )
    result = manager.submit_facecam_roi(
        {
            "clip_id": "clip",
            "x": "nan",
            "y": 0.05,
            "width": 0.2,
            "height": 0.2,
        }
    )
    assert result == {"status": "error", "message": "ROI facecam tidak valid"}


def test_managers_cannot_read_other_user_clip_meta(tmp_path):
    alice_dir = tmp_path / "alice"
    bob_dir = tmp_path / "bob"
    alice = mod.WebJobManager(app_dir=alice_dir, user_id="11111111-1111-1111-1111-111111111111", local_mode=True)
    bob = mod.WebJobManager(app_dir=bob_dir, user_id="22222222-2222-2222-2222-222222222222", local_mode=True)
    make_clip(alice_dir, clip_id="secret", status="ready_to_schedule", with_master=True)
    assert alice._clip_meta("secret")[0] is not None
    assert bob._clip_meta("secret")[0] is None
    assert bob.clip_artifact("secret", "final") is None
    assert bob.get_clip("secret")["status"] == "error"


def test_extract_clip_frame_rejects_invalid_seek(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    make_clip(tmp_path, duration_seconds=10)
    data, err = manager.extract_clip_frame("clip", "nan")
    assert data is None and "tidak valid" in err
    data, err = manager.extract_clip_frame("clip", float("inf"))
    assert data is None and "tidak valid" in err
    data, err = manager.extract_clip_frame("missing", 0)
    assert data is None and "tidak ditemukan" in err


def test_cancel_sets_event_and_removes_temp_render_files(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    path = make_clip(tmp_path, status="rendering")
    temp = path.parent / "master.abc123.tmp.mp4"
    preview = path.parent / "preview-deadbeefcafe.mp4"
    temp.write_bytes(b"temp")
    preview.write_bytes(b"prev")
    result = manager.cancel_clip_process({"clip_id": "clip"})
    assert result["status"] == "cancelled"
    assert manager._cancel_event("clip").is_set()
    assert not temp.exists()
    assert not preview.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "cancelled"


def test_preview_artifact_no_longer_served(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    path = make_clip(tmp_path)
    preview = path.parent / "preview-aaaaaaaaaaaa.mp4"
    preview.write_bytes(b"x" * 100)
    assert manager.clip_artifact("clip", "preview", "aaaaaaaaaaaa") is None


def test_validate_facecam_overlap_rejects_center_roi():
    center = {"x": 0.4, "y": 0.1, "width": 0.2, "height": 0.2}
    edge = {"x": 0.01, "y": 0.05, "width": 0.15, "height": 0.2}
    assert validate_facecam_overlap(edge, 1920, 1080) is True
    assert validate_facecam_overlap(center, 1920, 1080) is False


def test_transcript_path_is_jailed_to_clip_directory(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    path = make_clip(tmp_path, transcript_path="../../secret.json")
    safe = manager._safe_transcript_path(path.parent, json.loads(path.read_text(encoding="utf-8")))
    assert safe == (path.parent / "transcript.json").resolve()
    assert safe.parent == path.parent.resolve()


def test_upload_description_is_capped_to_youtube_limit(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    metadata = {}
    title, description = manager._upload_text({"title": "x" * 200, "description": "y" * 100_000}, metadata)
    assert len(title) == 100
    assert len(description) == 5000
    assert metadata == {"title": title, "description": description}


def test_non_finite_float_defaults_safely(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    assert manager._as_float("nan", 7.0) == 7.0
    assert manager._as_float("inf", 7.0) == 7.0
    assert manager._as_float("-inf", 7.0) == 7.0


def test_raw_path_media_routes_are_removed():
    source = (ROOT / "server.py").read_text(encoding="utf-8")
    assert 'elif parsed.path in {"/api/download", "/api/stream"}' in source
    assert "raw path= removed" in source
    assert 'allowed = media | text' in source
    assert 'text = {".json", ".srt", ".ass", ".txt", ".vtt"} if allow_text else set()' in source
