import importlib.util
import json
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("web_klip_job_manager_m3", ROOT / "job_manager.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

from clipper_ai import HARD_CLIP_MAX, HARD_CLIP_MIN, TARGET_CLIP_MAX, TARGET_CLIP_MIN
from clipper_core import LocalClipRenderer
from config.editor_defaults import v3_locked_render_settings
from subtitle_cues import build_subtitle_cues
from visual_style import normalize_hook_text


def test_hook_caps_seven_words_four_lines():
    text = "Ini adalah hook panjang sekali yang harus dipotong dengan aman sekarang"
    hook = normalize_hook_text(text)
    assert hook.replace("\n", " ").rstrip("!").split() == text.upper().split()[:7]
    assert len(hook.splitlines()) <= 4
    assert len(hook.replace("\n", " ").split()) <= 7
    assert hook == hook.upper()


def test_subtitle_contract_uppercase_and_punctuation_filter():
    transcript = {
        "duration": 2.0,
        "words": [
            {"word": "halo.", "start": 0.0, "end": 0.4},
            {"word": "dunia!", "start": 0.4, "end": 0.8},
            {"word": "ini:", "start": 0.8, "end": 1.2},
            {"word": "tes?", "start": 1.2, "end": 1.6},
        ],
        "segments": [],
    }
    cues = build_subtitle_cues(transcript)
    assert [cue["text"] for cue in cues] == ["HALO DUNIA!", "INI TES"]
    assert len(cues[0]["words"]) == 2


def test_duration_contract_is_40_to_70_target_50_to_70():
    assert (HARD_CLIP_MIN, HARD_CLIP_MAX) == (40, 70)
    assert (TARGET_CLIP_MIN, TARGET_CLIP_MAX) == (50, 70)


def test_locked_visuals_ignore_client_style():
    settings = v3_locked_render_settings({
        "watermark": {"enabled": True},
        "blur_background": {"enabled": True},
        "subtitle": {"text_transform": "none"},
        "video_layout": {"mode": "normal"},
    })
    assert settings["watermark"]["enabled"] is False
    assert settings["blur_background"]["enabled"] is False
    assert settings["subtitle"]["text_transform"] == "uppercase"
    assert settings["credit_watermark"]["text"] == "sc: @{channel}"


def test_intro_filter_freezes_then_hides_without_clipped_slide_and_delays_original_audio(tmp_path):
    renderer = LocalClipRenderer(ffmpeg_path="ffmpeg")
    renderer.hook_style_settings = {"duration": 5}
    command = renderer._build_composite_command(
        "source.mp4", "output.mp4", 50,
        audio_source="source.mp4", hook_overlay=tmp_path / "hook.png",
        tts_source=tmp_path / "tts.wav", intro_duration=2.6,
    )
    graph = command[command.index("-filter_complex") + 1]
    assert "tpad=stop_mode=clone:stop_duration=2.600" in graph
    assert "concat=n=2:v=1:a=0" in graph
    assert "overlay=0:0:enable='between(t,0,2.600)'" in graph
    assert "main_w" not in graph
    assert "apad=pad_dur=0.600" in graph
    assert "[atts][aoriginal]concat=n=2:v=0:a=1" in graph
    assert "volume=1,loudnorm=I=-14:LRA=7:TP=-1,asetpts=PTS-STARTPTS[aout]" in graph
    assert command[command.index("-ar") + 1] == "48000"
    assert command[command.index("-t") + 1] == "52.600"


def test_auto_render_isolates_clip_failure_and_keeps_success(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    run = tmp_path / "output" / "run"
    for clip_id in ("bad", "good"):
        clip = run / clip_id
        clip.mkdir(parents=True)
        (clip / "source.mp4").write_bytes(b"source")
        (clip / "transcript.json").write_text(json.dumps({"duration": 1, "words": [{"word": "tes", "start": 0, "end": 1}], "segments": []}), encoding="utf-8")
        (clip / "data.json").write_text(json.dumps({"clip_id": clip_id, "status": "needs_edit", "transcript_path": "transcript.json"}), encoding="utf-8")

    class Renderer:
        def __init__(self, **_kwargs):
            pass

        def render_existing_clip(self, clip_dir, _metadata, _settings, output, preview=False):
            if clip_dir.name == "bad":
                raise RuntimeError("broken clip")
            output.write_bytes(b"x" * 1000)

    monkeypatch.setattr(mod, "LocalClipRenderer", Renderer)
    results = manager._auto_render_run(run)
    states = {item["clip_id"]: item["status"] for item in results}
    assert states == {"bad": "render_error", "good": "ready_to_schedule"}
    assert json.loads((run / "bad" / "data.json").read_text())["status"] == "render_error"
    assert (run / "good" / "master.mp4").is_file()


def test_auto_render_skips_needs_facecam(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip = tmp_path / "output" / "run" / "manual"
    clip.mkdir(parents=True)
    (clip / "data.json").write_text(json.dumps({"clip_id": "manual", "status": "needs_facecam"}), encoding="utf-8")
    assert manager._auto_render_run(clip.parent) == []
    assert json.loads((clip / "data.json").read_text())["status"] == "needs_facecam"


def test_auto_render_reuses_ready_master(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip = tmp_path / "output" / "run" / "cached"
    clip.mkdir(parents=True)
    (clip / "master.mp4").write_bytes(b"existing")
    (clip / "data.json").write_text(json.dumps({"clip_id": "cached", "status": "ready_to_schedule"}), encoding="utf-8")
    assert manager._auto_render_run(clip.parent) == [{"clip_id": "cached", "status": "cached"}]
    assert (clip / "master.mp4").read_bytes() == b"existing"


def test_manual_roi_transitions_to_render_queue(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip = tmp_path / "output" / "run" / "roi"
    clip.mkdir(parents=True)
    (clip / "source.mp4").write_bytes(b"source")
    (clip / "transcript.json").write_text(json.dumps({"duration": 1, "words": [{"word": "tes", "start": 0, "end": 1}], "segments": []}), encoding="utf-8")
    meta = clip / "data.json"
    meta.write_text(json.dumps({
        "clip_id": "roi-m3", "status": "needs_facecam", "transcript_path": "transcript.json",
        "source_geometry": {"width": 1920, "height": 1080, "is_landscape": True},
    }), encoding="utf-8")

    class Renderer:
        def __init__(self, **_kwargs):
            pass

        def render_existing_clip(self, *_args, **_kwargs):
            pass

    class QueuedThread:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr(mod, "LocalClipRenderer", Renderer)
    monkeypatch.setattr(mod, "_GLOBAL_RENDER_LOCK", threading.Lock())
    monkeypatch.setattr(mod, "_GLOBAL_FINAL_RENDER_LOCK", threading.Lock())
    monkeypatch.setattr(mod.threading, "Thread", QueuedThread)
    result = manager.submit_facecam_roi({"clip_id": "roi-m3", "x": 0.02, "y": 0.03, "width": 0.18, "height": 0.2})
    assert result["status"] == "ok"
    assert result.get("render", {}).get("status") == "queued"
    assert result.get("clip_status") == "render_queued"
    assert json.loads(meta.read_text())["status"] == "render_queued"
