"""
Base class for all AutoClipper mixin classes.
Defines shared attributes so type checkers (Pyrefly, Pyright, mypy)
understand the mixin pattern properly.

All Mixin classes (FfmpegMixin, DownloadMixin, AiMixin, PortraitMixin, ExportMixin)
inherit from this base so self.log, self.ffmpeg_path, etc. are known to type checkers.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional


class ClipperBase:
    """Shared attribute declarations for all mixin classes."""

    # --- Paths & external tools ---
    ffmpeg_path: str
    ytdlp_path: str
    output_dir: Path
    temp_dir: Path
    cache_dir: Path

    # --- AI clients ---
    highlight_client: Any
    caption_client: Any
    tts_client: Any
    tts_api_key: str
    tts_model: str
    tts_voice: str
    whisper_model: str
    model: str
    temperature: float
    system_prompt: str
    ai_providers: dict

    # --- Video metadata ---
    video_info: dict
    channel_name: str
    video_quality: str
    output_resolution: str
    landscape_blur: bool
    screen_size: str
    subtitle_language: str

    # --- Feature settings ---
    watermark_settings: dict
    credit_watermark_settings: dict
    hook_style_settings: dict
    blur_background_settings: dict
    subtitle_style: dict
    subtitle_engine: str
    local_whisper: dict
    face_tracking_mode: str
    mediapipe_settings: dict
    optimize_mode: str
    use_download_sections: bool

    # --- GPU ---
    gpu_enabled: bool
    gpu_encoder_args: list

    # --- MediaPipe ---
    mp_face_mesh: Any
    mp_drawing: Any
    _local_whisper_model: Any

    # --- Callbacks ---
    log: Callable[..., None]
    set_progress: Callable[..., None]
    report_tokens: Callable[..., None]
    is_cancelled: Callable[[], bool]
