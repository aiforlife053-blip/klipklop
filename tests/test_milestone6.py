"""Milestone 6 release validation: restart, batch isolation, modes, workflow."""
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("web_klip_job_manager_m6", ROOT / "job_manager.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

from layout_modes import (  # noqa: E402
    LayoutModeError,
    build_filtergraph,
    output_geometry,
    validate_orientation,
)
from visual_style import normalize_hook_text  # noqa: E402


def make_clip(tmp_path, clip_id, status="needs_edit", **extra):
    clip = tmp_path / "output" / "run" / clip_id
    clip.mkdir(parents=True)
    (clip / "source.mp4").write_bytes(b"source")
    if status in {"ready_to_schedule", "scheduled", "uploaded", "upload_error"} or extra.pop("with_master", False):
        (clip / "master.mp4").write_bytes(b"final" * 200)
    if extra.pop("with_transcript", True):
        (clip / "transcript.json").write_text(
            json.dumps({"duration": 1, "words": [{"word": "tes", "start": 0, "end": 1}], "segments": []}),
            encoding="utf-8",
        )
        extra.setdefault("transcript_path", "transcript.json")
    path = clip / "data.json"
    path.write_text(json.dumps({"clip_id": clip_id, "status": status, "title": clip_id, **extra}), encoding="utf-8")
    return path


def test_output_geometry_default_and_quality_map():
    assert output_geometry() == (1080, 1920)
    assert output_geometry("480") == (540, 960)
    assert output_geometry("720") == (720, 1280)
    assert output_geometry("1080") == (1080, 1920)
    assert output_geometry("1440") == (1440, 2560)


def test_modes_reject_or_accept_orientation_as_contracted():
    assert validate_orientation("vertical_full", True) == "vertical_full"
    assert validate_orientation("vertical_full", False) == "vertical_full"
    assert validate_orientation("gaming", True) == "gaming"
    assert validate_orientation("split_middle", True) == "split_middle"
    with pytest.raises(LayoutModeError, match="landscape"):
        validate_orientation("gaming", False)
    with pytest.raises(LayoutModeError, match="landscape"):
        validate_orientation("split_middle", False)


def test_filtergraphs_for_three_modes_produce_1080x1920_labels():
    vf_l, label_l = build_filtergraph("vertical_full", 1920, 1080, None, 1080, 1920)
    vf_p, label_p = build_filtergraph("vertical_full", 576, 1024, None, 1080, 1920)
    gaming, g_label = build_filtergraph(
        "gaming", 1920, 1080, {"x": 0.01, "y": 0.05, "width": 0.15, "height": 0.2}, 1080, 1920
    )
    split, s_label = build_filtergraph("split_middle", 1920, 1080, None, 1080, 1920)
    assert label_l and label_p and g_label and s_label
    joined = "\n".join(vf_l + vf_p + gaming + split)
    assert "1080" in joined and "1920" in joined
    assert "vstack" in "\n".join(gaming) or "overlay" in "\n".join(gaming) or "xstack" in "\n".join(gaming)
    assert "vstack" in "\n".join(split) or "overlay" in "\n".join(split) or "xstack" in "\n".join(split)


def test_batch_five_clips_isolates_single_failure(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    run = tmp_path / "output" / "run"
    for index in range(5):
        clip_id = f"c{index}"
        make_clip(tmp_path, clip_id, status="needs_edit")

    class Renderer:
        def __init__(self, **_kwargs):
            pass

        def render_existing_clip(self, clip_dir, _metadata, _settings, output, preview=False):
            if clip_dir.name == "c2":
                raise RuntimeError("clip two broken")
            output.write_bytes(b"x" * 1200)

    monkeypatch.setattr(mod, "LocalClipRenderer", Renderer)
    results = manager._auto_render_run(run)
    states = {item["clip_id"]: item["status"] for item in results}
    assert states["c2"] == "render_error"
    for clip_id in ("c0", "c1", "c3", "c4"):
        assert states[clip_id] == "ready_to_schedule"
        assert (run / clip_id / "master.mp4").is_file()
    assert json.loads((run / "c2" / "data.json").read_text(encoding="utf-8"))["status"] == "render_error"


def test_needs_facecam_survives_manager_restart(tmp_path, monkeypatch):
    first = mod.WebJobManager(app_dir=tmp_path)
    path = make_clip(tmp_path, "facecam", status="needs_edit", with_transcript=False)
    monkeypatch.setattr(
        mod,
        "detect_facecam",
        lambda _path, minimum_confidence=0.62: (_ for _ in ()).throw(mod.GamingLayoutError(mod.FACE_NOT_FOUND_MESSAGE)),
    )
    assert first.prepare_gaming_layout("facecam")["status"] == "needs_facecam"
    second = mod.WebJobManager(app_dir=tmp_path)
    listed = second.list_clips()["clips"]
    assert any(item["clip_id"] == "facecam" and item["status"] == "needs_facecam" for item in listed)
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "needs_facecam"


def test_scheduled_and_upload_error_survive_manager_restart(tmp_path, monkeypatch):
    first = mod.WebJobManager(app_dir=tmp_path)
    ready = make_clip(tmp_path, "ready", status="ready_to_schedule")
    when = (datetime.now(timezone.utc) + timedelta(minutes=30)).astimezone().replace(tzinfo=None).isoformat(timespec="minutes")
    scheduled = first.schedule_clip_upload({"clip_id": "ready", "scheduled_at": when, "title": "Judul", "description": "Desc"})
    assert scheduled["status"] == "scheduled"
    fail = make_clip(tmp_path, "fail", status="upload_error", youtube_upload={"status": "error", "error": "boom", "title": "T"})
    second = mod.WebJobManager(app_dir=tmp_path)
    statuses = {item["clip_id"]: item["status"] for item in second.list_clips()["clips"]}
    assert statuses["ready"] == "scheduled"
    assert statuses["fail"] == "upload_error"
    assert json.loads(ready.read_text(encoding="utf-8"))["youtube_upload"]["status"] == "scheduled"
    assert json.loads(fail.read_text(encoding="utf-8"))["status"] == "upload_error"


def test_upload_success_and_failure_paths(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    path = make_clip(tmp_path, "up", status="scheduled", youtube_upload={
        "status": "scheduled",
        "scheduled_at": "2000-01-01T00:00:00+00:00",
        "title": "Judul",
        "description": "Desk",
        "privacy": "public",
    })
    monkeypatch.setattr(
        mod,
        "upload_youtube_video",
        lambda *_args, **_kwargs: {"video_id": "ok1", "url": "https://youtube.test/ok1"},
    )
    manager.process_due_youtube_uploads()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["status"] == "uploaded"
    assert saved["youtube_upload"]["video_id"] == "ok1"

    path2 = make_clip(tmp_path, "up2", status="scheduled", youtube_upload={
        "status": "scheduled",
        "scheduled_at": "2000-01-01T00:00:00+00:00",
        "title": "Judul2",
        "description": "Desk2",
        "privacy": "public",
    })

    def boom(*_a, **_k):
        raise RuntimeError("network down")

    monkeypatch.setattr(mod, "upload_youtube_video", boom)
    manager.process_due_youtube_uploads()
    failed = json.loads(path2.read_text(encoding="utf-8"))
    assert failed["status"] == "upload_error"


def test_delete_terminal_clip_and_cancel_schedule(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    make_clip(tmp_path, "del", status="ready_to_schedule")
    when = (datetime.now(timezone.utc) + timedelta(minutes=30)).astimezone().replace(tzinfo=None).isoformat(timespec="minutes")
    assert manager.schedule_clip_upload({"clip_id": "del", "scheduled_at": when, "title": "A", "description": "B"})["status"] == "scheduled"
    assert manager.cancel_clip_upload({"clip_id": "del"})["status"] == "cancelled"
    assert manager.delete_clip({"clip_id": "del"})["status"] == "deleted"
    assert not (tmp_path / "output" / "run" / "del").exists()


def test_hook_contract_matches_reference_rules():
    text = "RADIT KEBANYAKAN BACA HARUS FISIOTERAPI BANGET SEKARANG JUGA"
    hook = normalize_hook_text(text)
    words = hook.replace("\n", " ").split()
    assert hook.replace("\n", " ").rstrip("!").split() == text.split()[:6]
    assert len(hook.splitlines()) <= 4


def test_gaming_detection_cache_reuses_source_identity(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    path = make_clip(tmp_path, "cache", status="needs_edit", with_transcript=False)
    calls = []

    def detect(_path):
        calls.append(1)
        return {"x": 0.02, "y": 0.03, "width": 0.3, "height": 0.4, "confidence": 0.91}

    monkeypatch.setattr(mod, "detect_facecam", detect)
    first = manager.detect_gaming_facecam({"clip_id": "cache"})
    second = manager.detect_gaming_facecam({"clip_id": "cache"})
    assert first["cached"] is False
    assert second["cached"] is True
    assert calls == [1]
    saved = json.loads(path.read_text(encoding="utf-8"))["gaming_detection"]
    assert saved["facecam"] == first["facecam"]


def test_smoke_modes_from_synthetic_sources_if_ffmpeg_available(tmp_path):
    ffmpeg = subprocess.run(["ffmpeg", "-version"], capture_output=True)
    if ffmpeg.returncode != 0:
        pytest.skip("ffmpeg missing")
    out = tmp_path / "smoke"
    out.mkdir()
    landscape = out / "land.mp4"
    portrait = out / "port.mp4"
    # short synthetic sources only; no large fixture committed
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=30",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", str(landscape)],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=576x1024:rate=30",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", str(portrait)],
        check=True,
    )
    cases = [
        ("vertical_full", landscape, 1920, 1080, None),
        ("vertical_full", portrait, 576, 1024, None),
        ("gaming", landscape, 1920, 1080, {"x": 0.01, "y": 0.05, "width": 0.15, "height": 0.2}),
        ("split_middle", landscape, 1920, 1080, None),
    ]
    for index, (mode, source, width, height, roi) in enumerate(cases):
        filters, label = build_filtergraph(mode, width, height, roi, 1080, 1920)
        target = out / f"out-{index}.mp4"
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-t", "0.5",
            "-filter_complex", ";".join(filters), "-map", f"[{label}]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-c:a", "aac", "-shortest", str(target),
        ]
        subprocess.run(cmd, check=True)
        probe = json.loads(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of", "json", str(target)],
            capture_output=True, text=True, check=True,
        ).stdout)
        video = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
        assert (video["width"], video["height"]) == (1080, 1920)
        assert any(stream["codec_type"] == "audio" for stream in probe["streams"])
        assert target.stat().st_size > 1000


def test_filtergraph_output_geometry_follows_quality(tmp_path):
    ffmpeg = subprocess.run(["ffmpeg", "-version"], capture_output=True)
    if ffmpeg.returncode != 0:
        pytest.skip("ffmpeg missing")
    source = tmp_path / "src.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=854x480:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
            "-t", "0.4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
        ],
        check=True,
    )
    for quality, expected in (("480", (540, 960)), ("720", (720, 1280)), ("1080", (1080, 1920)), ("1440", (1440, 2560))):
        out_w, out_h = output_geometry(quality)
        filters, label = build_filtergraph("vertical_full", 854, 480, None, out_w, out_h)
        target = tmp_path / f"q{quality}.mp4"
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-t", "0.3",
                "-filter_complex", ";".join(filters), "-map", f"[{label}]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-c:a", "aac", "-shortest", str(target),
            ],
            check=True,
        )
        probe = json.loads(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of", "json", str(target)],
            capture_output=True, text=True, check=True,
        ).stdout)
        video = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
        assert (video["width"], video["height"]) == expected
        assert any(stream["codec_type"] == "audio" for stream in probe["streams"])
def test_hook_tts_uses_generate_content_audio_response(tmp_path, monkeypatch):
    renderer = mod.LocalClipRenderer(ffmpeg_path="ffmpeg", output_dir=str(tmp_path))
    renderer.tts_api_key = "secret"
    renderer.tts_base_url = "https://generativelanguage.googleapis.com/v1beta"
    renderer.tts_model = "gemini-3.1-flash-tts-preview"
    renderer.tts_voice = "Fenrir"
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            import base64
            return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/l16; rate=24000; channels=1", "data": base64.b64encode(b"\0\0" * 100).decode()}}]}}]}

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, payload=json, timeout=timeout)
        return Response()

    import requests
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(renderer, "_probe_media_duration", lambda _path: 1.0)
    output, duration = renderer._generate_hook_tts("Tes suara", tmp_path)
    assert captured["url"].endswith("/models/gemini-3.1-flash-tts-preview:generateContent")
    assert captured["payload"]["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert captured["payload"]["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Fenrir"
    prompt = captured["payload"]["contents"][0]["parts"][0]["text"]
    assert "langsung menghentak" in prompt
    assert "tempo cepat, artikulasi jelas" in prompt
    assert "konsonan akhir" in prompt
    assert output.is_file() and output.stat().st_size > 44
    assert duration == pytest.approx(1.0 / 1.12)


def test_hook_audio_is_faster_and_punchier(tmp_path):
    renderer = mod.LocalClipRenderer(ffmpeg_path="ffmpeg", output_dir=str(tmp_path))
    command = renderer._build_composite_command(
        "source.mp4", "output.mp4", 10,
        audio_source="source.mp4", tts_source=tmp_path / "hook.wav", intro_duration=3.0,
    )
    graph = command[command.index("-filter_complex") + 1]
    assert "atempo=1.12" in graph
    assert "acompressor=" in graph
    assert "volume=5dB" in graph
    assert "alimiter=" in graph


def test_final_renderer_routes_vertical_full_without_removed_legacy_filter(tmp_path, monkeypatch):
    clip_dir = tmp_path / "clip"
    clip_dir.mkdir()
    (clip_dir / "source.mp4").write_bytes(b"source")
    (clip_dir / "transcript.json").write_text('[{"start": 0, "end": 1, "text": "halo"}]')
    renderer = mod.LocalClipRenderer(ffmpeg_path="ffmpeg", output_dir=str(tmp_path))
    monkeypatch.setattr(renderer, "_probe_render_input", lambda _path: (854, 480, 1.0))
    monkeypatch.setattr(renderer, "convert_to_portrait_with_progress", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("skip track in unit test")))
    monkeypatch.setattr(renderer, "_generate_hook_tts", lambda *_args: (None, 0.0))
    monkeypatch.setattr(renderer, "_create_hook_overlay", lambda *_args, **_kwargs: Path(_args[-1]).write_bytes(b"png"))
    monkeypatch.setattr(renderer, "_create_caption_ass", lambda *_args: str(clip_dir / "captions.ass"))
    monkeypatch.setattr(renderer, "_create_credit_overlay", lambda *_args, **_kwargs: Path(_args[-1]).write_bytes(b"png"))
    monkeypatch.setattr(renderer, "_has_audio_stream", lambda _path: True)
    (clip_dir / "captions.ass").write_text("ass")
    captured = {}
    monkeypatch.setattr(renderer, "_build_composite_command", lambda *_args, **kwargs: captured.update(kwargs) or ["ffmpeg"])

    def fake_run(_command, _duration, _progress, timeout):
        (clip_dir / "master.mp4").write_bytes(b"x" * 1001)

    monkeypatch.setattr(renderer, "run_ffmpeg_with_progress", fake_run)
    renderer.render_existing_clip(
        clip_dir,
        {"title": "Halo", "hook_text": "Halo", "channel_name": "test"},
        {"video_layout": {"mode": "normal"}, "video_quality": "1080"},
        clip_dir / "master.mp4",
    )
    filters = captured["portrait_filters"]
    assert "crop=270:480:292:0" in filters[0]
    assert "scale=1080:1920" in filters[0]


def test_final_renderer_uses_quality_for_output_geometry(tmp_path, monkeypatch):
    clip_dir = tmp_path / "clip"
    clip_dir.mkdir()
    (clip_dir / "source.mp4").write_bytes(b"source")
    (clip_dir / "transcript.json").write_text('[{"start": 0, "end": 1, "text": "halo"}]')
    renderer = mod.LocalClipRenderer(ffmpeg_path="ffmpeg", output_dir=str(tmp_path), video_quality="480")
    monkeypatch.setattr(renderer, "_probe_render_input", lambda _path: (854, 480, 1.0))
    monkeypatch.setattr(renderer, "_generate_hook_tts", lambda *_args: (None, 0.0))
    monkeypatch.setattr(renderer, "_create_hook_overlay", lambda *_args, **_kwargs: Path(_args[-1]).write_bytes(b"png"))
    monkeypatch.setattr(renderer, "_create_caption_ass", lambda *_args: str(clip_dir / "captions.ass"))
    monkeypatch.setattr(renderer, "_create_credit_overlay", lambda *_args, **_kwargs: Path(_args[-1]).write_bytes(b"png"))
    monkeypatch.setattr(renderer, "_has_audio_stream", lambda _path: True)
    (clip_dir / "captions.ass").write_text("ass")
    captured = {}
    monkeypatch.setattr(renderer, "_build_composite_command", lambda *_args, **kwargs: captured.update(kwargs) or ["ffmpeg"])

    def fake_run(_command, _duration, _progress, timeout):
        (clip_dir / "master.mp4").write_bytes(b"x" * 1001)

    monkeypatch.setattr(renderer, "run_ffmpeg_with_progress", fake_run)
    renderer.render_existing_clip(
        clip_dir,
        {"title": "Halo", "hook_text": "Halo", "channel_name": "test"},
        {"video_layout": {"mode": "vertical_full"}, "video_quality": "480"},
        clip_dir / "master.mp4",
    )
    filters = captured["portrait_filters"]
    assert "scale=540:960" in filters[0]
    assert "scale=1080:1920" not in filters[0]


def test_final_renderer_routes_split_middle(tmp_path, monkeypatch):
    clip_dir = tmp_path / "clip"
    clip_dir.mkdir()
    (clip_dir / "source.mp4").write_bytes(b"source")
    (clip_dir / "transcript.json").write_text('[{"start": 0, "end": 1, "text": "halo"}]')
    renderer = mod.LocalClipRenderer(ffmpeg_path="ffmpeg", output_dir=str(tmp_path))
    monkeypatch.setattr(renderer, "_probe_render_input", lambda _path: (854, 480, 1.0))
    monkeypatch.setattr(renderer, "convert_to_portrait_with_progress", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("skip track in unit test")))
    monkeypatch.setattr(renderer, "_generate_hook_tts", lambda *_args: (None, 0.0))
    monkeypatch.setattr(renderer, "_create_hook_overlay", lambda *_args, **_kwargs: Path(_args[-1]).write_bytes(b"png"))
    monkeypatch.setattr(renderer, "_create_caption_ass", lambda *_args: str(clip_dir / "captions.ass"))
    monkeypatch.setattr(renderer, "_create_credit_overlay", lambda *_args, **_kwargs: Path(_args[-1]).write_bytes(b"png"))
    monkeypatch.setattr(renderer, "_has_audio_stream", lambda _path: True)
    (clip_dir / "captions.ass").write_text("ass")
    captured = {}
    monkeypatch.setattr(renderer, "_build_composite_command", lambda *_args, **kwargs: captured.update(kwargs) or ["ffmpeg"])

    def fake_run(_command, _duration, _progress, timeout):
        (clip_dir / "master.mp4").write_bytes(b"x" * 1001)

    monkeypatch.setattr(renderer, "run_ffmpeg_with_progress", fake_run)
    renderer.render_existing_clip(
        clip_dir,
        {"title": "Halo", "hook_text": "Halo", "channel_name": "test"},
        {"video_layout": {"mode": "split_middle"}},
        clip_dir / "master.mp4",
    )
    filters = captured["portrait_filters"]
    assert any("vstack=inputs=2" in item for item in filters)
    assert any("crop=426:480:0:0" in item for item in filters)
    assert any("crop=426:480:426:0" in item for item in filters)
