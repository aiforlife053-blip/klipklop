import importlib.util
import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "job_manager.py"
spec = importlib.util.spec_from_file_location("web_klip_job_manager", MODULE)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
import clipper_ai
import clipper_export
from clipper_core import AutoClipperCore, LocalClipRenderer
from clipper_shared import slice_timed_transcript, timed_segments_to_prompt, validate_timed_transcript
from clipper_download import DownloadMixin
from clipper_export import ExportMixin
from clipper_portrait import PortraitMixin
from clipper_ffmpeg import FfmpegMixin
from config.config_manager import ConfigManager
from subtitle_cues import build_subtitle_cues


def test_static_subtitle_cues_remove_rolling_caption_overlap():
    cues = build_subtitle_cues({"duration": 8.0, "words": [], "segments": [{"text": "lama", "start": 0.0, "end": 4.0}, {"text": "baru", "start": 2.0, "end": 6.0}, {"text": "terbaru", "start": 4.0, "end": 8.0}]})
    assert [(cue["text"], cue["start"], cue["end"]) for cue in cues] == [("lama", 0.0, 2.0), ("baru", 2.0, 4.0), ("terbaru", 4.0, 8.0)]


def test_new_config_enables_subtitles_by_default(tmp_path):
    manager = ConfigManager(tmp_path / "config.json", tmp_path / "output")
    assert manager.config["subtitle"]["enabled"] is True


def test_existing_config_migrates_subtitle_default_to_enabled(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"subtitle": {"enabled": False}, "_preview_defaults_v2_migrated": True}), encoding="utf-8")
    manager = ConfigManager(config_path, tmp_path / "output")
    assert manager.config["subtitle"]["enabled"] is True
    assert manager.config["_subtitle_default_enabled_migrated"] is True


def test_atomic_metadata_write_retries_transient_permission_error(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    path = tmp_path / "data.json"
    path.write_text(json.dumps({"status": "old"}), encoding="utf-8")
    real_replace = mod.os.replace
    attempts = []

    def replace(source, target):
        attempts.append((source, target))
        if len(attempts) < 3:
            raise PermissionError(5, "Access is denied")
        real_replace(source, target)

    monkeypatch.setattr(mod.os, "replace", replace)
    monkeypatch.setattr(mod.time, "sleep", lambda _delay: None)
    manager._write_json_atomic(path, {"status": "new"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"status": "new"}
    assert len(attempts) == 3
    assert list(tmp_path.glob("data.*.tmp")) == []


def test_atomic_metadata_write_preserves_target_after_retry_exhaustion(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    path = tmp_path / "data.json"
    path.write_text(json.dumps({"status": "old"}), encoding="utf-8")
    attempts = []

    def replace(_source, _target):
        attempts.append(1)
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(mod.os, "replace", replace)
    monkeypatch.setattr(mod.time, "sleep", lambda _delay: None)
    with pytest.raises(PermissionError):
        manager._write_json_atomic(path, {"status": "new"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"status": "old"}
    assert len(attempts) == 5
    assert list(tmp_path.glob("data.*.tmp")) == []


def test_validate_timed_transcript_sorts_and_returns_json_safe_copy():
    source = {
        "duration": 10,
        "words": [
            {"word": "late", "start": 2, "end": 3},
            {"word": "early", "start": 1, "end": 1.5},
        ],
        "segments": [
            {"text": "late", "start": 2, "end": 3},
            {"text": "early", "start": 1, "end": 1.5},
        ],
    }
    original = json.loads(json.dumps(source))

    result = validate_timed_transcript(source, require_words=True)

    assert result == {
        "duration": 10.0,
        "words": [
            {"word": "early", "start": 1.0, "end": 1.5},
            {"word": "late", "start": 2.0, "end": 3.0},
        ],
        "segments": [
            {"text": "early", "start": 1.0, "end": 1.5},
            {"text": "late", "start": 2.0, "end": 3.0},
        ],
    }
    assert source == original
    assert json.loads(json.dumps(result)) == result


@pytest.mark.parametrize(
    ("source", "require_words"),
    [
        ({"duration": float("nan"), "words": [], "segments": []}, False),
        ({"duration": float("inf"), "words": [], "segments": []}, False),
        ({"duration": -1.0, "words": [], "segments": []}, False),
        ({"duration": 1.0, "words": [{"word": "x", "start": -0.1, "end": 0.5}], "segments": []}, False),
        ({"duration": 1.0, "words": [{"word": "x", "start": 0.5, "end": 0.5}], "segments": []}, False),
        ({"duration": 1.0, "words": [], "segments": [{"text": "x", "start": 0.8, "end": 0.2}]}, False),
        ({"duration": 1.0, "words": [{"word": " ", "start": 0.0, "end": 0.5}], "segments": []}, False),
        ({"duration": 1.0, "words": [], "segments": [{"text": "", "start": 0.0, "end": 0.5}]}, False),
        ({"duration": 1.0, "words": [], "segments": []}, True),
    ],
)
def test_validate_timed_transcript_rejects_invalid_values(source, require_words):
    with pytest.raises(ValueError):
        validate_timed_transcript(source, require_words=require_words)


def test_parse_srt_timed_supports_bom_crlf_multiline_and_dot_milliseconds(tmp_path):
    path = tmp_path / "native.srt"
    path.write_bytes("\ufeff1\r\n00:00:09,000 --> 00:00:12,000\r\nbaris satu\r\nbaris dua\r\n\r\n00:01:09.000 --> 00:01:12.000\r\nkedua".encode("utf-8"))
    harness = object.__new__(DownloadMixin)
    transcript = harness.parse_srt_timed(str(path))
    assert transcript == {
        "duration": 72.0,
        "words": [],
        "segments": [
            {"text": "baris satu baris dua", "start": 9.0, "end": 12.0},
            {"text": "kedua", "start": 69.0, "end": 72.0},
        ],
    }


def test_timed_segments_to_prompt_formats_gemini_timestamps():
    source = {
        "duration": 75.0,
        "words": [],
        "segments": [{"text": "isi ucapan", "start": 70.2, "end": 74.8}],
    }
    assert timed_segments_to_prompt(source) == "[00:01:10,200 - 00:01:14,800] isi ucapan"


def test_slice_timed_transcript_rebases_and_clamps_without_mutation():
    source = {
        "duration": 20.0,
        "words": [
            {"word": "awal", "start": 4.8, "end": 5.2},
            {"word": "tengah", "start": 6.0, "end": 6.5},
            {"word": "akhir", "start": 8.8, "end": 9.2},
        ],
        "segments": [{"text": "awal tengah akhir", "start": 4.8, "end": 9.2}],
    }
    original = json.loads(json.dumps(source))

    sliced = slice_timed_transcript(source, 5.0, 9.0)

    assert sliced == {
        "duration": 4.0,
        "words": [
            {"word": "awal", "start": 0.0, "end": 0.2},
            {"word": "tengah", "start": 1.0, "end": 1.5},
            {"word": "akhir", "start": 3.8, "end": 4.0},
        ],
        "segments": [{"text": "awal tengah akhir", "start": 0.0, "end": 4.0}],
    }
    assert source == original


def test_slice_timed_transcript_uses_half_open_boundaries():
    source = {
        "duration": 10.0,
        "words": [
            {"word": "before", "start": 4.0, "end": 5.0},
            {"word": "inside", "start": 5.0, "end": 6.0},
            {"word": "after", "start": 7.0, "end": 8.0},
        ],
        "segments": [{"text": "inside", "start": 5.0, "end": 6.0}],
    }
    assert [item["word"] for item in slice_timed_transcript(source, 5.0, 7.0)["words"]] == ["inside"]


def test_slice_timed_transcript_drops_items_collapsed_by_rounding():
    source = {
        "duration": 1.0,
        "words": [{"word": "tiny", "start": 0.0001, "end": 0.0004}],
        "segments": [{"text": "tiny", "start": 0.0001, "end": 0.0004}],
    }
    result = slice_timed_transcript(source, 0.0, 1.0)
    assert result["words"] == []
    assert result["segments"] == []


def test_slice_timed_transcript_supports_overlapping_slices():
    source = {
        "duration": 10.0,
        "words": [{"word": "shared", "start": 4.0, "end": 6.0}],
        "segments": [{"text": "shared", "start": 4.0, "end": 6.0}],
    }
    first = slice_timed_transcript(source, 3.0, 5.0)
    second = slice_timed_transcript(source, 5.0, 7.0)
    assert first["words"] == [{"word": "shared", "start": 1.0, "end": 2.0}]
    assert second["words"] == [{"word": "shared", "start": 0.0, "end": 1.0}]


@pytest.mark.parametrize(("start", "end"), [(float("nan"), 1.0), (0.0, float("inf")), (-1.0, 1.0), (1.0, 1.0), (2.0, 1.0)])
def test_slice_timed_transcript_rejects_invalid_range(start, end):
    source = {"duration": 3.0, "words": [], "segments": []}
    with pytest.raises(ValueError):
        slice_timed_transcript(source, start, end)


class GroqResponse:
    def __init__(self, status_code, data=None, headers=None, text=""):
        self.status_code = status_code
        self._data = data
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._data


class GroqHarness(clipper_ai.AiMixin):
    def __init__(self, language="id"):
        self.caption_client = SimpleNamespace(base_url="https://api.groq.test/openai/v1", api_key="gsk_secret")
        self.whisper_model = "whisper-large-v3-turbo"
        self.subtitle_language = language
        self.ffmpeg_path = "ffmpeg"
        self.logs = []
        self.tokens = []

    def log(self, message):
        self.logs.append(message)

    def set_progress(self, *_args):
        pass

    def report_tokens(self, *args):
        self.tokens.append(args)

    def is_cancelled(self):
        return False


def groq_transcript(text="halo dunia", duration=2.0):
    return {
        "duration": duration,
        "text": text,
        "words": [
            {"word": "halo", "start": 0.0, "end": 0.8},
            {"word": "dunia", "start": 0.9, "end": 1.8},
        ],
        "segments": [{"text": text, "start": 0.0, "end": 1.8}],
    }


def test_groq_chunk_request_shape_and_normalization(tmp_path, monkeypatch):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio")
    captured = {}

    def post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return GroqResponse(200, groq_transcript())

    monkeypatch.setattr(clipper_ai.requests, "post", post)
    result = GroqHarness()._transcribe_groq_chunk(str(audio))

    assert captured["url"] == "https://api.groq.test/openai/v1/audio/transcriptions"
    assert captured["headers"] == {"Authorization": "Bearer gsk_secret"}
    assert captured["data"] == [
        ("model", "whisper-large-v3-turbo"),
        ("response_format", "verbose_json"),
        ("timestamp_granularities[]", "word"),
        ("timestamp_granularities[]", "segment"),
        ("language", "id"),
    ]
    assert captured["files"]["file"][0] == "audio.mp3"
    assert result == {
        "duration": 2.0,
        "words": [
            {"word": "halo", "start": 0.0, "end": 0.8},
            {"word": "dunia", "start": 0.9, "end": 1.8},
        ],
        "segments": [{"text": "halo dunia", "start": 0.0, "end": 1.8}],
    }
    assert isinstance(result, dict)


def test_groq_transcription_ignores_empty_word_timestamp(tmp_path, monkeypatch):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio")
    response = groq_transcript()
    response["words"].insert(0, {"word": "", "start": 0.0, "end": 0.1})
    monkeypatch.setattr(clipper_ai.requests, "post", lambda *_args, **_kwargs: GroqResponse(200, response))

    result = GroqHarness()._transcribe_groq_chunk(str(audio))

    assert result["words"] == [
        {"word": "halo", "start": 0.0, "end": 0.8},
        {"word": "dunia", "start": 0.9, "end": 1.8},
    ]


def test_groq_transcription_ignores_empty_segment_timestamp(tmp_path, monkeypatch):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio")
    response = groq_transcript()
    response["segments"].insert(0, {"text": "", "start": 0.0, "end": 0.1})
    monkeypatch.setattr(clipper_ai.requests, "post", lambda *_args, **_kwargs: GroqResponse(200, response))

    result = GroqHarness()._transcribe_groq_chunk(str(audio))

    assert result["segments"] == [{"text": "halo dunia", "start": 0.0, "end": 1.8}]


@pytest.mark.parametrize("language", ["", "none", "auto", " AUTO "])
def test_groq_language_auto_is_omitted(tmp_path, monkeypatch, language):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio")
    captured = {}

    def post(_url, **kwargs):
        captured.update(kwargs)
        return GroqResponse(200, groq_transcript())

    monkeypatch.setattr(clipper_ai.requests, "post", post)
    GroqHarness(language)._transcribe_groq_chunk(str(audio))
    assert not any(key == "language" for key, _value in captured["data"])


def test_groq_words_required(tmp_path, monkeypatch):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio")
    response = groq_transcript()
    response["words"] = []
    monkeypatch.setattr(clipper_ai.requests, "post", lambda *_args, **_kwargs: GroqResponse(200, response))
    monkeypatch.setattr(GroqHarness, "_probe_media_duration", lambda self, _path: 2.0)
    with pytest.raises(ValueError, match="word timestamps"):
        GroqHarness().transcribe_audio_with_timestamps(str(audio), require_words=True)


def test_groq_http_401_does_not_retry_or_leak_key(tmp_path, monkeypatch):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio")
    attempts = []
    monkeypatch.setattr(clipper_ai.requests, "post", lambda *_args, **_kwargs: attempts.append(1) or GroqResponse(401, text="bad gsk_secret"))
    with pytest.raises(Exception) as exc_info:
        GroqHarness()._transcribe_groq_chunk(str(audio))
    message = str(exc_info.value)
    assert len(attempts) == 1
    assert "HTTP 401" in message
    assert "https://api.groq.test/openai/v1" in message
    assert "whisper-large-v3-turbo" in message
    assert "gsk_secret" not in message


def test_groq_http_429_then_200_retries(tmp_path, monkeypatch):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio")
    responses = [GroqResponse(429, headers={"Retry-After": "99"}), GroqResponse(200, groq_transcript())]
    sleeps = []
    monkeypatch.setattr(clipper_ai.requests, "post", lambda *_args, **_kwargs: responses.pop(0))
    monkeypatch.setattr(clipper_ai.time, "sleep", sleeps.append)
    result = GroqHarness()._transcribe_groq_chunk(str(audio))
    assert result["segments"][0]["text"] == "halo dunia"
    assert sleeps == [30.0]


def test_groq_http_500_stops_after_three_attempts(tmp_path, monkeypatch):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio")
    attempts = []
    monkeypatch.setattr(clipper_ai.requests, "post", lambda *_args, **_kwargs: attempts.append(1) or GroqResponse(500))
    monkeypatch.setattr(clipper_ai.time, "sleep", lambda _seconds: None)
    with pytest.raises(Exception, match="HTTP 500"):
        GroqHarness()._transcribe_groq_chunk(str(audio))
    assert len(attempts) == 3


@pytest.mark.parametrize("error", [clipper_ai.requests.Timeout(), clipper_ai.requests.ConnectionError()])
def test_groq_transport_errors_stop_after_three_attempts(tmp_path, monkeypatch, error):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio")
    attempts = []

    def post(*_args, **_kwargs):
        attempts.append(1)
        raise error

    monkeypatch.setattr(clipper_ai.requests, "post", post)
    monkeypatch.setattr(clipper_ai.time, "sleep", lambda _seconds: None)
    with pytest.raises(Exception, match="after 3 attempts"):
        GroqHarness()._transcribe_groq_chunk(str(audio))
    assert len(attempts) == 3


def test_groq_chunk_offset_merge_and_cleanup(tmp_path, monkeypatch):
    audio = tmp_path / "large.mp3"
    audio.write_bytes(b"x")
    chunks = [tmp_path / "chunk-1.mp3", tmp_path / "chunk-2.mp3"]
    for chunk in chunks:
        chunk.write_bytes(b"chunk")
    harness = GroqHarness()
    offsets = []
    monkeypatch.setattr(clipper_ai.os.path, "getsize", lambda _path: clipper_ai.MAX_GROQ_UPLOAD_BYTES + 1)
    monkeypatch.setattr(GroqHarness, "_probe_media_duration", lambda self, _path: 20.0)
    monkeypatch.setattr(GroqHarness, "_create_groq_chunks", lambda self, _path, _duration, _count, chunk_paths: chunk_paths.extend(map(str, chunks)) or [(str(chunks[0]), 0.0), (str(chunks[1]), 10.0)])

    def transcribe(_self, _path, time_offset=0.0):
        offsets.append(time_offset)
        return {
            "duration": 10.0,
            "words": [{"word": str(int(time_offset)), "start": time_offset, "end": time_offset + 1.0}],
            "segments": [{"text": str(int(time_offset)), "start": time_offset, "end": time_offset + 1.0}],
        }

    monkeypatch.setattr(GroqHarness, "_transcribe_groq_chunk", transcribe)
    result = harness.transcribe_audio_with_timestamps(str(audio), require_words=True)
    assert offsets == [0.0, 10.0]
    assert result == {
        "duration": 20.0,
        "words": [
            {"word": "0", "start": 0.0, "end": 1.0},
            {"word": "10", "start": 10.0, "end": 11.0},
        ],
        "segments": [
            {"text": "0", "start": 0.0, "end": 1.0},
            {"text": "10", "start": 10.0, "end": 11.0},
        ],
    }
    assert all(not chunk.exists() for chunk in chunks)
    assert harness.tokens == [(0, 0, 20.0, 0)]


def test_groq_chunk_cleanup_on_failure(tmp_path, monkeypatch):
    audio = tmp_path / "large.mp3"
    audio.write_bytes(b"x")
    chunk = tmp_path / "chunk.mp3"
    chunk.write_bytes(b"chunk")
    monkeypatch.setattr(clipper_ai.os.path, "getsize", lambda _path: clipper_ai.MAX_GROQ_UPLOAD_BYTES + 1)
    monkeypatch.setattr(GroqHarness, "_probe_media_duration", lambda self, _path: 20.0)
    monkeypatch.setattr(GroqHarness, "_create_groq_chunks", lambda self, _path, _duration, _count, chunk_paths: chunk_paths.append(str(chunk)) or [(str(chunk), 0.0)])
    monkeypatch.setattr(GroqHarness, "_transcribe_groq_chunk", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("failed")))
    with pytest.raises(RuntimeError, match="failed"):
        GroqHarness().transcribe_audio_with_timestamps(str(audio))
    assert not chunk.exists()


def test_groq_chunk_cleanup_on_cancellation(tmp_path, monkeypatch):
    audio = tmp_path / "large.mp3"
    audio.write_bytes(b"x")
    chunk = tmp_path / "chunk.mp3"
    chunk.write_bytes(b"chunk")
    harness = GroqHarness()
    checks = iter([False, True])
    monkeypatch.setattr(clipper_ai.os.path, "getsize", lambda _path: clipper_ai.MAX_GROQ_UPLOAD_BYTES + 1)
    monkeypatch.setattr(GroqHarness, "_probe_media_duration", lambda self, _path: 20.0)
    monkeypatch.setattr(GroqHarness, "_create_groq_chunks", lambda self, _path, _duration, _count, chunk_paths: chunk_paths.append(str(chunk)) or [(str(chunk), 0.0)])
    monkeypatch.setattr(harness, "is_cancelled", lambda: next(checks))
    with pytest.raises(Exception, match="cancelled"):
        harness.transcribe_audio_with_timestamps(str(audio))
    assert not chunk.exists()


def test_status_keeps_active_job_url(tmp_path):
    class Manager(mod.WebJobManager):
        def _run(self, url, num_clips, add_captions, add_hook, subtitle_language, instruction):
            self.thread = None

    manager = Manager(app_dir=tmp_path)
    manager.start({"url": "https://www.youtube.com/watch?v=abc"})
    thread = manager.thread
    if thread:
        thread.join(1)
    assert manager.status()["url"] == "https://www.youtube.com/watch?v=abc"


def test_rejects_empty_url(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    result = manager.start({"url": ""})
    assert result["status"] == "error"
    assert "url" in result["message"].lower()


def test_rejects_non_dict_start_payload(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    result = manager.start(None)
    assert result["status"] == "error"


def test_check_ai_provider_requires_fields(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    result = manager.check_ai_provider({"base_url": "", "api_key": "", "model": ""})
    assert result["status"] == "error"
    assert "Base URL" in result["message"]


def test_api_caption_setting_is_ignored_for_local_default(tmp_path):
    class Manager(mod.WebJobManager):
        def _run(self, url, num_clips, add_captions, add_hook, subtitle_language, instruction):
            self.captured = {"add_captions": add_captions}
            self.thread = None
    manager = Manager(app_dir=tmp_path)
    manager.save_settings({"subtitle_engine": "api"})
    result = manager.start({"url": "https://www.youtube.com/watch?v=abc", "add_captions": True})
    thread = manager.thread
    if thread:
        thread.join(1)
    assert result["status"] == "queued"
    assert manager.captured["add_captions"] is True


def test_unsupported_screen_size_is_ignored(tmp_path):
    class Manager(mod.WebJobManager):
        def _run(self, url, num_clips, add_captions, add_hook, subtitle_language, instruction):
            self.captured = {"url": url}
            self.thread = None
    manager = Manager(app_dir=tmp_path)
    result = manager.start({"url": "https://www.youtube.com/watch?v=abc", "screen_size": "1:1"})
    thread = manager.thread
    if thread:
        thread.join(1)
    assert result["status"] == "queued"


def test_rejects_when_busy(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    manager.thread = type("Thread", (), {"is_alive": lambda self: True})()
    result = manager.start({"url": "https://www.youtube.com/watch?v=abc"})
    assert result == {"status": "busy", "message": "Processing is already running"}


def test_save_settings_never_returns_api_key(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    saved = manager.save_settings({
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key": "secret-key",
        "model": "gemini-3-flash-preview",
        "subtitle_language": "id",
        "output_dir": str(tmp_path / "out"),
    })
    assert saved["status"] == "saved"
    assert saved["settings"]["api_key"] == ""
    assert saved["settings"]["api_key_saved"] is True
    settings = manager.get_settings()
    assert settings["api_key"] == ""
    assert settings["api_key_saved"] is True
    assert settings["model"] == "gemini-3-flash-preview"


def test_clear_api_key_removes_saved_key(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    manager.save_settings({"api_key": "secret-key"})
    manager.save_settings({"clear_api_key": True})
    settings = manager.get_settings()
    assert settings["api_key_saved"] is False


def test_provider_keys_can_be_cleared_independently(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    manager.save_settings({"api_key": "gemini-secret", "caption_api_key": "groq-secret"})
    manager.save_settings({"clear_highlight_api_key": True})
    settings = manager.get_settings()
    assert settings["api_key_saved"] is False
    assert settings["caption_key_saved"] is True
    manager.save_settings({"clear_caption_api_key": True})
    settings = manager.get_settings()
    assert settings["caption_key_saved"] is False


def test_custom_output_dir_is_not_accepted_as_download_root(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    manager.save_settings({"output_dir": str(outside)})
    assert manager.get_settings()["output_dir"] == str(tmp_path / "output")
    assert manager._output_root() == tmp_path / "output"


def test_partial_caption_provider_gets_groq_defaults_and_removes_obsolete_config(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "api_key": "",
        "ai_providers": {"caption_maker": {"api_key": "groq-secret"}},
        "subtitle_engine": "local",
        "local_whisper": {"model": "old"},
        "mediapipe_settings": {"switch_threshold": 0.3},
        "face_tracking_mode": "mediapipe",
    }), encoding="utf-8")
    manager = mod.WebJobManager(app_dir=tmp_path)
    cfg = manager._config().config
    caption = cfg["ai_providers"]["caption_maker"]
    assert caption["base_url"] == mod.GROQ_BASE_URL
    assert caption["model"] == mod.GROQ_MODEL
    assert caption["api_key"] == "groq-secret"
    assert "subtitle_engine" not in cfg
    assert "local_whisper" not in cfg
    assert "mediapipe_settings" not in cfg
    assert cfg["face_tracking_mode"] == "center"


def test_text_style_settings_are_validated(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    settings = manager.save_settings({
        "hook_style": {
            "font_family": "Unknown Font",
            "font_weight": "broken",
            "text_color": "red",
            "outline_color": "#112233",
            "outline_thickness": 99,
        },
        "subtitle": {
            "font_family": "Poppins",
            "font_weight": 555,
            "text_color": "#ABCDEF",
            "color": "invalid",
            "outline_color": "#123456",
            "outline_thickness": -4,
        },
    })["settings"]
    assert settings["hook_style"]["font_family"] == "Plus Jakarta Sans"
    assert settings["hook_style"]["font_weight"] == 800
    assert settings["hook_style"]["text_color"] == "#FFD700"
    assert settings["hook_style"]["outline_color"] == "#112233"
    assert settings["hook_style"]["outline_thickness"] == 6.0
    assert settings["subtitle"]["font_family"] == "Poppins"
    assert settings["subtitle"]["font_weight"] == 600
    assert settings["subtitle"]["text_color"] == "#ABCDEF"
    assert settings["subtitle"]["color"] == "#00BFFF"
    assert settings["subtitle"]["outline_color"] == "#123456"
    assert settings["subtitle"]["outline_thickness"] == 0.0


def test_activity_log_records_to_console(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    result = manager.log_activity({"action": "download_click", "detail": "clip.mp4"})
    assert result == {"status": "logged"}
    assert manager.list_activities()["activities"][0]["action"] == "download_click"
    assert "[Activity] download_click: clip.mp4" in manager.status()["logs"][-1]


def test_invalid_activity_payload_rejected(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    assert manager.log_activity(None)["status"] == "error"


def test_save_settings_updates_title_provider_too(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    manager.save_settings({"base_url": "https://example.test/v1", "api_key": "secret-key", "model": "gemini-test"})
    cfg = manager._config().config
    assert cfg["ai_providers"]["highlight_finder"]["model"] == "gemini-test"
    assert cfg["ai_providers"]["youtube_title_maker"]["model"] == "gemini-test"
    assert cfg["ai_providers"]["caption_maker"]["model"] == "whisper-large-v3-turbo"


def test_indonesian_instruction_adds_viral_criteria(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    prompt = manager._with_indonesian_instruction("base", "fokus lucu")
    assert "penonton Indonesia" in prompt
    assert "berpotensi viral" in prompt
    assert "Arahan pengguna: fokus lucu" in prompt


def test_cookie_status_detects_missing_and_present_file(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    assert manager.cookie_status() == {"exists": False, "path": str(tmp_path / "cookie.txt")}
    (tmp_path / "cookie.txt").write_text("cookie")
    assert manager.cookie_status() == {"exists": True, "path": str(tmp_path / "cookie.txt")}


def test_download_mixin_does_not_fall_back_to_cwd_cookie(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path / "user")
    (tmp_path / "cookies.txt").write_text("global", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    core = object.__new__(mod.AutoClipperCore)
    core.cookies_path = None
    assert core._cookies_path() is None
    core.cookies_path = manager.core_cookie_file
    assert core._cookies_path() is None
    manager.save_cookies("SID=user")
    assert core._cookies_path() == manager.core_cookie_file


def test_blank_output_dir_falls_back_to_default(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    result = manager.save_settings({"output_dir": ""})
    assert result["status"] == "saved"
    assert manager.get_settings()["output_dir"] == str(tmp_path / "output")


def test_cookie_txt_syncs_to_core_cookies_txt(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    result = manager.save_cookies("SID=abc; HSID=def; path=/; HttpOnly; Secure")
    assert result["status"] == "saved"
    assert result["success"] is True
    assert result["cookies"] == {"exists": True, "path": str(tmp_path / "cookie.txt")}
    assert "# Netscape HTTP Cookie File" in (tmp_path / "cookies.txt").read_text()
    assert "\tSID\tabc" in (tmp_path / "cookies.txt").read_text()


def test_instruction_prompt_includes_user_direction(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    prompt = manager._with_indonesian_instruction("base", "fokus konflik")
    assert "Arahan pengguna: fokus konflik" in prompt


def test_settings_response_serializes_without_secret(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    settings = manager.save_settings({"api_key": "secret-key"})["settings"]
    raw = json.dumps(settings)
    assert "secret-key" not in raw
    assert settings["api_key"] == ""
    assert settings["api_key_saved"] is True


def test_status_sanitizes_login_file_errors(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    manager._error = "cookies.txt not found at cookie.txt"
    raw = json.dumps(manager.status()).lower()
    assert "cookie" not in raw
    assert "login file" in raw


class InstantJobManager(mod.WebJobManager):
    def _run(self, url, num_clips, add_captions, add_hook, subtitle_language, instruction):
        self.captured = {
            "url": url,
            "num_clips": num_clips,
            "add_captions": add_captions,
            "instruction": instruction,
        }
        self._status = "complete"
        self._message = "Complete"
        self._progress = 1.0
        self.thread = None


def test_start_rejects_unsupported_top_level_video_quality(tmp_path):
    manager = InstantJobManager(app_dir=tmp_path)
    result = manager.start({"url": "https://www.youtube.com/watch?v=abc", "video_quality": "2160"})
    assert result == {"status": "error", "message": "Kualitas video harus 480, 720, 1080, atau 1440"}
    assert manager.thread is None


def test_render_settings_rejects_persisted_unsupported_quality(tmp_path):
    manager = InstantJobManager(app_dir=tmp_path)
    with pytest.raises(mod.LayoutModeError, match="480, 720, 1080, atau 1440"):
        manager._render_settings({}, {"video_quality": "2160"})


def test_start_video_quality_does_not_reset_saved_model(tmp_path):
    manager = InstantJobManager(app_dir=tmp_path)
    manager.save_settings({"model": "gemini-3.5-flash", "base_url": "https://example.test/v1", "api_key": "secret-key"})
    assert manager._config().config["model"] == "gemini-3.5-flash"
    assert manager._config().config["ai_providers"]["highlight_finder"]["model"] == "gemini-3.5-flash"
    manager.start({"url": "https://www.youtube.com/watch?v=abc", "video_quality": "480"})
    thread = manager.thread
    if thread:
        thread.join(1)
    cfg = manager._config().config
    assert cfg["video_quality"] == "480"
    assert cfg["model"] == "gemini-3.5-flash"
    assert cfg["ai_providers"]["highlight_finder"]["model"] == "gemini-3.5-flash"
    assert cfg["ai_providers"]["youtube_title_maker"]["model"] == "gemini-3.5-flash"


def test_num_clips_accepts_allowed_values(tmp_path):
    manager = InstantJobManager(app_dir=tmp_path)
    manager.start({"url": "https://www.youtube.com/watch?v=abc", "add_captions": False, "num_clips": 3})
    thread = manager.thread
    if thread:
        thread.join(1)
    assert manager.captured["num_clips"] == 3


def test_num_clips_rejects_unsupported_values(tmp_path):
    manager = InstantJobManager(app_dir=tmp_path)
    manager.start({"url": "https://www.youtube.com/watch?v=abc", "add_captions": False, "num_clips": 999})
    thread = manager.thread
    if thread:
        thread.join(1)
    assert manager.captured["num_clips"] == 1


def test_invalid_num_clips_still_generates_one_clip(tmp_path):
    manager = InstantJobManager(app_dir=tmp_path)
    manager.start({"url": "https://www.youtube.com/watch?v=abc", "add_captions": False, "num_clips": "bad"})
    thread = manager.thread
    if thread:
        thread.join(1)
    assert manager.captured["num_clips"] == 1


def test_instruction_is_trimmed_and_limited(tmp_path):
    manager = InstantJobManager(app_dir=tmp_path)
    manager.start({"url": "https://www.youtube.com/watch?v=abc", "add_captions": False, "instruction": "  " + "x" * 1200})
    thread = manager.thread
    if thread:
        thread.join(1)
    assert manager.captured["instruction"] == "x" * 1000


def test_youtube_url_alias_starts_job(tmp_path):
    manager = InstantJobManager(app_dir=tmp_path)
    result = manager.start({"youtube_url": "https://www.youtube.com/watch?v=abc", "add_captions": False})
    thread = manager.thread
    if thread:
        thread.join(1)
    assert result == {"status": "queued", "queue_position": 1}
    assert manager.captured["url"] == "https://www.youtube.com/watch?v=abc"


def test_sixteen_by_nine_screen_size_is_ignored(tmp_path):
    manager = InstantJobManager(app_dir=tmp_path)
    result = manager.start({"url": "https://www.youtube.com/watch?v=abc", "add_captions": False, "screen_size": "16:9"})
    thread = manager.thread
    if thread:
        thread.join(1)
    assert result == {"status": "queued", "queue_position": 1}


class LegacySevenArgJobManager(mod.WebJobManager):
    def _run(self, url, num_clips, add_captions, add_hook, subtitle_language, instruction, landscape_blur):
        self.captured = {"landscape_blur": landscape_blur}
        self.thread = None


def test_legacy_seven_arg_run_gets_landscape_blur_forced_off(tmp_path):
    manager = LegacySevenArgJobManager(app_dir=tmp_path)
    result = manager.start({"url": "https://www.youtube.com/watch?v=abc", "add_captions": False, "landscape_blur": True})
    thread = manager.thread
    if thread:
        thread.join(1)
    assert result == {"status": "queued", "queue_position": 1}
    assert manager.captured["landscape_blur"] is False


def test_nested_provider_settings_are_supported(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    result = manager.save_settings({
        "provider": {"base_url": "https://api.example.com/v1", "api_key": "secret-key", "model": "gpt-4"},
        "subtitle_language": "en",
        "output_dir": str(tmp_path / "out"),
    })
    settings = result["settings"]
    assert settings["provider"] == {"base_url": "https://api.example.com/v1", "api_key": "", "model": "gpt-4"}
    assert result["local_ai_provider"] == settings["provider"]
    assert settings["api_key_saved"] is True


def test_cookie_exists_top_level_flag(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    assert manager.get_settings()["cookie_exists"] is False
    manager.save_cookies("SID=abc")
    assert manager.get_settings()["cookie_exists"] is True


class SubtitleHarness(ExportMixin):
    subtitle_style = {
        "font_family": "Poppins",
        "size": 60,
        "font_weight": 400,
        "text_color": "#11AA22",
        "color": "#123456",
        "outline_color": "#654321",
        "outline_thickness": 2.0,
        "position_x": 0.4,
        "position_y": 0.8,
    }
    landscape_blur = False

    def format_time(self, seconds):
        centiseconds = int(round(seconds * 100))
        h, rem = divmod(centiseconds, 360000)
        m, rem = divmod(rem, 6000)
        s, cs = divmod(rem, 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def test_ass_subtitle_groups_words_in_dynamic_chunks(tmp_path):
    transcript = {
        "duration": 2.0,
        "words": [
            {"word": f"w{i}", "start": i * 0.2, "end": i * 0.2 + 0.1}
            for i in range(7)
        ],
        "segments": [],
    }
    output = tmp_path / "sub.ass"
    count = SubtitleHarness().create_ass_subtitle_capcut(transcript, str(output))
    text = output.read_text(encoding="utf-8")
    assert count == 7
    assert "PlayResX: 720" in text
    assert "Fontname, Fontsize" in text
    assert "Style: Default,Poppins,40,&H0022AA11,&H0022AA11,&H00214365" in text
    assert ",0,0,0,0,100,100,0.00,0,1,4,0,5," in text
    assert "{\\pos(288,1024)\\b400}" in text
    assert "{\\c&H00563412}" in text
    assert "w0" in text and "w1" in text


def test_hook_overlay_uses_selected_colors_weight_and_outline(tmp_path):
    from PIL import Image

    harness = object.__new__(SubtitleHarness)
    harness.hook_style_settings = {
        "font_family": "Plus Jakarta Sans",
        "font_weight": 400,
        "font_size": 0.054,
        "text_color": "#FF0000",
        "outline_color": "#00FF00",
        "outline_thickness": 3.0,
        "position_x": 0.5,
        "position_y": 0.2,
    }
    output = tmp_path / "hook.png"
    harness._create_hook_overlay("TEST", 340, 604, output)
    image = Image.open(output).convert("RGBA")
    colors = image.getdata()
    assert any(red > 200 and green < 80 and blue < 80 and alpha > 0 for red, green, blue, alpha in colors)
    assert any(green > 200 and red < 80 and blue < 80 and alpha > 0 for red, green, blue, alpha in colors)


def test_hook_wrap_uses_preview_width():
    from PIL import ImageFont

    font = ImageFont.truetype(str(ROOT / "fonts" / "PlusJakartaSans.ttf"), 33)
    font.set_variation_by_axes([800])
    lines = SubtitleHarness()._wrap_preview_text("JUDUL VIDEO VIRAL BIKIN PENASARAN", font, 648)
    assert lines == ["JUDUL VIDEO VIRAL BIKIN PENASARAN"]


def test_high_resolution_caps_parallel_cpu_workers():
    assert mod.WebJobManager._parallel_workers_for_quality(3, "720") == 3
    assert mod.WebJobManager._parallel_workers_for_quality(3, "1080") == 2
    assert mod.WebJobManager._parallel_workers_for_quality(3, "1440") == 1
    assert mod.WebJobManager._parallel_workers_for_quality(3, "2160") == 1


def test_high_resolution_uses_ultrafast_cpu_encoder():
    harness = object.__new__(FfmpegMixin)
    harness.gpu_enabled = False
    harness.gpu_encoder_args = []
    harness.optimize_mode = "hosting_2cpu"
    harness.video_quality = "1440"
    assert harness.get_video_encoder_args() == ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28']
    harness.video_quality = "720"
    assert harness.get_video_encoder_args() == ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '28']


def test_due_youtube_upload_persists_public_result(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    (clip_dir / "master.mp4").write_bytes(b"x")
    (clip_dir / "data.json").write_text(json.dumps({"youtube_upload": {"status": "scheduled", "scheduled_at": "2000-01-01T00:00:00+00:00", "title": "Judul", "description": ""}}), encoding="utf-8")
    captured = {}
    monkeypatch.setattr(mod, "upload_youtube_video", lambda path, title, description, privacy, user_id: captured.update(path=path, title=title, privacy=privacy, user_id=user_id) or {"video_id": "abc", "url": "https://youtube.test/watch?v=abc"})
    manager.process_due_youtube_uploads()
    upload = json.loads((clip_dir / "data.json").read_text(encoding="utf-8"))["youtube_upload"]
    assert captured["privacy"] == "public"
    assert upload["status"] == "uploaded"
    assert upload["video_id"] == "abc"


def test_list_clips_exposes_draft_workflow_state(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    (clip_dir / "draft.mp4").write_bytes(b"x")
    (clip_dir / "data.json").write_text(json.dumps({"clip_id": "clip-1", "status": "needs_edit", "title": "Draft"}), encoding="utf-8")
    result = manager.list_clips()
    assert result["clips"][0]["clip_id"] == "clip-1"
    assert result["clips"][0]["status"] == "needs_edit"
    assert "clip_id=clip-1&artifact=draft" in result["clips"][0]["stream_url"]
    assert "draft.mp4" not in result["clips"][0]["stream_url"]


def test_editor_defaults_enable_subtitles_and_use_larger_foreground(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    defaults = manager._editor_defaults_local()
    assert defaults["subtitle"]["enabled"] is True
    assert defaults["subtitle"]["text_transform"] == "none"
    assert defaults["blur_background"]["scale"] == 1.6
    assert defaults["blur_background"]["enabled"] is False


def test_render_settings_ignore_client_style_without_mutating_defaults(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    settings = manager._render_settings({"settings": {"hook_style": {"enabled": True, "position_y": 0.3}}}, {})
    assert settings["hook_style"]["enabled"] is True
    assert settings["hook_style"]["position_y"] == 0.62
    assert manager.get_settings()["hook_style"]["position_y"] != 0.3


def test_render_settings_use_draft_snapshot_after_defaults_change(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    manager.save_settings({"video_quality": "480", "blur_background": {"enabled": False, "strength": 1}})
    metadata = {"draft_settings": {"landscape_blur": True, "blur_background": {"enabled": True, "strength": 30}, "video_quality": "1080", "screen_size": "9:16"}}
    settings = manager._render_settings({}, metadata)
    assert settings["landscape_blur"] is False
    assert settings["blur_background"]["enabled"] is False
    assert settings["video_quality"] == "1080"


def test_render_settings_prefer_clip_quality_over_global_default(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    manager.save_settings({"video_quality": "1080"})
    settings = manager._render_settings({}, {"video_quality": "480", "draft_settings": {"video_quality": "480"}})
    assert settings["video_quality"] == "480"


def test_local_renderer_accepts_progress_callback():
    stages = []
    renderer = LocalClipRenderer(progress_callback=lambda stage, progress=None: stages.append((stage, progress)))
    renderer.set_progress("Menyiapkan video", 0.25)
    assert stages == [("Menyiapkan video", 0.25)]


def test_legacy_clip_view_probes_and_persists_source_geometry(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    (clip_dir / "source.mp4").write_bytes(b"source")
    meta_path = clip_dir / "data.json"
    metadata = {"clip_id": "geometry", "status": "needs_edit"}
    meta_path.write_text(json.dumps(metadata), encoding="utf-8")
    monkeypatch.setattr(manager, "_source_geometry", lambda _path: {"width": 820, "height": 480, "is_landscape": True})
    view = manager._clip_view(meta_path, metadata)
    assert view["source_geometry"]["is_landscape"] is True
    assert json.loads(meta_path.read_text(encoding="utf-8"))["source_geometry"]["width"] == 820


def test_preview_render_removed_in_v3(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    (clip_dir / "source.mp4").write_bytes(b"source")
    (clip_dir / "data.json").write_text(json.dumps({"clip_id": "preview", "status": "needs_edit"}), encoding="utf-8")
    result = manager.render_clip({"clip_id": "preview", "settings": {"subtitle": {"enabled": False}}}, preview=True)
    assert result == {"status": "error", "message": "Preview akurat dihapus di V3. Gunakan render final."}


def test_failed_final_render_preserves_existing_master(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    master = clip_dir / "master.mp4"
    master.write_bytes(b"old-master")
    meta_path = clip_dir / "data.json"
    metadata = {"clip_id": "final", "status": "needs_edit", "render_revision": 2, "draft_settings": {"landscape_blur": False, "blur_background": {"enabled": False}, "video_quality": "720", "screen_size": "9:16"}}
    meta_path.write_text(json.dumps(metadata), encoding="utf-8")

    class Renderer:
        def __init__(self, **_kwargs):
            pass

        def render_existing_clip(self, *_args, **_kwargs):
            raise RuntimeError("technical details")

    monkeypatch.setattr(mod, "LocalClipRenderer", Renderer)
    assert mod._GLOBAL_FINAL_RENDER_LOCK.acquire(blocking=False)
    manager._render_clip_file(meta_path, metadata, manager._render_settings({}, metadata), clip_dir / "master.tmp.mp4", True)
    saved = json.loads(meta_path.read_text(encoding="utf-8"))
    assert master.read_bytes() == b"old-master"
    assert saved["status"] == "render_error"
    assert saved["render_error"] == "Render gagal. Periksa source klip lalu coba lagi."


def test_clip_upload_lifecycle_uses_clip_id_without_client_path(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    (clip_dir / "master.mp4").write_bytes(b"x")
    (clip_dir / "data.json").write_text(json.dumps({"clip_id": "ready", "status": "ready_to_schedule", "title": "Judul"}), encoding="utf-8")
    monkeypatch.setattr(mod, "upload_youtube_video", lambda *_args: {"video_id": "id", "url": "https://youtube.test/id"})
    # V3: immediate upload disabled — schedule only
    result = manager.upload_clip_now({"clip_id": "ready", "title": "Judul baru", "description": "Deskripsi"})
    assert result["status"] == "error"
    assert "Jadwalkan" in result["message"] or "10 menit" in result["message"]
    metadata = json.loads((clip_dir / "data.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "ready_to_schedule"
    assert "youtube_upload" not in metadata


def test_render_settings_normalize_untrusted_editor_values(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    metadata = {"draft_settings": {"landscape_blur": True, "blur_background": {"enabled": True}, "video_quality": "1080"}}
    settings = manager._render_settings({"settings": {"hook_style": {"font_family": "Invalid", "font_weight": 999, "font_size": 99, "text_color": "bad", "position_x": -2}, "blur_background": {"zoom": 99, "strength": -1}}}, metadata)
    assert settings["hook_style"]["font_family"] == "Poppins"
    assert settings["hook_style"]["font_weight"] == 700
    assert settings["hook_style"]["font_size"] == 0.070  # locked compact hook preset
    assert settings["hook_style"]["position_x"] == 0.5
    assert settings["hook_style"]["text_color"].startswith("#")
    assert settings["blur_background"]["enabled"] is False


def test_upload_error_retry_returns_to_schedule_panel(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    (clip_dir / "master.mp4").write_bytes(b"final")
    metadata = {"clip_id": "retry", "status": "upload_error", "title": "Judul", "youtube_upload": {"status": "error", "title": "Judul retry", "description": "Desc"}}
    (clip_dir / "data.json").write_text(json.dumps(metadata), encoding="utf-8")
    monkeypatch.setattr(mod, "upload_youtube_video", lambda *_args: {"video_id": "retried", "url": "https://youtube.test/retried"})
    result = manager.retry_clip_upload({"clip_id": "retry", "upload_now": True})
    saved = json.loads((clip_dir / "data.json").read_text(encoding="utf-8"))
    assert result["status"] == "ready"
    assert saved["status"] == "ready_to_schedule"
    assert "youtube_upload" not in saved
    assert saved["pending_youtube_upload"]["title"] == "Judul retry"


def test_clip_views_expose_separate_files_render_and_upload_details(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    (clip_dir / "draft.mp4").write_bytes(b"draft")
    (clip_dir / "master.mp4").write_bytes(b"final")
    metadata = {
        "clip_id": "details",
        "status": "uploaded",
        "render_progress": 1.0,
        "render_stage": "Selesai",
        "render_started_at": "2026-07-13T00:00:00+00:00",
        "render_elapsed_seconds": 12.5,
        "youtube_upload": {"status": "uploaded", "video_id": "new"},
        "youtube_upload_history": [{"status": "uploaded", "video_id": "old"}],
    }
    (clip_dir / "data.json").write_text(json.dumps(metadata), encoding="utf-8")
    listed = manager.list_clips()["clips"][0]
    fetched = manager.get_clip("details")["clip"]
    for clip in (listed, fetched):
        assert "artifact=draft" in clip["draft_url"]
        assert "artifact=final" in clip["final_url"]
        assert "artifact=final&download=1" in clip["final_download_url"]
        assert "draft.mp4" not in clip["draft_url"]
        assert "master.mp4" not in clip["final_url"]
        assert clip["final_file"] == {"exists": True, "size": 5}
        assert clip["render"]["progress"] == 1.0
        assert clip["render"]["stage"] == "Selesai"
        assert clip["render"]["started_at"] == "2026-07-13T00:00:00+00:00"
        assert clip["render"]["elapsed_seconds"] == 12.5
        assert clip["youtube_upload"]["video_id"] == "new"
        assert clip["youtube_upload_history"][0]["video_id"] == "old"


def test_clip_views_allowlist_metadata_and_hide_secrets_and_paths(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    (clip_dir / "draft.mp4").write_bytes(b"draft")
    metadata = {"clip_id": "safe-view", "status": "needs_edit", "title": "Safe", "api_key": "secret", "token": "bearer", "cookie": "private", "source_path": "C:/private/source.mp4"}
    (clip_dir / "data.json").write_text(json.dumps(metadata), encoding="utf-8")
    clip = manager.list_clips()["clips"][0]
    assert not {"api_key", "token", "cookie", "source_path"}.intersection(clip)
    assert "C:/private" not in json.dumps(clip)
    assert manager.clip_artifact("safe-view", "draft") == clip_dir / "draft.mp4"
    assert manager.clip_artifact("missing", "draft") is None


def test_render_rejects_non_editable_state_and_persists_callback_progress(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    meta_path = clip_dir / "data.json"
    metadata = {"clip_id": "strict-render", "status": "ready_to_schedule", "draft_settings": {}}
    meta_path.write_text(json.dumps(metadata), encoding="utf-8")
    assert manager.render_clip({"clip_id": "strict-render"})["status"] == "error"
    metadata["status"] = "render_error"
    meta_path.write_text(json.dumps(metadata), encoding="utf-8")

    class Renderer:
        def __init__(self, progress_callback=None, **_kwargs):
            self.progress_callback = progress_callback

        def render_existing_clip(self, _clip_dir, _metadata, _settings, output, preview=False):
            self.progress_callback("Menyusun video", 0.6)
            output.write_bytes(b"x" * 1000)

    monkeypatch.setattr(mod, "LocalClipRenderer", Renderer)
    assert mod._GLOBAL_FINAL_RENDER_LOCK.acquire(blocking=False)
    manager._render_clip_file(meta_path, metadata, manager._render_settings({}, metadata), clip_dir / "master.tmp.mp4", True)
    saved = json.loads(meta_path.read_text(encoding="utf-8"))
    assert saved["status"] == "ready_to_schedule"
    assert saved["render_progress"] == 1.0
    assert saved["render_stage"] == "Selesai"
    assert saved["render_started_at"]
    assert saved["render_elapsed_seconds"] >= 0


def test_cancel_retry_edit_and_delete_follow_strict_lifecycle(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    (clip_dir / "master.mp4").write_bytes(b"final")
    meta_path = clip_dir / "data.json"
    meta_path.write_text(json.dumps({"clip_id": "lifecycle", "status": "ready_to_schedule"}), encoding="utf-8")
    scheduled = manager.schedule_clip_upload({"clip_id": "lifecycle", "scheduled_at": "2030-01-02T10:30", "title": "Judul jadwal", "description": "Deskripsi jadwal"})
    assert scheduled["status"] == "scheduled"
    scheduled_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert scheduled_meta["title"] == "Judul jadwal"
    assert scheduled_meta["description"] == "Deskripsi jadwal"
    assert manager.cancel_clip_upload({"clip_id": "lifecycle"})["status"] == "cancelled"
    assert json.loads(meta_path.read_text(encoding="utf-8"))["status"] == "ready_to_schedule"
    meta_path.write_text(json.dumps({"clip_id": "lifecycle", "status": "upload_error", "youtube_upload": {"status": "error"}}), encoding="utf-8")
    assert manager.retry_clip_upload({"clip_id": "lifecycle"})["status"] == "ready"
    for state in ("rendering", "render_queued", "scheduled", "uploading"):
        meta_path.write_text(json.dumps({"clip_id": "lifecycle", "status": state}), encoding="utf-8")
        assert manager.delete_clip({"clip_id": "lifecycle"})["status"] == "error"
        assert clip_dir.exists()
    meta_path.write_text(json.dumps({"clip_id": "lifecycle", "status": "needs_edit"}), encoding="utf-8")
    monkeypatch.setattr(mod.shutil, "rmtree", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("private path")))
    result = manager.delete_clip({"clip_id": "lifecycle"})
    assert result == {"status": "error", "message": "Klip gagal dihapus"}


def test_upload_now_disabled_rejects_immediate_publish(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    (clip_dir / "master.mp4").write_bytes(b"final")
    meta_path = clip_dir / "data.json"
    meta_path.write_text(json.dumps({"clip_id": "claim", "status": "ready_to_schedule", "render_revision": 3}), encoding="utf-8")
    uploads = []
    monkeypatch.setattr(mod, "upload_youtube_video", lambda *_args: uploads.append(1) or {"video_id": "one", "url": "https://youtube.test/one"})
    first = manager.upload_clip_now({"clip_id": "claim"})
    second = manager.upload_clip_now({"clip_id": "claim"})
    assert first["status"] == "error"
    assert second["status"] == "error"
    assert uploads == []
    assert json.loads(meta_path.read_text(encoding="utf-8"))["status"] == "ready_to_schedule"


def test_stale_render_completion_cannot_replace_newer_attempt(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    master = clip_dir / "master.mp4"
    master.write_bytes(b"current")
    meta_path = clip_dir / "data.json"
    metadata = {"clip_id": "cas-render", "status": "rendering", "attempt_id": "old", "render_base_revision": 1, "render_revision": 1, "draft_settings": {}}
    meta_path.write_text(json.dumps({**metadata, "attempt_id": "new", "render_base_revision": 1}), encoding="utf-8")

    class Renderer:
        def __init__(self, **_kwargs):
            pass

        def render_existing_clip(self, _clip_dir, _metadata, _settings, output, preview=False):
            output.write_bytes(b"stale" * 300)

    monkeypatch.setattr(mod, "LocalClipRenderer", Renderer)
    assert mod._GLOBAL_FINAL_RENDER_LOCK.acquire(blocking=False)
    manager._render_clip_file(meta_path, metadata, manager._render_settings({}, metadata), clip_dir / "master.old.tmp.mp4", True)
    assert master.read_bytes() == b"current"
    assert json.loads(meta_path.read_text(encoding="utf-8"))["attempt_id"] == "new"


def test_recovery_marks_stale_upload_and_render_states(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    states = [("uploading", {"youtube_upload": {"status": "uploading", "attempt_id": "u", "uploading_at": stale}}), ("rendering", {"attempt_id": "r", "render_started_at": stale}), ("render_queued", {"attempt_id": "q", "render_queued_at": stale})]
    paths = []
    for index, (status, extra) in enumerate(states):
        clip_dir = tmp_path / "output" / "run" / f"clip-{index}"
        clip_dir.mkdir(parents=True)
        path = clip_dir / "data.json"
        path.write_text(json.dumps({"clip_id": f"stale-{index}", "status": status, **extra}), encoding="utf-8")
        paths.append(path)
    manager.recover_stale_clip_operations()
    assert [json.loads(path.read_text(encoding="utf-8"))["status"] for path in paths] == ["upload_error", "render_error", "render_error"]


def test_auto_render_sets_render_started_at_so_recovery_skips_fresh(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    meta_path = clip_dir / "data.json"
    meta_path.write_text(json.dumps({"clip_id": "auto-fresh", "status": "needs_edit", "draft_settings": {}}), encoding="utf-8")

    class Renderer:
        def __init__(self, **kwargs):
            self.progress_callback = kwargs.get("progress_callback")

        def render_existing_clip(self, _clip_dir, _metadata, _settings, output, preview=False):
            if self.progress_callback:
                self.progress_callback("Menyusun video final", 0.4)
            output.write_bytes(b"final" * 300)

    monkeypatch.setattr(mod, "LocalClipRenderer", Renderer)
    monkeypatch.setattr(manager, "_render_settings", lambda _payload, _meta: {
        "watermark": {}, "credit_watermark": {}, "hook_style": {}, "blur_background": {},
        "subtitle": {}, "video_quality": "480",
    })
    monkeypatch.setattr(manager, "_hook_tts_config", lambda: {})
    results = manager._auto_render_run(tmp_path / "output" / "run")
    saved = json.loads(meta_path.read_text(encoding="utf-8"))
    assert results == [{"clip_id": "auto-fresh", "status": "ready_to_schedule"}]
    assert saved["status"] == "ready_to_schedule"
    assert saved["render_started_at"]
    assert datetime.fromisoformat(saved["render_started_at"]).tzinfo is not None
    assert saved["render_progress"] == 1.0
    # fresh timestamp must not be recovered as stale
    meta_path.write_text(json.dumps({
        "clip_id": "auto-fresh", "status": "rendering", "attempt_id": "a",
        "render_started_at": datetime.now(timezone.utc).isoformat(),
    }), encoding="utf-8")
    manager.recover_stale_clip_operations()
    assert json.loads(meta_path.read_text(encoding="utf-8"))["status"] == "rendering"
    # missing timestamp still recovered (stale / crash path)
    meta_path.write_text(json.dumps({"clip_id": "auto-fresh", "status": "rendering", "attempt_id": "b"}), encoding="utf-8")
    manager.recover_stale_clip_operations()
    assert json.loads(meta_path.read_text(encoding="utf-8"))["status"] == "render_error"


def test_retention_skips_active_clip_sessions(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    for index, status in enumerate(("render_queued", "rendering", "scheduled", "uploading")):
        run = tmp_path / "output" / f"run-{index}"
        clip = run / "clip"
        clip.mkdir(parents=True)
        (run / "run.json").write_text(json.dumps({"status": "staged", "file_exists": True}), encoding="utf-8")
        (clip / "data.json").write_text(json.dumps({"clip_id": str(index), "status": status}), encoding="utf-8")
        (clip / "draft.mp4").write_bytes(b"active")
    manager._enforce_retention(max_active=0)
    assert all((tmp_path / "output" / f"run-{index}" / "clip" / "draft.mp4").exists() for index in range(4))


def test_section_format_has_hard_cap_and_fast_codec_sort():
    harness = object.__new__(DownloadMixin)
    harness.video_quality = "1080"
    selector = harness._format_selector()
    assert selector.count("height<=1080") == 4
    assert selector.endswith("best[height<=1080]")
    assert all("height<=1080" in fallback for fallback in selector.split("/"))
    assert harness._format_sort() == ["res", "fps:30", "br"]


def test_cpu_1080_encoder_uses_upload_quality_crf():
    harness = object.__new__(LocalClipRenderer)
    harness.gpu_enabled = False
    harness.gpu_encoder_args = []
    harness.video_quality = "1080"
    harness.optimize_mode = "hosting_2cpu"
    assert harness.get_video_encoder_args() == ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"]


def test_section_download_does_not_force_reencode():
    source = (ROOT / "clipper_download.py").read_text(encoding="utf-8")
    assert "force_keyframes_at_cuts" not in source
    assert "--force-keyframes-at-cuts" not in source
    assert "concurrent_fragment_downloads': 4" in source


def test_final_composite_uses_one_encode_and_separate_audio_source(tmp_path):
    harness = object.__new__(SubtitleHarness)
    harness.ffmpeg_path = "ffmpeg"
    harness.output_resolution = "720:1280"
    harness.hook_style_settings = {"duration": 5.0}
    harness.watermark_settings = {"enabled": False}
    harness.get_video_encoder_args = lambda: ["-c:v", "libx264", "-preset", "veryfast"]
    command = harness._build_composite_command(
        "portrait.mp4",
        "master.mp4",
        10.0,
        audio_source="section.mp4",
        hook_overlay=tmp_path / "hook.png",
        ass_file=tmp_path / "captions.ass",
        credit_overlay=tmp_path / "credit.png",
    )
    filter_graph = command[command.index("-filter_complex") + 1]
    assert command.count("-c:v") == 1
    assert command[command.index("-map", command.index("-map") + 1) + 1] == "[aout]"
    assert "[1:a]asetpts=PTS-STARTPTS,loudnorm=I=-14:LRA=7:TP=-1[aout]" in filter_graph
    assert filter_graph.index("overlay=0:0:enable") < filter_graph.index("ass=") < filter_graph.rindex("overlay=0:0")


def test_hook_tts_freezes_video_and_plays_before_original_audio(tmp_path):
    harness = object.__new__(SubtitleHarness)
    harness.ffmpeg_path = "ffmpeg"
    harness.output_resolution = "720:1280"
    harness.hook_style_settings = {"duration": 5.0}
    harness.watermark_settings = {"enabled": False}
    harness.get_video_encoder_args = lambda: ["-c:v", "libx264"]
    command = harness._build_composite_command(
        "portrait.mp4",
        "master.mp4",
        10.0,
        audio_source="section.mp4",
        hook_overlay=tmp_path / "hook.png",
        tts_source=tmp_path / "hook.wav",
        intro_duration=2.75,
    )
    graph = command[command.index("-filter_complex") + 1]
    assert "trim=start_frame=0:end_frame=1" in graph
    assert "tpad=stop_mode=clone:stop_duration=2.750" in graph
    assert "concat=n=2:v=1:a=0" in graph
    assert "[2:a]aresample=48000" in graph
    assert "[1:a]aresample=48000" in graph
    assert "concat=n=2:v=0:a=1,loudnorm=I=-14:LRA=7:TP=-1[aout]" in graph
    assert "amix" not in graph
    assert "enable='between(t,0,2.750)'" in graph
    assert command[command.index("-t") + 1] == "12.750"


def test_prefilter_transcript_keeps_viral_signals(tmp_path):

    core = object.__new__(AutoClipperCore)
    transcript = "\n".join(
        [f"[00:00:{i % 60:02d},000 - 00:00:{i % 60:02d},500] oke nah filler biasa {i}" for i in range(500)]
        + ["[00:10:00,000 - 00:10:10,000] gue hampir bangkrut karena masalah uang besar"]
    )
    filtered = core._prefilter_transcript_for_ai(transcript, max_chars=2000)
    assert len(filtered) <= 2000
    assert "bangkrut" in filtered


def test_short_ai_highlight_is_expanded(tmp_path):
    class Choice:
        message = SimpleNamespace(content=json.dumps([{
            "start_time": "00:01:00,000",
            "end_time": "00:01:04,000",
            "title": "Short",
            "description": "Desc",
            "virality_score": 8,
            "hook_text": "TERNYATA [ALDI TAHER] BERUBAH!",
        }]))

    class Chat:
        class completions:
            @staticmethod
            def create(**kwargs):
                return SimpleNamespace(choices=[Choice()], usage=None)

    core = object.__new__(AutoClipperCore)
    core.model = "test-model"
    core.temperature = 0
    core.system_prompt = core.get_default_prompt()
    core.highlight_client = SimpleNamespace(base_url="test", chat=Chat())
    core.log = lambda *_args, **_kwargs: None
    core.report_tokens = lambda *_args, **_kwargs: None
    result = core._find_highlights_single("[00:01:00,000 - 00:01:04,000] halo.", {"title": "video"}, 1, allow_chunking=False)
    assert result[0]["duration_seconds"] >= 10
    assert result[0]["hook_text"] == "TERNYATA [ALDI TAHER] BERUBAH!"
    assert len(result[0]["hook_text"].replace("[", "").replace("]", "").split()) <= 6


class PipelineCore(AutoClipperCore):
    def __init__(self, root, has_srt=False, parallel_workers=1):
        self.output_dir = root / "out"
        self.temp_dir = self.output_dir / "_temp"
        self.temp_dir.mkdir(parents=True)
        self.cache_dir = self.output_dir / "cache"
        self.parallel_workers = parallel_workers
        self.use_download_sections = True
        self.has_srt = has_srt
        self.downloaded_audio = 0
        self.downloaded_sections = 0
        self.transcription_calls = []
        self.caption_transcripts = {}
        self.highlight_transcript = None

    def set_progress(self, *_args):
        pass

    def is_cancelled(self):
        return False

    def download_subtitle_only(self, _url):
        if not self.has_srt:
            return None, {"title": "video"}
        path = self.temp_dir / "source.srt"
        path.write_text("srt", encoding="utf-8")
        return str(path), {"title": "video"}

    def parse_srt_timed(self, _path):
        return {
            "duration": 72.0,
            "words": [],
            "segments": [
                {"text": "pertama", "start": 9.0, "end": 12.0},
                {"text": "kedua", "start": 69.0, "end": 72.0},
            ],
        }

    def parse_srt(self, _path):
        return timed_segments_to_prompt(self.parse_srt_timed(_path))

    def download_audio_only(self, _url):
        self.downloaded_audio += 1
        path = self.temp_dir / "source_audio.mp3"
        path.write_bytes(b"audio")
        return str(path)

    def transcribe_audio_with_timestamps(self, audio_path, require_words=False):
        name = Path(audio_path).name
        self.transcription_calls.append((name, require_words))
        if name.startswith("section_"):
            word = "pertama" if name == "section_001.mp4" else "kedua"
            return {
                "duration": 3.0,
                "words": [{"word": word, "start": 0.2, "end": 0.7}],
                "segments": [{"text": word, "start": 0.1, "end": 0.9}],
            }
        return {
            "duration": 90.0,
            "words": [
                {"word": "pertama", "start": 10.0, "end": 10.5},
                {"word": "kedua", "start": 70.0, "end": 70.5},
            ],
            "segments": [
                {"text": "pertama", "start": 9.0, "end": 12.0},
                {"text": "kedua", "start": 69.0, "end": 72.0},
            ],
        }

    def download_video_section(self, _url, _start_time, _end_time, output_path):
        self.downloaded_sections += 1
        path = Path(output_path)
        path.write_bytes(b"section")
        return str(path)

    def find_highlights(self, transcript, _video_info, num_clips):
        self.highlight_transcript = transcript
        return [
            {
                "start_time": "00:00:09,000",
                "end_time": "00:00:12,000",
                "title": "first",
                "duration_seconds": 3.0,
            },
            {
                "start_time": "00:01:09,000",
                "end_time": "00:01:12,000",
                "title": "second",
                "duration_seconds": 3.0,
            },
        ][:num_clips]

    def process_clip(
        self,
        source_path,
        _highlight,
        index,
        _total_clips,
        add_captions=True,
        add_hook=True,
        pre_cut=False,
        caption_transcript=None,
    ):
        self.caption_transcripts[index] = caption_transcript
        if add_captions and caption_transcript is None:
            self.transcribe_audio_with_timestamps(source_path, require_words=True)

    def cleanup(self):
        pass

    def log(self, _message):
        pass


def test_missing_srt_transcribes_once_and_reuses_words_for_caption(tmp_path):
    core = PipelineCore(tmp_path)
    core.process("https://www.youtube.com/watch?v=abc", num_clips=2, add_captions=True)
    assert core.downloaded_audio == 1
    assert core.transcription_calls == [("source_audio.mp3", True)]
    assert core.highlight_transcript == (
        "[00:00:09,000 - 00:00:12,000] pertama\n"
        "[00:01:09,000 - 00:01:12,000] kedua"
    )
    assert core.caption_transcripts[1]["words"] == [{"word": "pertama", "start": 1.0, "end": 1.5}]
    assert core.caption_transcripts[2]["words"] == [{"word": "kedua", "start": 1.0, "end": 1.5}]


def test_missing_srt_captions_off_transcribes_once_and_retains_timed_content(tmp_path):
    core = PipelineCore(tmp_path)
    core.process("https://www.youtube.com/watch?v=abc", num_clips=2, add_captions=False)
    assert core.transcription_calls == [("source_audio.mp3", False)]
    assert core.caption_transcripts[1]["segments"][0]["text"] == "pertama"
    assert core.caption_transcripts[2]["segments"][0]["text"] == "kedua"


def test_srt_finds_highlights_then_transcribes_selected_sections_for_word_timing(tmp_path):
    core = PipelineCore(tmp_path, has_srt=True)
    core.process("https://www.youtube.com/watch?v=abc", num_clips=2, add_captions=True)
    assert core.highlight_transcript == (
        "[00:00:09,000 - 00:00:12,000] pertama\n"
        "[00:01:09,000 - 00:01:12,000] kedua"
    )
    assert core.downloaded_audio == 0
    assert core.transcription_calls == [("section_001.mp4", True), ("section_002.mp4", True)]
    assert core.caption_transcripts[1]["words"] == [{"word": "pertama", "start": 0.2, "end": 0.7}]
    assert core.caption_transcripts[2]["words"] == [{"word": "kedua", "start": 0.2, "end": 0.7}]


def test_srt_captions_off_never_calls_groq(tmp_path):
    core = PipelineCore(tmp_path, has_srt=True)
    core.process("https://www.youtube.com/watch?v=abc", num_clips=2, add_captions=False)
    assert core.downloaded_audio == 0
    assert core.transcription_calls == []


def test_parallel_missing_srt_transcribes_once_and_passes_distinct_slices(tmp_path):
    core = PipelineCore(tmp_path, parallel_workers=2)
    core.process("https://www.youtube.com/watch?v=abc", num_clips=2, add_captions=True)
    assert core.transcription_calls == [("source_audio.mp3", True)]
    assert core.caption_transcripts[1]["words"][0]["word"] == "pertama"
    assert core.caption_transcripts[2]["words"][0]["word"] == "kedua"
    assert core.caption_transcripts[1] is not core.caption_transcripts[2]


def timed_words(*words, duration=5.0):
    return {
        "duration": duration,
        "words": [
            {"word": word, "start": start, "end": end}
            for word, start, end in words
        ],
        "segments": [],
    }


def test_supplied_caption_transcript_never_extracts_or_retranscribes(tmp_path, monkeypatch):
    harness = SubtitleHarness()
    harness.log = lambda *_args: None
    harness.transcribe_audio_with_timestamps = lambda *_args, **_kwargs: pytest.fail("retranscribed")
    monkeypatch.setattr(clipper_export.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("extracted"))
    ass_file = harness._create_caption_ass(
        "section.mp4",
        tmp_path,
        timed_words(("halo", 0.0, 0.5)),
    )
    assert ass_file == tmp_path / "captions.ass"
    assert ass_file.exists()


def test_caption_without_supplied_transcript_extracts_mp3_and_requires_words(tmp_path, monkeypatch):
    harness = SubtitleHarness()
    harness.ffmpeg_path = "ffmpeg"
    harness.log = lambda *_args: None
    calls = []

    def run(command, **_kwargs):
        Path(command[-1]).write_bytes(b"x" * 1000)
        calls.append(command)
        return SimpleNamespace(returncode=0)

    def transcribe(path, require_words=False):
        calls.append((Path(path).name, require_words))
        return timed_words(("halo", 0.0, 0.5))

    monkeypatch.setattr(clipper_export.subprocess, "run", run)
    harness.transcribe_audio_with_timestamps = transcribe
    harness._create_caption_ass("section.mp4", tmp_path)
    assert calls[0][-1].endswith("caption_audio.mp3")
    assert calls[0][calls[0].index("-ar") + 1] == "16000"
    assert calls[0][calls[0].index("-ac") + 1] == "1"
    assert calls[1] == ("caption_audio.mp3", True)


def test_supplied_segment_transcript_creates_ass_without_extraction(tmp_path, monkeypatch):
    harness = SubtitleHarness()
    harness.log = lambda *_args: None
    monkeypatch.setattr(clipper_export.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("extracted"))
    ass_file = harness._create_caption_ass(
        "section.mp4",
        tmp_path,
        {"duration": 1.0, "words": [], "segments": [{"text": "halo", "start": 0.0, "end": 1.0}]},
    )
    assert "Dialogue:" in ass_file.read_text(encoding="utf-8")


def test_supplied_empty_transcript_is_fatal_without_extraction(tmp_path, monkeypatch):
    harness = SubtitleHarness()
    monkeypatch.setattr(clipper_export.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("extracted"))
    with pytest.raises(ValueError, match="timestamped content"):
        harness._create_caption_ass(
            "section.mp4",
            tmp_path,
            {"duration": 1.0, "words": [], "segments": []},
        )


def test_rebased_transcript_creates_ass_near_clip_start(tmp_path):
    source = timed_words(("jam", 3601.0, 3601.5), duration=3610.0)
    transcript = slice_timed_transcript(source, 3600.0, 3605.0)
    output = tmp_path / "rebased.ass"
    SubtitleHarness().create_ass_subtitle_capcut(transcript, str(output))
    dialogue = next(line for line in output.read_text(encoding="utf-8").splitlines() if line.startswith("Dialogue:"))
    assert ",0:00:01.00," in dialogue
    assert "1:00:" not in dialogue


def test_ass_escapes_backslashes_braces_and_newlines(tmp_path):
    output = tmp_path / "escaped.ass"
    transcript = timed_words(("slash\\{teks}\nbar", 0.0, 0.5))
    SubtitleHarness().create_ass_subtitle_capcut(transcript, str(output))
    dialogue = next(line for line in output.read_text(encoding="utf-8").splitlines() if line.startswith("Dialogue:"))
    assert r"slash\\\{teks\} bar" in dialogue
    assert "\n" not in dialogue


class ProcessClipHarness(SubtitleHarness):
    def __init__(self, root):
        self.output_dir = root
        self.screen_size = "9:16"
        self.output_resolution = "720:1280"
        self.ffmpeg_path = "ffmpeg"
        self.watermark_settings = {"enabled": False}
        self.credit_watermark_settings = {"enabled": False}
        self.hook_style_settings = {}
        self.channel_name = ""
        self.video_info = {}
        self.video_quality = "1080"
        self.landscape_blur = True
        self.blur_background_settings = {"enabled": True, "strength": 30}
        self.draft_only = False
        self.events = []

    def is_cancelled(self):
        return False

    def parse_timestamp(self, timestamp):
        hours, minutes, seconds = timestamp.replace(",", ".").split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    def log(self, *_args):
        pass

    def set_progress(self, *_args):
        pass

    def _create_caption_ass(self, _input_path, clip_dir, transcript=None):
        self.events.append(("caption", transcript))
        path = clip_dir / "captions.ass"
        path.write_text("ass", encoding="utf-8")
        return path

    def convert_to_portrait_with_progress(self, _source, output, _progress):
        self.events.append(("portrait", None))
        Path(output).write_bytes(b"x" * 1000)

    def _probe_render_input(self, _path):
        return 720, 1280, 3.0

    def _has_audio_stream(self, _path):
        return True

    def get_video_encoder_args(self):
        return ["-c:v", "libx264"]

    def log_ffmpeg_command(self, *_args):
        pass

    def run_ffmpeg_with_progress(self, command, _duration, _progress):
        Path(command[-1]).write_bytes(b"x" * 1000)

    def _run_probe_subprocess(self, command, **_kwargs):
        Path(command[-1]).write_bytes(b"thumbnail")
        return SimpleNamespace(returncode=0)


def test_draft_writes_required_artifacts_without_ass_or_overlays(tmp_path):
    source = tmp_path / "section.mp4"
    source.write_bytes(b"x" * 1000)
    harness = ProcessClipHarness(tmp_path / "out")
    harness.draft_only = True
    transcript = timed_words(("halo", 0.0, 0.5))
    harness.process_clip(
        str(source),
        {
            "start_time": "00:00:00,000",
            "end_time": "00:00:03,000",
            "duration_seconds": 3.0,
            "title": "clip",
        },
        1,
        add_captions=True,
        add_hook=True,
        pre_cut=True,
        caption_transcript=transcript,
    )
    clip_dir = next(path for path in harness.output_dir.iterdir() if path.is_dir())
    assert {path.name for path in clip_dir.iterdir()} == {"source.mp4", "draft.mp4", "transcript.json", "data.json", "thumbnail.jpg"}
    metadata = json.loads((clip_dir / "data.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "needs_edit"
    assert metadata["generation_id"] == harness.output_dir.name
    assert metadata["created_at"]
    assert metadata["draft_settings"] == {"landscape_blur": True, "blur_background": {"enabled": True, "strength": 30}, "video_quality": "1080", "screen_size": "9:16"}
    assert harness.events == [("portrait", None)]


def test_draft_without_caption_overlay_retains_usable_transcript(tmp_path):
    source = tmp_path / "section.mp4"
    source.write_bytes(b"x" * 1000)
    harness = ProcessClipHarness(tmp_path / "out")
    harness.draft_only = True
    transcript = timed_words(("halo", 0.0, 0.5))
    harness.process_clip(str(source), {"start_time": "00:00:00,000", "end_time": "00:00:03,000", "duration_seconds": 3.0, "title": "clip"}, 1, add_captions=False, add_hook=False, pre_cut=True, caption_transcript=transcript)
    clip_dir = next(path for path in harness.output_dir.iterdir() if path.is_dir())
    saved = json.loads((clip_dir / "transcript.json").read_text(encoding="utf-8"))
    metadata = json.loads((clip_dir / "data.json").read_text(encoding="utf-8"))
    assert saved["words"][0]["word"] == "halo"
    assert metadata["transcript_path"] == "transcript.json"


def test_draft_without_captions_still_writes_transcript_artifact(tmp_path):
    source = tmp_path / "section.mp4"
    source.write_bytes(b"x" * 1000)
    harness = ProcessClipHarness(tmp_path / "out")
    harness.draft_only = True
    harness.process_clip(
        str(source),
        {
            "start_time": "00:00:00,000",
            "end_time": "00:00:03,000",
            "duration_seconds": 3.0,
            "title": "clip",
        },
        1,
        add_captions=False,
        add_hook=False,
        pre_cut=True,
    )
    clip_dir = next(path for path in harness.output_dir.iterdir() if path.is_dir())
    transcript = json.loads((clip_dir / "transcript.json").read_text(encoding="utf-8"))
    metadata = json.loads((clip_dir / "data.json").read_text(encoding="utf-8"))
    assert transcript == {"duration": 3.0, "words": [], "segments": []}
    assert metadata["transcript_path"] == ""


def test_process_clip_prepares_portrait_before_captions(tmp_path):
    source = tmp_path / "section.mp4"
    source.write_bytes(b"x" * 1000)
    harness = ProcessClipHarness(tmp_path / "out")
    transcript = timed_words(("halo", 0.0, 0.5))
    harness.process_clip(
        str(source),
        {
            "start_time": "00:00:00,000",
            "end_time": "00:00:03,000",
            "duration_seconds": 3.0,
            "title": "clip",
        },
        1,
        add_captions=True,
        add_hook=False,
        pre_cut=True,
        caption_transcript=transcript,
    )
    assert harness.events[:2] == [("portrait", None), ("caption", transcript)]


def test_legacy_clip_defaults_to_normal_gaming_layout(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    assert manager._render_settings({}, {})["video_layout"] == {"mode": "normal"}
    assert manager._config().config["video_layout"] == {"mode": "normal"}


def test_global_defaults_persist_gaming_mode_without_facecam_roi(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    manager.save_settings({"video_layout": {"mode": "gaming", "facecam_x": 0.1, "facecam_y": 0.1, "facecam_width": 0.2, "facecam_height": 0.2, "facecam_confidence": 0.9}})
    assert manager._config().config["video_layout"] == {"mode": "gaming"}


def test_saved_gaming_default_allows_loading_legacy_clip_without_detection(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    manager.save_settings({"video_layout": {"mode": "gaming"}})
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    (clip_dir / "draft.mp4").write_bytes(b"draft")
    (clip_dir / "source.mp4").write_bytes(b"source")
    (clip_dir / "data.json").write_text(json.dumps({"clip_id": "legacy-gaming", "status": "needs_edit"}), encoding="utf-8")
    result = manager.get_clip("legacy-gaming")
    assert result["status"] == "ok"
    assert result["defaults"]["video_layout"] == {"mode": "gaming"}


def test_v3_all_modes_force_nine_by_sixteen(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    metadata = {"draft_settings": {"screen_size": "16:9"}, "gaming_detection": {"facecam": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2}, "confidence": 0.9}}
    gaming = manager._render_settings({"settings": {"video_layout": {"mode": "gaming"}}}, metadata)
    normal = manager._render_settings({"settings": {"video_layout": {"mode": "normal"}}}, metadata)
    assert gaming["screen_size"] == "9:16"
    assert normal["screen_size"] == "9:16"


def test_gaming_render_without_detection_is_rejected(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    (clip_dir / "source.mp4").write_bytes(b"source")
    (clip_dir / "data.json").write_text(json.dumps({"clip_id": "gaming", "status": "needs_edit", "source_geometry": {"width": 1920, "height": 1080, "is_landscape": True}}), encoding="utf-8")
    result = manager.render_clip({"clip_id": "gaming", "settings": {"video_layout": {"mode": "gaming"}, "subtitle": {"enabled": False}}}, preview=False)
    assert result == {"status": "error", "message": mod.FACE_NOT_FOUND_MESSAGE}


def test_detect_gaming_facecam_persists_and_reuses_source_identity(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    source = clip_dir / "source.mp4"
    source.write_bytes(b"source")
    meta_path = clip_dir / "data.json"
    meta_path.write_text(json.dumps({"clip_id": "detect", "status": "needs_edit"}), encoding="utf-8")
    calls = []
    monkeypatch.setattr(mod, "detect_facecam", lambda _path: calls.append(1) or {"x": 0.02, "y": 0.03, "width": 0.3, "height": 0.4, "confidence": 0.91})
    first = manager.detect_gaming_facecam({"clip_id": "detect"})
    second = manager.detect_gaming_facecam({"clip_id": "detect"})
    saved = json.loads(meta_path.read_text(encoding="utf-8"))["gaming_detection"]
    assert first["cached"] is False and second["cached"] is True
    assert calls == [1]
    assert saved["facecam"] == first["facecam"]
    source.write_bytes(b"changed-source")
    manager.detect_gaming_facecam({"clip_id": "detect"})
    assert calls == [1, 1]


def test_detect_gaming_facecam_rejects_invalid_payload_and_portrait(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    assert manager.detect_gaming_facecam(None)["status"] == "error"
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    (clip_dir / "source.mp4").write_bytes(b"source")
    (clip_dir / "data.json").write_text(json.dumps({"clip_id": "portrait", "status": "needs_edit"}), encoding="utf-8")
    monkeypatch.setattr(mod, "detect_facecam", lambda _path: (_ for _ in ()).throw(mod.GamingLayoutError("Mode gaming hanya mendukung source landscape.")))
    result = manager.detect_gaming_facecam({"clip_id": "portrait"})
    assert result == {"status": "error", "message": "Mode gaming hanya mendukung source landscape."}


def test_clip_artifact_rejects_path_traversal_and_unknown_names(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    (clip_dir / "master.mp4").write_bytes(b"final")
    (clip_dir / "data.json").write_text(json.dumps({"clip_id": "art"}), encoding="utf-8")
    assert manager.clip_artifact("art", "final").name == "master.mp4"
    assert manager.clip_artifact("art", "../master.mp4") is None
    assert manager.clip_artifact("art", "preview", "../../etc/passwd") is None
    assert manager.clip_artifact("missing", "final") is None


def test_prepare_gaming_layout_sets_needs_facecam_on_low_confidence(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    (clip_dir / "source.mp4").write_bytes(b"source")
    meta_path = clip_dir / "data.json"
    meta_path.write_text(json.dumps({"clip_id": "nf", "status": "needs_edit", "title": "NF"}), encoding="utf-8")
    monkeypatch.setattr(
        mod,
        "detect_facecam",
        lambda _path, minimum_confidence=0.62: (_ for _ in ()).throw(mod.GamingLayoutError(mod.FACE_NOT_FOUND_MESSAGE)),
    )
    result = manager.prepare_gaming_layout("nf")
    assert result["status"] == "needs_facecam"
    saved = json.loads(meta_path.read_text(encoding="utf-8"))
    assert saved["status"] == "needs_facecam"
    listed = manager.list_clips()
    assert any(item["clip_id"] == "nf" and item["status"] == "needs_facecam" for item in listed["clips"])


def test_submit_facecam_roi_rejects_overlap_and_accepts_valid(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    monkeypatch.setattr(manager, "render_clip", lambda *_args, **_kwargs: {"status": "queued", "attempt_id": "test"})

    clip_dir = tmp_path / "output" / "run" / "clip"
    clip_dir.mkdir(parents=True)
    (clip_dir / "source.mp4").write_bytes(b"source")
    (clip_dir / "transcript.json").write_text(json.dumps({"duration": 1, "words": [{"word": "tes", "start": 0, "end": 1}], "segments": []}), encoding="utf-8")
    meta_path = clip_dir / "data.json"
    meta_path.write_text(json.dumps({
        "clip_id": "roi",
        "status": "needs_facecam",
        "transcript_path": "transcript.json",
        "source_geometry": {"width": 1920, "height": 1080, "is_landscape": True},
    }), encoding="utf-8")
    bad = manager.submit_facecam_roi({"clip_id": "roi", "x": 0.4, "y": 0.1, "width": 0.3, "height": 0.3})
    assert bad["status"] == "error"
    ok = manager.submit_facecam_roi({"clip_id": "roi", "x": 0.02, "y": 0.03, "width": 0.18, "height": 0.2})
    assert ok["status"] == "ok"
    saved = json.loads(meta_path.read_text(encoding="utf-8"))
    assert saved["status"] in {"needs_edit", "render_queued", "rendering", "ready_to_schedule", "render_error"}
    assert saved["gaming_detection"]["manual"] is True
    assert saved["gaming_detection"]["facecam"]["x"] == pytest.approx(0.02)
    assert ok.get("render", {}).get("status") in {"queued", "error", "cached"}


def test_extract_clip_frame_requires_owned_clip(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path)
    raw, error = manager.extract_clip_frame("missing")
    assert raw is None and error


if __name__ == "__main__":
    tests = [value for name, value in globals().items() if name.startswith("test_")]
    import tempfile
    for test in tests:
        with tempfile.TemporaryDirectory() as directory:
            test(Path(directory))
    print(f"{len(tests)} tests passed")
