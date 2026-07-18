"""Speedups: persistent subtitle cache + reuse draft portrait on final render."""
from pathlib import Path
from unittest.mock import MagicMock

from clipper_core import AutoClipperCore
from clipper_export import ExportMixin


def _core_for_cache(tmp_path: Path) -> AutoClipperCore:
    core = object.__new__(AutoClipperCore)
    core.cache_dir = tmp_path / "cache"
    core.temp_dir = tmp_path / "temp"
    core.cache_dir.mkdir(parents=True, exist_ok=True)
    core.temp_dir.mkdir(parents=True, exist_ok=True)
    return core


def test_video_cache_dir_is_stable_for_same_url(tmp_path):
    core = _core_for_cache(tmp_path)
    url = "https://www.youtube.com/watch?v=95INIXz2Zv0&si=abc"
    first = core._video_cache_dir(url)
    second = core._video_cache_dir(url)
    assert first == second
    assert first.name == "95INIXz2Zv0"
    assert first.parent == core.cache_dir


def test_video_cache_dir_supports_shorts_urls(tmp_path):
    core = _core_for_cache(tmp_path)
    path = core._video_cache_dir("https://youtube.com/shorts/dtFKYx0B8tQ?si=x")
    assert path.name == "dtFKYx0B8tQ"


def test_video_cache_dir_distinguishes_embed_and_live_urls(tmp_path):
    core = _core_for_cache(tmp_path)
    assert core._video_cache_dir("https://youtube.com/embed/AAA111").name == "AAA111"
    assert core._video_cache_dir("https://youtube.com/embed/BBB222").name == "BBB222"
    assert core._video_cache_dir("https://youtube.com/live/CCC333").name == "CCC333"


def test_render_existing_clip_reuses_draft_and_skips_retrack(tmp_path, monkeypatch):
    clip_dir = tmp_path / "clip"
    clip_dir.mkdir()
    source = clip_dir / "source.mp4"
    draft = clip_dir / "draft.mp4"
    source.write_bytes(b"0" * 2000)
    draft.write_bytes(b"1" * 2000)
    (clip_dir / "transcript.json").write_text(
        '{"duration": 5.0, "words": [{"word": "hai", "start": 0.0, "end": 0.5}], "segments": []}',
        encoding="utf-8",
    )

    renderer = object.__new__(ExportMixin)
    renderer.output_dir = str(tmp_path)
    renderer.video_quality = "480"
    renderer.render_timeout = 30
    renderer.log = lambda *args, **kwargs: None
    renderer.set_progress = lambda *args, **kwargs: None
    renderer.channel_name = ""

    probes = {
        str(source): (1280, 720, 5.0),
        str(draft): (540, 960, 5.0),
    }

    def fake_probe(path):
        return probes[str(path)]

    convert_calls = []

    def fake_convert(input_path, output_path, progress_callback):
        convert_calls.append((input_path, output_path))
        raise AssertionError("should not re-track when draft portrait exists")

    tts_calls = []

    def fake_tts(hook_text, clip_dir_arg):
        tts_calls.append(hook_text)
        wav = clip_dir / "hook.wav"
        wav.write_bytes(b"RIFF")
        return wav, 1.2

    monkeypatch.setattr(renderer, "_probe_render_input", fake_probe)
    monkeypatch.setattr(renderer, "convert_to_portrait_with_progress", fake_convert, raising=False)
    monkeypatch.setattr(renderer, "_generate_hook_tts", fake_tts)
    monkeypatch.setattr(renderer, "_has_audio_stream", lambda path: True)
    monkeypatch.setattr(renderer, "_create_hook_overlay", lambda *a, **k: None)
    monkeypatch.setattr(renderer, "_create_credit_overlay", lambda *a, **k: None)
    def fake_caption_ass(*args, **kwargs):
        path = clip_dir / "captions.ass"
        path.write_text("x", encoding="utf-8")
        return path

    monkeypatch.setattr(renderer, "_create_caption_ass", fake_caption_ass)

    built = {}
    output_holder = {}

    def wrap_build(render_input, output_path, duration, **kwargs):
        built["render_input"] = render_input
        built["kwargs"] = kwargs
        output_holder["path"] = output_path
        return ["ffmpeg", "noop", str(output_path)]

    monkeypatch.setattr(renderer, "_build_composite_command", wrap_build)

    # run_ffmpeg_with_progress just needs to create the requested output file.
    def fake_progress_run(command, total_duration, progress_callback=None, timeout=None):
        Path(output_holder["path"]).write_bytes(b"m" * 2000)
        if progress_callback:
            progress_callback(1.0)

    monkeypatch.setattr(renderer, "run_ffmpeg_with_progress", fake_progress_run, raising=False)

    output = clip_dir / "master.auto.tmp.mp4"
    metadata = {
        "hook_text": "ternyata [dokter tirta] marah-marah",
        "title": "test",
        "channel_name": "channel",
        "transcript_path": "transcript.json",
    }
    settings = {
        "video_quality": "480",
        "video_layout": {"mode": "vertical_full"},
        "subtitle": {},
        "hook_style": {},
        "credit_watermark": {},
        "watermark": {},
        "blur_background": {},
    }
    renderer.render_existing_clip(clip_dir, metadata, settings, output, preview=False)

    assert convert_calls == []
    assert tts_calls
    assert Path(built["render_input"]) == draft
    assert output.is_file() and output.stat().st_size >= 1000
