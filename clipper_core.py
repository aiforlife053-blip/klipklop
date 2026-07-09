import hashlib
import json
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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
            tts_config = self.ai_providers.get("hook_maker", {})
            self.tts_client = None
            self.tts_api_key = tts_config.get("api_key") or hf_config.get("api_key") or ""
            self.tts_model = tts_config.get("model", "gemini-3.1-flash-tts-preview")
            self.tts_voice = tts_config.get("voice", "Fenrir")
        else:
            self.highlight_client = client
            self.caption_client = client
            self.tts_client = None
            self.tts_api_key = ""
            self.model = model
            self.tts_model = "gemini-3.1-flash-tts-preview"
            self.tts_voice = "Fenrir"
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
        self.blur_background_settings = self.hook_style_settings.get("blur_background", {}) if isinstance(self.hook_style_settings, dict) else {}
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
        self.optimize_mode = str((self.ai_providers or {}).get("optimize_mode") or os.environ.get("KLIPKLOP_OPTIMIZE_MODE") or "local").lower()
        self.use_download_sections = self.optimize_mode in {"local", "hosting_2cpu", "fast_cpu"}
        self.subtitle_style = subtitle_style or {"font": "Plus Jakarta Sans", "size": 58, "bottom_margin": 360}
        self.subtitle_engine = subtitle_engine or "local"
        self.local_whisper = local_whisper or {"enabled": True, "model": "small", "device": "cpu", "compute_type": "int8"}
        self._local_whisper_model = None
        resolutions = {"16:9": {"480": "854:480", "720": "1280:720", "1080": "1920:1080"}, "9:16": {"480": "540:960", "720": "720:1280", "1080": "1080:1920"}}
        self.output_resolution = resolutions[self.screen_size].get(self.video_quality, resolutions[self.screen_size]["720"])
        self._progress_lock = threading.Lock()
        
        self._raw_log = log_callback or print
        self._raw_set_progress = progress_callback or (lambda s, p: None)
        
        def _safe_log(*args, **kwargs):
            with self._progress_lock:
                self._raw_log(*args, **kwargs)
                
        def _safe_set_progress(*args, **kwargs):
            with self._progress_lock:
                self._raw_set_progress(*args, **kwargs)
                
        self.log = _safe_log
        self.set_progress = _safe_set_progress
        self.report_tokens = token_callback or (lambda gi, go, w, t: None)
        self.is_cancelled = cancel_check or (lambda: False)
        self.gpu_enabled = False
        self.gpu_encoder_args = []
        self.mp_face_mesh = None
        self.mp_drawing = None
        self.temp_dir = self.output_dir / "_temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = Path(os.environ.get("KLIPKLOP_CACHE_DIR") or self.output_dir.parent / "cache")
        # Parallel clip processing: default 2 workers (safe for 2-CPU VPS).
        # Override via config 'parallel_workers' or env KLIPKLOP_PARALLEL_WORKERS.
        # Set to 1 to disable parallelism entirely.
        _env_workers = os.environ.get("KLIPKLOP_PARALLEL_WORKERS")
        _cfg_workers = (self.ai_providers or {}).get("parallel_workers")
        try:
            self.parallel_workers = int(_cfg_workers or _env_workers or 3)
        except (TypeError, ValueError):
            self.parallel_workers = 3
        self.parallel_workers = max(1, self.parallel_workers)
        self.parallel_workers = max(1, self.parallel_workers)

    def _video_cache_dir(self, url: str) -> Path:
        parsed = urlparse(url)
        video_id = parse_qs(parsed.query).get("v", [""])[0] if parsed.query else ""
        key = video_id or hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        
        # User requested to disable caching. We now store "cached" files
        # in the temp_dir so they are automatically wiped at the end of each run.
        import uuid
        unique_key = f"{key}_{uuid.uuid4().hex[:8]}"
        path = self.temp_dir / unique_key
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _cache_key(self, value: str) -> str:
        return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]

    def _cleanup_stale_cache(self, ttl_days: int = 7):
        """Delete cache entries older than ttl_days to prevent unbounded disk growth.
        
        Each video gets its own subdirectory under cache_dir (keyed by video ID).
        Runs at the start of every process() call; best-effort, never raises.
        """
        import time
        try:
            if not self.cache_dir.exists():
                return
            cutoff = time.time() - ttl_days * 86400
            removed = 0
            for entry in self.cache_dir.iterdir():
                if entry.is_dir() and entry.stat().st_mtime < cutoff:
                    import shutil
                    shutil.rmtree(entry, ignore_errors=True)
                    removed += 1
            if removed:
                debug_log(f"Cache cleanup: removed {removed} stale cache folder(s) older than {ttl_days} days")
        except Exception as exc:
            debug_log(f"Cache cleanup error (ignored): {exc}")

    def process(self, url: str, num_clips: int = 5, add_captions: bool = True, add_hook: bool = True):
        try:
            self._cleanup_stale_cache()
            cache_dir = self._video_cache_dir(url)
            cached_srt = cache_dir / "transcript.srt"
            cached_info = cache_dir / "video_info.json"
            self.set_progress("Downloading subtitle...", 0.1)
            use_sections = getattr(self, "use_download_sections", True)
            if use_sections and cached_srt.exists():
                srt_path = str(cached_srt)
                video_info = json.loads(cached_info.read_text(encoding="utf-8")) if cached_info.exists() else {"title": "video"}
                self.log("  ✓ Using cached SRT")
            else:
                srt_path, video_info = self.download_subtitle_only(url)
                if use_sections and srt_path:
                    shutil.copyfile(srt_path, cached_srt)
                    cached_info.write_text(json.dumps(video_info or {}, ensure_ascii=False, indent=2), encoding="utf-8")
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
            highlights_cache = cache_dir / f"highlights.{self._cache_key(str(num_clips) + getattr(self, 'system_prompt', '') + str(transcript))}.json"
            if use_sections and highlights_cache.exists():
                highlights = json.loads(highlights_cache.read_text(encoding="utf-8"))
                self.log("  ✓ Using cached highlights")
            else:
                highlights = self.find_highlights(transcript, video_info, num_clips)
                if use_sections:
                    highlights_cache.write_text(json.dumps(highlights, ensure_ascii=False, indent=2), encoding="utf-8")
            if self.is_cancelled():
                return
            if not highlights:
                raise Exception("No valid highlights found!")
            total_clips = len(highlights)
            if use_sections and srt_path:
                self._process_clips_with_sections(url, highlights, total_clips, add_captions, add_hook)
            else:
                if not source_path:
                    self.set_progress("Downloading source video/audio once...", 0.32)
                    source_path = self.download_video_only(url)
                self._process_clips_parallel(source_path, highlights, total_clips, add_captions, add_hook, pre_cut=False)
            self.set_progress("Complete!", 1.0)
            self.log(f"\n\u2705 Created {total_clips} clips in: {self.output_dir}")
        finally:
            self.cleanup()

    def _process_clips_with_sections(self, url, highlights, total_clips, add_captions, add_hook):
        """Download each section sequentially (yt-dlp is single-threaded), then
        process all clips in parallel using ThreadPoolExecutor.

        Strategy:
          1. Download all sections sequentially (can't parallelise yt-dlp safely).
          2. Kick off process_clip for all downloaded sections in parallel.
        """
        # Phase 1: download sections sequentially
        sections = []  # list of (clip_source, highlight, index)
        for i, highlight in enumerate(highlights, 1):
            if self.is_cancelled():
                return
            self.set_progress(
                f"Clip {i}/{total_clips}: Downloading section...",
                0.32 + (0.08 * (i - 1) / total_clips),
            )
            section_path = str(self.temp_dir / f"section_{i:03d}.mp4")
            clip_source = self.download_video_section(
                url, highlight["start_time"], highlight["end_time"], section_path
            )
            sections.append((clip_source, highlight, i))

        # Phase 2: process (encode + caption burn) in parallel
        self._process_clips_parallel(
            source_path=None,
            highlights=highlights,
            total_clips=total_clips,
            add_captions=add_captions,
            add_hook=add_hook,
            pre_cut=True,
            sections=sections,
        )

    def _process_clips_parallel(
        self,
        source_path,
        highlights,
        total_clips,
        add_captions,
        add_hook,
        pre_cut=False,
        sections=None,
    ):
        """Run process_clip in parallel using ThreadPoolExecutor.

        Falls back to sequential (max_workers=1) if parallel_workers == 1.
        Thread-safe: each clip writes to its own output subdirectory.
        """
        workers = self.parallel_workers
        mode = f"parallel ({workers} workers)" if workers > 1 else "sequential"
        self.log(f"  Processing {total_clips} clip(s) [{mode}]")

        def _do_clip(args):
            if self.is_cancelled():
                return
            clip_source, highlight, idx = args
            try:
                self.process_clip(
                    clip_source, highlight, idx, total_clips,
                    add_captions=add_captions, add_hook=add_hook, pre_cut=pre_cut,
                )
            finally:
                if pre_cut:
                    try:
                        Path(clip_source).unlink(missing_ok=True)
                    except Exception:
                        pass

        if sections is not None:
            tasks = sections
        else:
            tasks = [(source_path, h, i) for i, h in enumerate(highlights, 1)]

        if workers == 1:
            for task in tasks:
                if self.is_cancelled():
                    break
                _do_clip(task)
        else:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="clip-worker") as executor:
                futures = {executor.submit(_do_clip, task): task[2] for task in tasks}
                for future in as_completed(futures):
                    clip_idx = futures[future]
                    try:
                        future.result()
                    except Exception as exc:
                        self.log(f"  Clip {clip_idx} failed: {exc}")
                        raise
                    if self.is_cancelled():
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

