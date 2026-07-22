import json
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from openai import APIConnectionError, APIError, APIStatusError, RateLimitError

from clipper_shared import SUBPROCESS_FLAGS, SubtitleNotFoundError, YTDLP_MODULE_AVAILABLE, _hex_to_rgb, yt_dlp
from clipper_base import ClipperBase
from utils.helpers import get_deno_path, get_ffmpeg_path, is_ytdlp_module_available
from utils.logger import debug_log


_FFMPEG_PROCESS_LOCK = threading.Lock()


class FfmpegMixin(ClipperBase):
    _CPU_FALLBACK_ARGS = ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23']
    _PROBE_TIMEOUT = 30
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
        if str(getattr(self, "video_quality", "720")) in {"1440", "2160"}:
            return ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28']
        if getattr(self, "optimize_mode", "local") in {"local", "hosting_2cpu", "fast_cpu"}:
            crf = '21' if str(getattr(self, "video_quality", "720")) == "1080" else '28'
            return ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', crf]
        return ['-c:v', 'libx264', '-preset', 'fast', '-crf', '18']

    @classmethod
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

    @classmethod
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

    def _stop_subprocess(self, proc):
        if proc.poll() is not None:
            return proc.communicate()
        try:
            proc.terminate()
        except OSError:
            pass
        try:
            return proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass
            return proc.communicate()

    def _run_cancelable_subprocess(self, cmd: list, deadline=None, **kwargs):
        capture_output = kwargs.pop('capture_output', False)
        text = kwargs.pop('text', False)
        timeout = kwargs.pop('timeout', None)
        if timeout is not None:
            timeout_deadline = time.monotonic() + timeout
            deadline = min(deadline, timeout_deadline) if deadline is not None else timeout_deadline
        if capture_output:
            kwargs.setdefault('stdout', subprocess.PIPE)
            kwargs.setdefault('stderr', subprocess.PIPE)
        proc = subprocess.Popen(cmd, text=text, **kwargs)
        try:
            while True:
                if self.is_cancelled():
                    self._stop_subprocess(proc)
                    raise InterruptedError("Stopped")
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    self._stop_subprocess(proc)
                    raise TimeoutError(f"Command timed out: {cmd[0]}")
                try:
                    stdout, stderr = proc.communicate(timeout=min(0.25, remaining) if remaining is not None else 0.25)
                    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    continue
        except Exception:
            if proc.poll() is None:
                self._stop_subprocess(proc)
            raise

    def _run_ffmpeg_subprocess(self, cmd: list, **kwargs):
        """Run an FFmpeg command with automatic CPU fallback on GPU encoder errors.

        Wraps ``subprocess.run`` and, if the command fails with a signature
        that looks like a GPU encoder problem, rewrites the command to use
        libx264 and retries once. Returns the final ``CompletedProcess``.
        """
        kwargs.setdefault('capture_output', True)
        kwargs.setdefault('text', True)
        kwargs.setdefault('creationflags', SUBPROCESS_FLAGS)
        deadline = kwargs.pop('deadline', None)
        timeout = kwargs.pop('timeout', None)
        if timeout is not None:
            timeout_deadline = time.monotonic() + timeout
            deadline = min(deadline, timeout_deadline) if deadline is not None else timeout_deadline

        result = self._run_cancelable_subprocess(cmd, deadline=deadline, **kwargs)
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

        retry = self._run_cancelable_subprocess(fallback_cmd, deadline=deadline, **kwargs)
        return retry

    def _run_probe_subprocess(self, cmd: list, **kwargs):
        kwargs.setdefault('timeout', self._PROBE_TIMEOUT)
        with _FFMPEG_PROCESS_LOCK:
            return self._run_cancelable_subprocess(cmd, **kwargs)

    def log_ffmpeg_command(self, cmd: list, description: str = "FFmpeg"):
        """Log FFmpeg command for debugging"""
        # Format command nicely
        cmd_str = ' '.join(f'"{arg}"' if ' ' in str(arg) else str(arg) for arg in cmd)
        self.log(f"  🎬 {description} Command:")
        self.log(f"     {cmd_str}")

    def _run_ffmpeg_progress_once(self, cmd: list, duration: float, progress_callback, deadline=None):
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=SUBPROCESS_FLAGS)
        output = deque(maxlen=200)
        lines = queue.Queue()

        def read_output():
            try:
                for line in proc.stdout or []:
                    lines.put(line)
            finally:
                lines.put(None)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        try:
            while True:
                if self.is_cancelled():
                    self._stop_subprocess(proc)
                    raise InterruptedError("Stopped")
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    self._stop_subprocess(proc)
                    raise TimeoutError(f"Command timed out: {cmd[0]}")
                try:
                    line = lines.get(timeout=min(0.25, remaining) if remaining is not None else 0.25)
                except queue.Empty:
                    if proc.poll() is not None and not reader.is_alive():
                        break
                    continue
                if line is None:
                    break
                output.append(line)
                text = line.strip()
                value = None
                if text.startswith("out_time_ms="):
                    try:
                        value = float(text.split("=", 1)[1]) / 1_000_000
                    except ValueError:
                        value = None
                elif text.startswith("out_time="):
                    match = re.search(r"(\d+):(\d+):(\d+(?:\.\d+)?)", text)
                    if match:
                        h, m, s = match.groups()
                        value = int(h) * 3600 + int(m) * 60 + float(s)
                if value is not None and duration > 0:
                    progress_callback(max(0.0, min(0.99, value / duration)))
            proc.wait()
            combined_output = "".join(output)
            return subprocess.CompletedProcess(cmd, proc.returncode, combined_output, combined_output)
        except Exception:
            if proc.poll() is None:
                self._stop_subprocess(proc)
            raise

    def run_ffmpeg_with_progress(self, cmd: list, duration: float, progress_callback, timeout=None, deadline=None):
        """Run ffmpeg command and parse progress"""
        debug_log(f"Running ffmpeg command: {' '.join(cmd[:5])}...")
        debug_log(f"Expected duration: {duration}s")
        if timeout is not None:
            timeout_deadline = time.monotonic() + timeout
            deadline = min(deadline, timeout_deadline) if deadline is not None else timeout_deadline
        with _FFMPEG_PROCESS_LOCK:
            if "-progress" in cmd and "pipe:1" in cmd:
                result = self._run_ffmpeg_progress_once(cmd, duration, progress_callback, deadline=deadline)
                if result.returncode != 0 and self._is_gpu_encoder_error(result.stderr or result.stdout or ""):
                    fallback_cmd = self._swap_cmd_to_cpu_encoder(cmd)
                    if fallback_cmd != list(cmd):
                        self._disable_gpu_acceleration_runtime("FFmpeg GPU progress command failed")
                        result = self._run_ffmpeg_progress_once(fallback_cmd, duration, progress_callback, deadline=deadline)
            else:
                result = self._run_ffmpeg_subprocess(cmd, deadline=deadline)
        progress_callback(1.0)
        debug_log(f"FFmpeg completed with return code: {result.returncode}")
        
        if result.returncode != 0:
            error_msg = result.stderr if result.stderr else "Unknown FFmpeg error"
            
            # Extract the actual error (usually at the end)
            error_lines = error_msg.split('\n')
            relevant_errors = [line for line in error_lines if any(keyword in line.lower() for keyword in 
                ['error', 'invalid', 'failed', 'cannot', 'unable', 'not found', 'does not exist'])]
            
            # Get last 10 lines which usually contain the actual error
            last_lines = '\n'.join(error_lines[-10:])
            
            debug_log(f"[FFMPEG ERROR] Full stderr:\n{error_msg}")
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
