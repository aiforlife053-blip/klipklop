import os
from pathlib import Path

from openai import OpenAI

from clipper_ai import AiMixin
from clipper_download import DownloadMixin
from clipper_export import ExportMixin
from clipper_ffmpeg import FfmpegMixin
from clipper_portrait import PortraitMixin
from clipper_shared import SubtitleNotFoundError, _hex_to_rgb
from utils.helpers import get_deno_path, get_ffmpeg_path
from utils.logger import debug_log

_deno_path = get_deno_path()
_ffmpeg_path = get_ffmpeg_path()

if _deno_path and Path(_deno_path).exists():
    _deno_dir = str(Path(_deno_path).parent)
    if "PATH" in os.environ:
        if _deno_dir not in os.environ["PATH"]:
            os.environ["PATH"] = f"{_deno_dir}{os.pathsep}{os.environ['PATH']}"
    else:
        os.environ["PATH"] = _deno_dir
    debug_log(f"Deno added to PATH: {_deno_dir}")

if _ffmpeg_path and Path(_ffmpeg_path).exists():
    _ffmpeg_dir = str(Path(_ffmpeg_path).parent)
    if "PATH" in os.environ:
        if _ffmpeg_dir not in os.environ["PATH"]:
            os.environ["PATH"] = f"{_ffmpeg_dir}{os.pathsep}{os.environ['PATH']}"
    else:
        os.environ["PATH"] = _ffmpeg_dir
    debug_log(f"FFmpeg added to PATH: {_ffmpeg_dir}")


class AutoClipperCore(FfmpegMixin, DownloadMixin, AiMixin, PortraitMixin, ExportMixin):
    def __init__(
        self,
        client: OpenAI,
        ffmpeg_path: str = "ffmpeg",
        ytdlp_path: str = "yt-dlp",
        output_dir: str = "output",
        model: str = "gpt-4.1",
        tts_model: str = "tts-1",
        temperature: float = 1.0,
        system_prompt: str = None,
        watermark_settings: dict = None,
        credit_watermark_settings: dict = None,
        hook_style_settings: dict = None,
        face_tracking_mode: str = "center",
        mediapipe_settings: dict = None,
        ai_providers: dict = None,
        subtitle_language: str = "id",
        video_quality: str = "720",
        landscape_blur: bool = False,
        screen_size: str = "9:16",
        subtitle_style: dict = None,
        subtitle_engine: str = "local",
        local_whisper: dict = None,
        log_callback=None,
        progress_callback=None,
        token_callback=None,
        cancel_check=None,
    ):
        self.ai_providers = ai_providers or {}
        if self.ai_providers:
            hf_config = self.ai_providers.get("highlight_finder", {})
            self.highlight_client = OpenAI(
                api_key=hf_config.get("api_key", ""),
                base_url=hf_config.get("base_url", "https://api.openai.com/v1"),
            )
            self.model = hf_config.get("model", model)
            cm_config = self.ai_providers.get("caption_maker", {})
            self.caption_client = OpenAI(
                api_key=cm_config.get("api_key"),
                base_url=cm_config.get("base_url", "https://api.openai.com/v1"),
                timeout=600.0,
            ) if cm_config.get("api_key") else None
            self.whisper_model = cm_config.get("model", "whisper-1")
            self.tts_client = None
            self.tts_model = tts_model
        else:
            self.highlight_client = client
            self.caption_client = client
            self.tts_client = None
            self.model = model
            self.tts_model = tts_model
            self.whisper_model = "whisper-1"

        self.client = client
        self.ffmpeg_path = ffmpeg_path
        self.ytdlp_path = ytdlp_path
        self.output_dir = Path(output_dir)
        self.temperature = temperature
        self.system_prompt = system_prompt or self.get_default_prompt()
        self.watermark_settings = watermark_settings or {"enabled": False}
        self.credit_watermark_settings = credit_watermark_settings or {"enabled": False}
        self.hook_style_settings = hook_style_settings or {}
        self.video_info = {}
        self.channel_name = ""
        self.face_tracking_mode = face_tracking_mode
        self.mediapipe_settings = mediapipe_settings or {
            "lip_activity_threshold": 0.15,
            "switch_threshold": 0.3,
            "min_shot_duration": 90,
            "center_weight": 0.3,
        }
        self.subtitle_language = subtitle_language or "id"
        self.video_quality = str(video_quality or "720")
        self.landscape_blur = bool(landscape_blur)
        self.screen_size = "16:9" if str(screen_size) == "16:9" else "9:16"
        self.subtitle_style = subtitle_style or {"font": "Plus Jakarta Sans", "size": 65, "bottom_margin": 400}
        self.subtitle_engine = subtitle_engine or "local"
        self.local_whisper = local_whisper or {"enabled": True, "model": "medium", "device": "cpu", "compute_type": "int8"}
        self._local_whisper_model = None
        resolutions = {"16:9": {"480": "854:480", "720": "1280:720", "1080": "1920:1080"}, "9:16": {"480": "540:960", "720": "720:1280", "1080": "1080:1920"}}
        self.output_resolution = resolutions[self.screen_size].get(self.video_quality, resolutions[self.screen_size]["720"])
        self.log = log_callback or print
        self.set_progress = progress_callback or (lambda s, p: None)
        self.report_tokens = token_callback or (lambda gi, go, w, t: None)
        self.is_cancelled = cancel_check or (lambda: False)
        self.gpu_enabled = False
        self.gpu_encoder_args = []
        self.mp_face_mesh = None
        self.mp_drawing = None
        self.temp_dir = self.output_dir / "_temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def process(self, url: str, num_clips: int = 5, add_captions: bool = True, add_hook: bool = True):
        try:
            self.set_progress("Downloading subtitle...", 0.1)
            srt_path, video_info = self.download_subtitle_only(url)
            self.video_info = video_info or {}
            self.channel_name = video_info.get("channel", "") if video_info else ""
            if self.is_cancelled():
                return
            source_path = ""
            if not srt_path:
                self.set_progress("Subtitle tidak ditemukan, download video untuk transkripsi lokal...", 0.18)
                source_path = self.download_video_only(url)
                transcript = self.transcribe_full_video_local(source_path)
            else:
                transcript = self.parse_srt(srt_path)
            self.set_progress("Finding highlights...", 0.3)
            highlights = self.find_highlights(transcript, video_info, num_clips)
            if self.is_cancelled():
                return
            if not highlights:
                raise Exception("No valid highlights found!")
            if not source_path:
                self.set_progress("Downloading source video/audio once...", 0.32)
                source_path = self.download_video_only(url)
            total_clips = len(highlights)
            for i, highlight in enumerate(highlights, 1):
                if self.is_cancelled():
                    return
                self.process_clip(source_path, highlight, i, total_clips, add_captions=add_captions, add_hook=add_hook, pre_cut=False)
            self.set_progress("Complete!", 1.0)
            self.log(f"\n✅ Created {total_clips} clips in: {self.output_dir}")
        finally:
            self.cleanup()
