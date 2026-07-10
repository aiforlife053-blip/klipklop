import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "job_manager.py"
spec = importlib.util.spec_from_file_location("web_klip_job_manager", MODULE)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
from clipper_core import AutoClipperCore
from clipper_download import DownloadMixin
from clipper_export import ExportMixin
from clipper_portrait import PortraitMixin


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
    assert result["status"] == "started"
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
    assert result["status"] == "started"


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
    assert cfg["ai_providers"]["caption_maker"]["model"] == "whisper-1"


def test_output_listing_is_limited_to_known_file_types(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    (output / "clip.mp4").write_bytes(b"x")
    (output / "secret.key").write_text("nope")
    manager = mod.WebJobManager(app_dir=tmp_path)
    names = [item["name"] for item in manager.list_outputs()["files"]]
    assert names == ["clip.mp4"]


def test_output_listing_groups_run_folders(tmp_path):
    run = tmp_path / "output" / "20260706-video"
    clip = run / "20260706-120000-01"
    clip.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"title": "Judul", "caption": "2 klip", "timestamp": "2026-07-06T12:00:00"}))
    (clip / "master.mp4").write_bytes(b"x")
    manager = mod.WebJobManager(app_dir=tmp_path)
    result = manager.list_outputs()
    groups = result["groups"]
    assert groups[0]["title"] == "Judul"
    assert groups[0]["thumbnail"].endswith("master.mp4")
    assert result["outputs"] == result["files"]


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


def test_enable_captions_alias_can_disable_captions(tmp_path):
    manager = InstantJobManager(app_dir=tmp_path)
    result = manager.start({"url": "https://www.youtube.com/watch?v=abc", "enable_captions": False})
    thread = manager.thread
    assert result == {"status": "started"}
    if thread:
        thread.join(1)
    assert manager.captured["add_captions"] is False


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
    assert result == {"status": "started"}
    assert manager.captured["url"] == "https://www.youtube.com/watch?v=abc"


def test_sixteen_by_nine_screen_size_is_ignored(tmp_path):
    manager = InstantJobManager(app_dir=tmp_path)
    result = manager.start({"url": "https://www.youtube.com/watch?v=abc", "add_captions": False, "screen_size": "16:9"})
    thread = manager.thread
    if thread:
        thread.join(1)
    assert result == {"status": "started"}


class LegacySevenArgJobManager(mod.WebJobManager):
    def _run(self, url, num_clips, add_captions, add_hook, subtitle_language, instruction, landscape_blur):
        self.captured = {"landscape_blur": landscape_blur}
        self.thread = None


def test_legacy_seven_arg_run_gets_landscape_blur_enabled(tmp_path):
    manager = LegacySevenArgJobManager(app_dir=tmp_path)
    result = manager.start({"url": "https://www.youtube.com/watch?v=abc", "add_captions": False, "landscape_blur": True})
    thread = manager.thread
    if thread:
        thread.join(1)
    assert result == {"status": "started"}
    assert manager.captured["landscape_blur"] is True


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


def test_save_output_accepts_empty_clips_payload(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    run = tmp_path / "output" / "run"
    run.mkdir(parents=True)
    result = manager.save_output({"path": str(run), "clips": None})
    assert result["status"] == "saved"


def test_save_output_ignores_clips_outside_session(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    run = tmp_path / "output" / "run"
    run.mkdir(parents=True)
    outside = tmp_path / "output" / "other" / "master.mp4"
    outside.parent.mkdir()
    outside.write_bytes(b"x")
    result = manager.save_output({"path": str(run), "clips": [str(outside)]})
    meta = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert result["status"] == "saved"
    assert meta["saved_clips"] == []


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
    words = [SimpleNamespace(word=f"w{i}", start=i * 0.2, end=i * 0.2 + 0.1) for i in range(7)]
    output = tmp_path / "sub.ass"
    count = SubtitleHarness().create_ass_subtitle_capcut(SimpleNamespace(words=words), str(output))
    text = output.read_text(encoding="utf-8")
    assert count == 7
    assert "PlayResX: 720" in text
    assert "Fontname, Fontsize" in text
    assert "Style: Default,Poppins,40,&H0022AA11,&H0022AA11,&H00214365" in text
    assert ",0,0,0,0,100,100,0,0,1,4,0,5," in text
    assert "{\\pos(288,1024)}" in text
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


def test_blur_filter_matches_preview_geometry():
    harness = object.__new__(PortraitMixin)
    harness.blur_background_settings = {"zoom": 1.08, "strength": 3, "scale": 1.5}
    filter_graph = harness._preview_blur_filter(720, 1280)
    assert "scale=1080:608:force_original_aspect_ratio=increase,crop=1080:608[fg]" in filter_graph
    assert "gblur=sigma=6.353:steps=2" in filter_graph
    assert "colorchannelmixer=rr=0.6:gg=0.6:bb=0.6" in filter_graph
    assert "overlay=(W-w)/2:(H-h)/2" in filter_graph
    harness.blur_background_settings["strength"] = 0
    assert "gblur=" not in harness._preview_blur_filter(720, 1280)


def test_high_resolution_caps_parallel_cpu_workers():
    assert mod.WebJobManager._parallel_workers_for_quality(3, "720") == 3
    assert mod.WebJobManager._parallel_workers_for_quality(3, "1080") == 2
    assert mod.WebJobManager._parallel_workers_for_quality(3, "1440") == 1
    assert mod.WebJobManager._parallel_workers_for_quality(3, "2160") == 1


def test_section_format_has_hard_cap_and_fast_codec_sort():
    harness = object.__new__(DownloadMixin)
    harness.video_quality = "1080"
    selector = harness._format_selector()
    assert selector.count("height<=1080") == 4
    assert selector.endswith("best[height<=1080]")
    assert all("height<=1080" in fallback for fallback in selector.split("/"))
    assert harness._format_sort() == ["res", "vcodec:h264", "fps:30", "br"]


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
    assert "[1:a]asetpts=PTS-STARTPTS[aout]" in filter_graph
    assert filter_graph.index("overlay=0:0:enable") < filter_graph.index("ass=") < filter_graph.rindex("overlay=0:0")


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
    result = core._find_highlights_single("[00:01:00,000 - 00:01:04,000] halo", {"title": "video"}, 1, allow_chunking=False)
    assert result[0]["duration_seconds"] >= 10
    assert result[0]["hook_text"] == "Short"


class NoSubtitleCore(AutoClipperCore):
    def __init__(self):
        self.output_dir = Path("out")
        self.temp_dir = self.output_dir / "_temp"
        self.cache_dir = self.output_dir / "cache"
        self.parallel_workers = 1
        self.use_download_sections = True

    def set_progress(self, stage, progress):
        pass

    def is_cancelled(self):
        return False

    def download_subtitle_only(self, url):
        return None, {"title": "video"}

    def download_audio_only(self, url):
        self.downloaded_audio = getattr(self, "downloaded_audio", 0) + 1
        return "source_audio.mp3"

    def transcribe_audio_local(self, audio_path):
        self.transcribed = audio_path
        return "[00:00:00,000 - 00:00:03,000] halo indonesia"

    def download_video_section(self, url, start_time, end_time, output_path):
        self.downloaded_sections = getattr(self, "downloaded_sections", 0) + 1
        return "section.mp4"

    def find_highlights(self, transcript, video_info, num_clips):
        self.highlight_transcript = transcript
        return [{"start_time": "00:00:00,000", "end_time": "00:00:03,000"}]

    def process_clip(self, source_path, highlight, index, total_clips, add_captions=True, add_hook=True, pre_cut=False):
        self.processed = source_path

    def cleanup(self):
        self.cleaned = True

    def log(self, message):
        pass


def test_process_falls_back_to_audio_only_whisper_then_section_download(tmp_path):
    core = NoSubtitleCore()
    core.process("https://www.youtube.com/watch?v=abc", num_clips=1)
    assert core.transcribed == "source_audio.mp3"
    assert core.highlight_transcript == "[00:00:00,000 - 00:00:03,000] halo indonesia"
    assert core.downloaded_audio == 1
    assert core.downloaded_sections == 1
    assert core.processed == "section.mp4"


if __name__ == "__main__":
    tests = [value for name, value in globals().items() if name.startswith("test_")]
    import tempfile
    for test in tests:
        with tempfile.TemporaryDirectory() as directory:
            test(Path(directory))
    print(f"{len(tests)} tests passed")
