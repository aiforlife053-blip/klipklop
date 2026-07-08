import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from openai import APIConnectionError, APIError, APIStatusError, RateLimitError

from clipper_shared import SUBPROCESS_FLAGS, SubtitleNotFoundError, YTDLP_MODULE_AVAILABLE, _hex_to_rgb, yt_dlp
from utils.helpers import get_deno_path, get_ffmpeg_path, is_ytdlp_module_available
from utils.logger import debug_log


class FfmpegMixin:
    _CPU_FALLBACK_ARGS = ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23']
    _GPU_ENCODER_NAMES = (
        'h264_nvenc', 'hevc_nvenc',
        'h264_qsv', 'hevc_qsv',
        'h264_amf', 'hevc_amf',
        'h264_videotoolbox', 'hevc_videotoolbox',
        'h264_mf', 'hevc_mf',
    )

    def enable_gpu_acceleration(self, enabled: bool = True):
        """Enable or disable GPU acceleration for video encoding"""
        self.gpu_enabled = enabled
        
        if enabled:
            try:
                from utils.gpu_detector import GPUDetector
                detector = GPUDetector(self.ffmpeg_path)
                self.gpu_encoder_args = detector.get_encoder_args(use_gpu=True)
                self.log(f"  ⚡ GPU Acceleration: ENABLED")
                self.log(f"  Encoder args: {' '.join(self.gpu_encoder_args)}")
            except Exception as e:
                self.log(f"  ⚠ GPU Acceleration failed to initialize: {e}")
                self.log(f"  Falling back to CPU encoding")
                self.gpu_enabled = False
                self.gpu_encoder_args = []
        else:
            self.log(f"  💻 GPU Acceleration: DISABLED (using CPU)")
            self.gpu_encoder_args = []

    def get_video_encoder_args(self) -> list:
        """Get video encoder arguments based on GPU settings"""
        if self.gpu_enabled and self.gpu_encoder_args:
            return self.gpu_encoder_args
        else:
            if getattr(self, "optimize_mode", "local") in {"local", "hosting_2cpu", "fast_cpu"}:
                return ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23']
            return ['-c:v', 'libx264', '-preset', 'fast', '-crf', '18']

    def _is_gpu_encoder_error(cls, stderr: str) -> bool:
        """Heuristically detect FFmpeg failures caused by GPU encoder options."""
        if not stderr:
            return False
        text = stderr.lower()
        # Mention of any hardware encoder + a known option/init failure phrase
        mentions_hw = any(enc in text for enc in cls._GPU_ENCODER_NAMES)
        failure_phrases = (
            'error applying encoder options',
            'error setting option',
            'unable to parse',
            'no nvenc capable devices found',
            'cannot load nvcuda',
            'cannot load nvencodeapi',
            'failed loading nvenc',
            'device creation failed',
            'no device available',
            'impossible to convert between',
            'function not implemented',
        )
        mentions_failure = any(p in text for p in failure_phrases)
        return mentions_hw and mentions_failure

    def _swap_cmd_to_cpu_encoder(cls, cmd: list) -> list:
        """Return a copy of cmd with any GPU encoder block replaced by CPU args.

        This walks the command, finds every ``-c:v <hw_encoder>`` and removes
        the encoder + any GPU-specific options that follow it (until the next
        FFmpeg flag or input/output token). It then injects the CPU fallback
        args in the same position. Audio codec args (``-c:a``) are preserved.
        """
        if not cmd:
            return cmd

        # Options that are known to belong to GPU encoders. We strip them
        # together with their value so libx264 doesn't choke on them.
        gpu_only_opts = {
            '-preset', '-rc', '-cq', '-qp', '-qp_i', '-qp_p', '-qp_b',
            '-quality', '-global_quality', '-look_ahead', '-rc_lookahead',
            '-spatial_aq', '-temporal_aq', '-aq-strength', '-tune',
            '-profile:v', '-level', '-b:v', '-maxrate', '-bufsize',
            '-pix_fmt',
        }

        new_cmd = []
        i = 0
        replaced = False
        while i < len(cmd):
            token = cmd[i]
            if token == '-c:v' and i + 1 < len(cmd) and cmd[i + 1] in cls._GPU_ENCODER_NAMES:
                # Inject CPU fallback once
                if not replaced:
                    new_cmd.extend(cls._CPU_FALLBACK_ARGS)
                    replaced = True
                # Skip '-c:v <hw_encoder>'
                i += 2
                # Skip any trailing GPU-specific options
                while i < len(cmd) - 1 and cmd[i] in gpu_only_opts:
                    i += 2
                continue
            new_cmd.append(token)
            i += 1

        # If no GPU encoder was present in cmd but caller still asked for
        # fallback, leave cmd untouched (nothing to swap).
        return new_cmd if replaced else list(cmd)

    def _disable_gpu_acceleration_runtime(self, reason: str = ""):
        """Disable GPU encoding for the rest of this processing session."""
        if not self.gpu_enabled:
            return
        self.gpu_enabled = False
        self.gpu_encoder_args = []
        msg = "  ⚠ GPU encoding disabled for the rest of this session"
        if reason:
            msg += f" ({reason})"
        self.log(msg)
        self.log("  💻 Continuing with CPU encoding (libx264)")

    def _run_ffmpeg_subprocess(self, cmd: list, **kwargs):
        """Run an FFmpeg command with automatic CPU fallback on GPU encoder errors.

        Wraps ``subprocess.run`` and, if the command fails with a signature
        that looks like a GPU encoder problem, rewrites the command to use
        libx264 and retries once. Returns the final ``CompletedProcess``.
        """
        kwargs.setdefault('capture_output', True)
        kwargs.setdefault('text', True)
        kwargs.setdefault('creationflags', SUBPROCESS_FLAGS)

        result = subprocess.run(cmd, **kwargs)
        if result.returncode == 0:
            return result

        stderr = result.stderr or ''
        if not self._is_gpu_encoder_error(stderr):
            return result

        # Looks like a GPU encoder issue: swap to CPU and retry once.
        fallback_cmd = self._swap_cmd_to_cpu_encoder(cmd)
        if fallback_cmd == list(cmd):
            # No GPU encoder found in cmd to swap; return original failure.
            return result

        self.log("  ⚠ FFmpeg failed with GPU encoder error, retrying on CPU...")
        # Pull a short reason line from stderr for the log
        reason_line = next(
            (ln.strip() for ln in stderr.splitlines()
             if 'error' in ln.lower() or 'unable' in ln.lower()),
            ''
        )
        self._disable_gpu_acceleration_runtime(reason_line[:120])

        retry = subprocess.run(fallback_cmd, **kwargs)
        return retry

    def log_ffmpeg_command(self, cmd: list, description: str = "FFmpeg"):
        """Log FFmpeg command for debugging"""
        # Format command nicely
        cmd_str = ' '.join(f'"{arg}"' if ' ' in str(arg) else str(arg) for arg in cmd)
        self.log(f"  🎬 {description} Command:")
        self.log(f"     {cmd_str}")

    def _find_system_font_bold(self) -> str:
        """Find a bold system font across platforms"""
        if sys.platform == "win32":
            candidates = [
                "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/segoeui.ttf",
            ]
        elif sys.platform == "darwin":
            candidates = [
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/Library/Fonts/Arial Bold.ttf",
                "/Library/Fonts/Arial.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
                "/System/Library/Fonts/SFNS.ttf",
            ]
        else:
            candidates = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            ]
        
        for font in candidates:
            if os.path.exists(font):
                return font
        return None

    def _get_ffmpeg_font_path(self) -> str:
        """Get fontfile argument for FFmpeg drawtext filter, platform-aware"""
        font = self._find_system_font_bold()
        if font:
            if sys.platform == "win32":
                # Escape colon for FFmpeg filter on Windows
                escaped = font.replace("\\", "/").replace(":", "\\:")
                return f"fontfile='{escaped}':"
            else:
                return f"fontfile='{font}':"
        # Fallback: let FFmpeg use fontconfig default
        return "font='Arial':"

    def run_ffmpeg_with_progress(self, cmd: list, duration: float, progress_callback):
        """Run ffmpeg command and parse progress"""
        print(f"[DEBUG] Running ffmpeg command: {' '.join(cmd[:5])}...")
        print(f"[DEBUG] Expected duration: {duration}s")
        
        # Just run ffmpeg normally without progress parsing for now
        # Progress parsing from ffmpeg is complex due to carriage returns
        # _run_ffmpeg_subprocess auto-falls-back to libx264 if a GPU encoder
        # error is detected (e.g. invalid preset on h264_qsv).
        result = self._run_ffmpeg_subprocess(cmd)
        
        # Set to 100% when done
        progress_callback(1.0)
        print(f"[DEBUG] FFmpeg completed with return code: {result.returncode}")
        
        if result.returncode != 0:
            error_msg = result.stderr if result.stderr else "Unknown FFmpeg error"
            
            # Extract the actual error (usually at the end)
            error_lines = error_msg.split('\n')
            relevant_errors = [line for line in error_lines if any(keyword in line.lower() for keyword in 
                ['error', 'invalid', 'failed', 'cannot', 'unable', 'not found', 'does not exist'])]
            
            # Get last 10 lines which usually contain the actual error
            last_lines = '\n'.join(error_lines[-10:])
            
            print(f"[FFMPEG ERROR] Full stderr:\n{error_msg}")
            self.log(f"FFmpeg command failed: {' '.join(cmd)}")
            self.log(f"FFmpeg full error output:\n{error_msg}")
            
            # Show relevant error or last lines
            if relevant_errors:
                error_summary = '\n'.join(relevant_errors[-5:])
            else:
                error_summary = last_lines
            
            raise Exception(f"FFmpeg process failed:\n{error_summary}")

    def format_time(self, seconds: float) -> str:
        """Convert seconds to ASS time format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centisecs = int((seconds % 1) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"

    def parse_timestamp(self, ts: str) -> float:
        """Convert timestamp to seconds"""
        ts = ts.replace(",", ".")
        parts = ts.split(":")
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])

    def cleanup(self):
        """Clean up temp files"""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
