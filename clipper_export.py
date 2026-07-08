import base64
import hashlib
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


class ExportMixin:
    def process_clip(self, video_path: str, highlight: dict, index: int, total_clips: int = 1, add_captions: bool = True, add_hook: bool = True, pre_cut: bool = False):
        """Process a single clip: cut, portrait, hook (optional), captions (optional)
        
        Args:
            video_path: Path to source video (full video or pre-cut section)
            highlight: Highlight dict with metadata
            index: Clip index (1-based)
            total_clips: Total number of clips being processed
            add_captions: Whether to add captions
            add_hook: Whether to add hook
            pre_cut: If True, video_path is already a pre-cut section (skip cutting step)
        """
        
        # Check cancel before starting
        if self.is_cancelled():
            return
        
        # Create output folder with unique timestamp per clip
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{index:02d}"
        clip_dir = self.output_dir / timestamp
        clip_dir.mkdir(parents=True, exist_ok=True)
        
        self.log(f"  Output folder: {clip_dir}")
        
        start = highlight["start_time"].replace(",", ".")
        end = highlight["end_time"].replace(",", ".")
        
        self.log(f"\n[Clip {index}] {highlight['title']}")
        
        # Calculate total steps based on options
        total_steps = 1  # Re-encode/Cut is always 1 step
        total_steps += 1  # Portrait conversion always
        if add_hook:
            total_steps += 1
        if add_captions:
            total_steps += 1
        
        # Helper to report sub-progress with percentage
        def clip_progress(step_name: str, step_num: int, sub_progress: float = 0):
            # Calculate overall progress: base (30%) + clip progress (60%)
            clip_base = 0.3 + (0.6 * (index - 1) / total_clips)
            clip_portion = 0.6 / total_clips
            step_progress = clip_portion * ((step_num + sub_progress) / total_steps)
            overall = clip_base + step_progress
            
            # Format with percentage
            percent = int(sub_progress * 100)
            if percent > 0:
                status = f"Clip {index}/{total_clips}: {step_name} ({percent}%)"
            else:
                status = f"Clip {index}/{total_clips}: {step_name}"
            
            print(f"[DEBUG] clip_progress: {status} (overall: {overall*100:.1f}%)")
            self.set_progress(status, overall)
        
        current_step = 0
        
        # Step 1: Cut video (skip if pre-cut section from --download-sections)
        if self.is_cancelled():
            return
        
        landscape_file = clip_dir / "temp_landscape.mp4"
        duration = self.parse_timestamp(end) - self.parse_timestamp(start)
        
        if pre_cut:
            # Video is already cut to the right section, just re-encode for consistency
            clip_progress("Re-encoding video...", current_step, 0)
            
            encoder_args = self.get_video_encoder_args()
            
            cmd = [
                self.ffmpeg_path, "-y",
                "-i", video_path,
                *encoder_args,
                "-c:a", "aac", "-b:a", "192k",
                "-progress", "pipe:1",
                str(landscape_file)
            ]
            
            self.log_ffmpeg_command(cmd, "Re-encode Pre-cut Section")
            
            self.run_ffmpeg_with_progress(cmd, duration, 
                lambda p: clip_progress("Re-encoding video...", current_step, p))
            
            self.log("  ✓ Re-encoded pre-cut section")
        else:
            # Original flow: cut from full video
            clip_progress("Cutting video...", current_step, 0)
            
            encoder_args = self.get_video_encoder_args()
            
            cmd = [
                self.ffmpeg_path, "-y",
                "-ss", start,
                "-i", video_path,
                "-t", str(duration),
                *encoder_args,
                "-c:a", "aac", "-b:a", "192k",
                "-progress", "pipe:1",
                str(landscape_file)
            ]
            
            self.log_ffmpeg_command(cmd, "Cut Video")
            
            self.run_ffmpeg_with_progress(cmd, duration, 
                lambda p: clip_progress("Cutting video...", current_step, p))
            
            self.log("  ✓ Cut video")
        
        current_step += 1
        
        # Step 2: Convert to selected aspect ratio with progress
        if self.is_cancelled():
            return
        portrait_file = clip_dir / "temp_portrait.mp4"
        if getattr(self, "screen_size", "9:16") == "16:9":
            self.log("  ⊘ Skipped portrait conversion (16:9)")
            current_output = landscape_file
        else:
            clip_progress("Converting to portrait...", current_step, 0)
            self.convert_to_portrait_with_progress(str(landscape_file), str(portrait_file), 
                lambda p: clip_progress("Converting to portrait...", current_step, p))
            self.log("  ✓ Portrait conversion")
            current_output = portrait_file
        current_step += 1
        
        # Track which file is the current output
        hook_duration = 0
        
        # Step 3: Add hook (optional)
        if add_hook:
            if self.is_cancelled():
                return
            clip_progress("Adding hook...", current_step, 0)
            hooked_file = clip_dir / "temp_hooked.mp4"
            hook_text = highlight.get("hook_text", highlight["title"])
            hook_duration = self.add_hook_with_progress(str(current_output), hook_text, str(hooked_file),
                lambda p: clip_progress("Adding hook...", current_step, p))
            if hook_duration > 0:
                if not hooked_file.exists():
                    raise Exception(f"Failed to create hooked video: {hooked_file}")
                self.log(f"  ✓ Added hook ({hook_duration:.1f}s)")
                current_output = hooked_file
            else:
                self.log("  ⊘ Skipped hook")
                add_hook = False
            current_step += 1
        else:
            self.log("  ⊘ Skipped hook (disabled)")
        
        # Step 4: Add captions (optional)
        final_file = clip_dir / "master.mp4"
        if add_captions and getattr(self, "screen_size", "9:16") == "16:9":
            self.log("  ⊘ Skipped captions (landscape)")
            add_captions = False

        if add_captions:
            if self.is_cancelled():
                return
            clip_progress("Adding captions...", current_step, 0)
            
            audio_source = str(portrait_file if getattr(self, "screen_size", "9:16") != "16:9" else landscape_file) if add_hook else None
            
            # If watermark enabled, add captions to temp file first
            if self.watermark_settings.get("enabled"):
                temp_captioned = clip_dir / "temp_captioned.mp4"
                self.add_captions_api_with_progress(str(current_output), str(temp_captioned), audio_source, hook_duration,
                    lambda p: clip_progress("Adding captions...", current_step, p))
                
                if not temp_captioned.exists():
                    raise Exception(f"Failed to create captioned video: {temp_captioned}")
                
                current_output = temp_captioned
            else:
                # No watermark, captions go directly to final
                self.add_captions_api_with_progress(str(current_output), str(final_file), audio_source, hook_duration,
                    lambda p: clip_progress("Adding captions...", current_step, p))
                
                if not final_file.exists():
                    raise Exception(f"Failed to create final video: {final_file}")
            
            self.log("  ✓ Added captions")
            current_step += 1
        else:
            self.log("  ⊘ Skipped captions (disabled)")
        
        # Step 5: Add watermark (if enabled)
        if self.watermark_settings.get("enabled"):
            if self.is_cancelled():
                return
            
            # Check if we need to add watermark step to progress
            if not add_captions:
                # Watermark is a new step
                total_steps += 1
            
            clip_progress("Adding watermark...", current_step, 0)
            
            # Apply watermark to current output
            self.add_watermark_with_progress(str(current_output), str(final_file),
                lambda p: clip_progress("Adding watermark...", current_step, p))
            
            if not final_file.exists():
                raise Exception(f"Failed to create final video with watermark: {final_file}")
            
            self.log("  ✓ Added watermark")
            current_output = final_file
            current_step += 1
            
            # Cleanup temp captioned file if exists
            if add_captions:
                try:
                    temp_captioned = clip_dir / "temp_captioned.mp4"
                    if temp_captioned.exists():
                        temp_captioned.unlink()
                except Exception as e:
                    self.log(f"  Warning: Could not delete temp_captioned.mp4: {e}")
        elif not add_captions:
            # No captions and no watermark, just copy current output to final
            import shutil
            shutil.copy(str(current_output), str(final_file))
            current_output = final_file
        
        # Step 6: Add credit watermark (if enabled)
        if self.credit_watermark_settings.get("enabled") and self.channel_name:
            if self.is_cancelled():
                return
            
            total_steps += 1
            clip_progress("Adding credit...", current_step, 0)
            
            # If current_output is already final_file, we need a temp file
            if str(current_output) == str(final_file):
                temp_credit_input = clip_dir / "temp_before_credit.mp4"
                import shutil
                shutil.copy(str(final_file), str(temp_credit_input))
                current_output = temp_credit_input
            
            self.add_credit_watermark_with_progress(str(current_output), str(final_file),
                lambda p: clip_progress("Adding credit...", current_step, p))
            
            if not final_file.exists():
                raise Exception(f"Failed to create final video with credit: {final_file}")
            
            self.log(f"  ✓ Added credit: sc: {self.channel_name}")
            current_step += 1
            
            # Cleanup temp file
            try:
                temp_credit_input = clip_dir / "temp_before_credit.mp4"
                if temp_credit_input.exists():
                    temp_credit_input.unlink()
            except Exception as e:
                self.log(f"  Warning: Could not delete temp_before_credit.mp4: {e}")
        
        # Mark complete
        clip_progress("Done", total_steps, 0)
        
        # Cleanup temp files
        try:
            if landscape_file.exists():
                landscape_file.unlink()
        except Exception as e:
            self.log(f"  Warning: Could not delete {landscape_file.name}: {e}")
        
        try:
            if portrait_file.exists():
                portrait_file.unlink()
        except Exception as e:
            self.log(f"  Warning: Could not delete {portrait_file.name}: {e}")
        
        if add_hook:
            try:
                hooked_file = clip_dir / "temp_hooked.mp4"
                if hooked_file.exists():
                    hooked_file.unlink()
            except Exception as e:
                self.log(f"  Warning: Could not delete temp_hooked.mp4: {e}")
        
        # Save metadata
        metadata = {
            "title": highlight["title"],
            "description": highlight.get("description", ""),
            "source_title": self.video_info.get("title", ""),
            "source_description": self.video_info.get("description", ""),
            "hook_text": highlight.get("hook_text", highlight["title"]),
            "start_time": highlight["start_time"],
            "end_time": highlight["end_time"],
            "duration_seconds": highlight["duration_seconds"],
            "has_hook": add_hook,
            "has_captions": add_captions,
            "has_watermark": self.watermark_settings.get("enabled", False),
            "has_credit": self.credit_watermark_settings.get("enabled", False),
            "channel_name": self.channel_name,
        }
        
        with open(clip_dir / "data.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def add_hook(self, input_path: str, hook_text: str, output_path: str) -> float:
        """Add hook scene at the beginning with multi-line yellow text (Fajar Sadboy style)"""
        
        if not self.tts_client:
            return self.add_hook_with_progress(input_path, hook_text, output_path, lambda _: None)
        self.report_tokens(0, 0, 0, len(hook_text))
        
        try:
            tts_response = self.tts_client.audio.speech.create(
                model=self.tts_model,
                voice="nova",
                input=hook_text,
                speed=1.0
            )
        except APIConnectionError as e:
            self.log(f"  ❌ TTS API Connection Error: Could not connect to {self.tts_client.base_url}")
            raise Exception(f"TTS API connection failed!\n\nCould not connect to: {self.tts_client.base_url}\nError: {e}")
        except RateLimitError as e:
            self.log(f"  ❌ TTS API Rate Limit: {e}")
            raise Exception(f"TTS API rate limit exceeded!\n\nPlease wait a moment and try again.\nDetails: {e}")
        except APIStatusError as e:
            self.log(f"  ❌ TTS API Error (HTTP {e.status_code}): {e.message}")
            self.log(f"     Model: {self.tts_model}, Base URL: {self.tts_client.base_url}")
            raise Exception(
                f"TTS (Hook) API Error!\n\n"
                f"Status: {e.status_code}\n"
                f"Message: {e.message}\n"
                f"Model: {self.tts_model}\n"
                f"Base URL: {self.tts_client.base_url}\n\n"
                f"Check your Hook Maker API settings."
            )
        except Exception as e:
            self.log(f"  ❌ TTS API Unexpected Error: {type(e).__name__}: {e}")
            raise Exception(f"TTS (Hook) generation failed!\n\nError: {type(e).__name__}: {e}\nModel: {self.tts_model}")
        
        tts_file = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False).name
        with open(tts_file, 'wb') as f:
            f.write(tts_response.content)
        
        # Get TTS duration using ffprobe
        probe_cmd = [
            self.ffmpeg_path, "-i", tts_file,
            "-f", "null", "-"
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
        duration_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
        
        if duration_match:
            h, m, s = duration_match.groups()
            hook_duration = int(h) * 3600 + int(m) * 60 + float(s) + 0.5
        else:
            hook_duration = 3.0
        
        # Format hook text: uppercase, split into lines (max 3 words per line for better visibility)
        hook_upper = hook_text.upper()
        words = hook_upper.split()
        
        # Split into lines (max 3 words per line - Fajar Sadboy style)
        lines = []
        current_line = []
        for word in words:
            current_line.append(word)
            if len(current_line) >= 3:
                lines.append(' '.join(current_line))
                current_line = []
        if current_line:
            lines.append(' '.join(current_line))
        
        # Get input video info
        probe_cmd = [self.ffmpeg_path, "-i", input_path]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
        
        # Extract fps
        fps_match = re.search(r'(\d+(?:\.\d+)?)\s*fps', result.stderr)
        fps = float(fps_match.group(1)) if fps_match else 30
        
        # Extract resolution
        res_match = re.search(r'(\d{3,4})x(\d{3,4})', result.stderr)
        if res_match:
            width, height = int(res_match.group(1)), int(res_match.group(2))
        else:
            width, height = 1080, 1920
        
        # Create hook video: freeze first frame + TTS audio + text overlay
        hook_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
        
        # Build drawtext filter for each line
        # Style: Yellow/gold text on white background box
        drawtext_filters = []
        line_height = 85  # pixels between lines
        font_size = 58
        total_text_height = len(lines) * line_height
        start_y = (height // 3) - (total_text_height // 2)  # Position at upper third
        
        for i, line in enumerate(lines):
            # Escape special characters for FFmpeg drawtext
            escaped_line = line.replace("'", "'\\''").replace(":", "\\:").replace("\\", "\\\\")
            y_pos = start_y + (i * line_height)
            
            # Yellow/gold text with white box background
            font_path = self._get_ffmpeg_font_path()
            drawtext_filters.append(
                f"drawtext=text='{escaped_line}':"
                f"{font_path}"
                f"fontsize={font_size}:"
                f"fontcolor=#FFD700:"  # Golden yellow
                f"box=1:"
                f"boxcolor=white@0.95:"  # White background
                f"boxborderw=12:"  # Padding around text
                f"x=(w-text_w)/2:"
                f"y={y_pos}"
            )
        
        filter_chain = ",".join(drawtext_filters)
        
        # Get encoder args
        encoder_args = self.get_video_encoder_args()
        
        # Step 1: Create hook video with frozen frame + text + TTS audio
        # Use -t to set exact duration, freeze first frame
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", input_path,
            "-i", tts_file,
            "-filter_complex",
            f"[0:v]trim=0:0.04,loop=loop=-1:size=1:start=0,setpts=N/{fps}/TB,{filter_chain},trim=0:{hook_duration},setpts=PTS-STARTPTS[v];"
            f"[1:a]aresample=44100,apad=whole_dur={hook_duration}[a]",
            "-map", "[v]",
            "-map", "[a]",
            *encoder_args,
            "-r", str(fps),
            "-s", f"{width}x{height}",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-ac", "2",
            "-t", str(hook_duration),
            hook_video
        ]
        self.log_ffmpeg_command(cmd, "Create Hook Video")
        result = self._run_ffmpeg_subprocess(cmd)
        
        if result.returncode != 0:
            error_lines = result.stderr.split('\n') if result.stderr else []
            actual_errors = [line for line in error_lines if 'error' in line.lower()]
            error_msg = '\n'.join(actual_errors[-3:]) if actual_errors else "Unknown error"
            raise Exception(f"Failed to create hook video: {error_msg}")
        
        # Step 2: Re-encode main video to EXACT same format (critical for concat)
        main_reencoded = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", input_path,
            *encoder_args,
            "-r", str(fps),
            "-s", f"{width}x{height}",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-ac", "2",
            main_reencoded
        ]
        self.log_ffmpeg_command(cmd, "Re-encode Main Video")
        result = self._run_ffmpeg_subprocess(cmd)
        
        if result.returncode != 0:
            error_lines = result.stderr.split('\n') if result.stderr else []
            actual_errors = [line for line in error_lines if 'error' in line.lower()]
            error_msg = '\n'.join(actual_errors[-3:]) if actual_errors else "Unknown error"
            raise Exception(f"Failed to re-encode main video: {error_msg}")
        
        # Step 3: Concatenate using concat demuxer (more reliable than filter_complex)
        concat_list = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False).name
        with open(concat_list, 'w') as f:
            f.write(f"file '{hook_video.replace(chr(92), '/')}'\n")
            f.write(f"file '{main_reencoded.replace(chr(92), '/')}'\n")
        
        cmd = [
            self.ffmpeg_path, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
        
        # If concat demuxer fails, try filter_complex as fallback
        if result.returncode != 0:
            # Extract actual error message (skip ffmpeg version info)
            error_lines = result.stderr.split('\n') if result.stderr else []
            actual_errors = [line for line in error_lines if 'error' in line.lower() or 'invalid' in line.lower() or 'failed' in line.lower()]
            error_summary = '\n'.join(actual_errors[-3:]) if actual_errors else "Unknown concat error"
            
            self.log(f"  Concat demuxer failed: {error_summary[:100]}")
            self.log(f"  Trying filter_complex fallback...")
            
            cmd = [
                self.ffmpeg_path, "-y",
                "-i", hook_video,
                "-i", main_reencoded,
                "-filter_complex",
                "[0:v:0][0:a:0][1:v:0][1:a:0]concat=n=2:v=1:a=1[outv][outa]",
                "-map", "[outv]",
                "-map", "[outa]",
                *encoder_args,
                "-c:a", "aac",
                "-b:a", "192k",
                output_path
            ]
            self.log_ffmpeg_command(cmd, "Concat Hook (filter_complex fallback)")
            result = self._run_ffmpeg_subprocess(cmd)
            
            if result.returncode != 0:
                # Extract actual error, not version info
                error_lines = result.stderr.split('\n') if result.stderr else []
                actual_errors = [line for line in error_lines if 'error' in line.lower() or 'invalid' in line.lower() or 'failed' in line.lower()]
                error_msg = '\n'.join(actual_errors[-3:]) if actual_errors else result.stderr[-200:] if result.stderr else "Unknown error"
                raise Exception(f"Failed to concatenate hook video: {error_msg}")
        
        # Cleanup
        try:
            os.unlink(tts_file)
        except Exception as e:
            pass  # Ignore cleanup errors
        
        try:
            os.unlink(hook_video)
        except Exception as e:
            pass
        
        try:
            os.unlink(main_reencoded)
        except Exception as e:
            pass
        
        try:
            os.unlink(concat_list)
        except Exception as e:
            pass
        
        # Verify output was created
        if not os.path.exists(output_path):
            raise Exception(f"Failed to create hook video at {output_path}")
        
        return hook_duration

    def add_captions_api(self, input_path: str, output_path: str, audio_source: str = None, time_offset: float = 0):
        """Add CapCut-style captions using OpenAI Whisper API
        
        Args:
            input_path: Video to burn captions into (with hook)
            output_path: Output video path
            audio_source: Video to extract audio from for transcription (without hook)
            time_offset: Offset to add to all timestamps (hook duration)
        """
        
        # Use audio_source if provided, otherwise use input_path
        transcribe_source = audio_source if audio_source else input_path
        
        # Extract audio from video - use WAV format for better compatibility
        audio_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", transcribe_source,
            "-vn",
            "-acodec", "pcm_s16le",  # PCM 16-bit WAV
            "-ar", "16000",  # 16kHz sample rate
            "-ac", "1",  # Mono
            audio_file
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
        
        if result.returncode != 0:
            self.log(f"  Warning: Audio extraction failed")
            import shutil
            shutil.copy(input_path, output_path)
            return
        
        # Check if audio file exists and has content
        if not os.path.exists(audio_file) or os.path.getsize(audio_file) < 1000:
            self.log(f"  Warning: Audio file too small or missing")
            import shutil
            shutil.copy(input_path, output_path)
            if os.path.exists(audio_file):
                os.unlink(audio_file)
            return
        
        # Get audio duration for token reporting
        probe_cmd = [self.ffmpeg_path, "-i", audio_file, "-f", "null", "-"]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
        duration_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
        audio_duration = 0
        if duration_match:
            h, m, s = duration_match.groups()
            audio_duration = int(h) * 3600 + int(m) * 60 + float(s)
            self.report_tokens(0, 0, audio_duration, 0)
        
        try:
            transcript = self._whisper_transcribe_words(audio_file)
        except Exception:
            os.unlink(audio_file)
            raise
        
        os.unlink(audio_file)
        
        # Create ASS subtitle file with time offset for hook
        ass_file = tempfile.NamedTemporaryFile(mode='w', suffix='.ass', delete=False, encoding='utf-8').name
        event_count = self.create_ass_subtitle_capcut(transcript, ass_file, time_offset)
        self.log(f"  ASS events: {event_count}")
        if event_count <= 0:
            os.unlink(ass_file)
            raise Exception("Subtitle transcription produced 0 ASS events")
        
        # Burn subtitles into video using GPU/CPU encoder
        # Escape path for FFmpeg on Windows
        ass_path_escaped = ass_file.replace('\\', '/').replace(':', '\\:')
        fonts_dir_escaped = str(Path(__file__).resolve().parent / "fonts").replace('\\', '/').replace(':', '\\:')
        
        encoder_args = self.get_video_encoder_args()
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", input_path,
            "-vf", f"ass='{ass_path_escaped}':fontsdir='{fonts_dir_escaped}'",
            *encoder_args,
            "-c:a", "copy",
            output_path
        ]
        
        self.log_ffmpeg_command(cmd, "Burn Captions")
        result = self._run_ffmpeg_subprocess(cmd)
        os.unlink(ass_file)
        
        if result.returncode != 0:
            raise Exception(f"Caption burn failed: {result.stderr}")
        self.log("  Subtitle burn OK")

    def create_ass_subtitle_capcut(self, transcript, output_path: str, time_offset: float = 0):
        """Create ASS subtitle file with CapCut-style word-by-word highlighting"""
        
        style = getattr(self, "subtitle_style", {}) or {}
        font = str(style.get("font") or "Plus Jakarta Sans").replace(",", " ")
        size = int(style.get("size") or 58)
        alignment = 2
        bottom_margin = int(style.get("bottom_margin") or 360)
        ass_content = f"""[Script Info]
Title: Auto-generated captions
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00A07B24,&H00A07B24,-1,0,0,0,100,100,0,0,3,8,0,{alignment},80,80,{bottom_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        events = []
        
        # Check if we have word-level timestamps
        if hasattr(transcript, 'words') and transcript.words:
            words = []
            for word in transcript.words:
                text = str(getattr(word, 'word', '') or '').strip()
                start = float(getattr(word, 'start', 0) or 0)
                end = float(getattr(word, 'end', start + 0.25) or start + 0.25)
                if text and end > start:
                    words.append({'text': text, 'start': start, 'end': end})
            chunk = []
            chunks = []
            for index, word in enumerate(words):
                chunk.append(word)
                next_word = words[index + 1] if index + 1 < len(words) else None
                remaining = len(words) - index - 1
                should_flush = False
                if len(chunk) >= 3:
                    should_flush = not next_word or word['text'].rstrip().endswith(('.', ',', '?', '!')) or next_word['start'] - word['end'] > 0.45 or len(chunk) >= (4 if remaining == 3 else 5)
                if should_flush:
                    chunks.append(chunk)
                    chunk = []
            if chunk:
                chunks.append(chunk)
            for chunk in chunks:
                events.append({
                    'start': self.format_time(chunk[0]['start'] + time_offset),
                    'end': self.format_time(chunk[-1]['end'] + time_offset),
                    'text': ' '.join(item['text'] for item in chunk)
                })

        
        # Fallback: use segment-level timestamps if no word timestamps
        elif hasattr(transcript, 'segments') and transcript.segments:
            for segment in transcript.segments:
                start = segment.get('start', 0) + time_offset
                end = segment.get('end', 0) + time_offset
                text = segment.get('text', '').strip()
                
                if text:
                    words = text.split()
                    parts = [' '.join(words[i:i + 4]) for i in range(0, len(words), 4)] or [text]
                    span = max(0.25, (end - start) / len(parts))
                    for index, part in enumerate(parts):
                        part_start = start + index * span
                        part_end = end if index == len(parts) - 1 else min(end, part_start + span)
                        events.append({
                            'start': self.format_time(part_start),
                            'end': self.format_time(part_end),
                            'text': part
                        })
        
        # Write events to ASS file
        for event in events:
            text = str(event['text']).replace('{', '').replace('}', '').replace('\n', ' ')
            ass_content += f"Dialogue: 0,{event['start']},{event['end']},Default,,0,0,0,,{text}\n"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        return len(events)

    def _generate_gemini_tts(self, hook_text: str) -> str:
        api_key = getattr(self, "tts_api_key", "")
        if not api_key:
            raise RuntimeError("Gemini TTS API key kosong")
        cache_root = Path(os.environ.get("KLIPKLOP_CACHE_DIR") or self.output_dir.parent / "cache") / "tts"
        cache_root.mkdir(parents=True, exist_ok=True)
        cache_file = cache_root / f"{hashlib.sha1((getattr(self, 'tts_voice', 'Fenrir') + hook_text).encode('utf-8')).hexdigest()}.wav"
        if cache_file.exists():
            self.log("  ✓ Using cached hook TTS")
            return str(cache_file)
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=getattr(self, "tts_model", "gemini-3.1-flash-tts-preview"),
            contents=f"Say energetically in Indonesian: {hook_text}",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=getattr(self, "tts_voice", "Fenrir")
                        )
                    )
                )
            )
        )
        data = response.candidates[0].content.parts[0].inline_data.data
        audio = base64.b64decode(data) if isinstance(data, str) else data
        with open(cache_file, 'wb') as f:
            f.write(audio)
        return str(cache_file)

    def add_hook_with_progress(self, input_path: str, hook_text: str, output_path: str, progress_callback) -> float:
        """Add hook scene at the beginning with progress tracking"""
        
        progress_callback(0.1)
        if getattr(self, "tts_api_key", ""):
            try:
                tts_file = self._generate_gemini_tts(hook_text)
            except Exception as e:
                self.log(f"  ⊘ Hook skipped; Gemini TTS failed: {e}")
                return 0
            probe_cmd = [self.ffmpeg_path, "-i", tts_file, "-f", "null", "-"]
            result = subprocess.run(probe_cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
            duration_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
            if duration_match:
                h, m, s = duration_match.groups()
                hook_duration = int(h) * 3600 + int(m) * 60 + float(s) + 0.5
            else:
                hook_duration = 3.0
        elif self.tts_client:
            self.report_tokens(0, 0, 0, len(hook_text))
            try:
                tts_response = self.tts_client.audio.speech.create(
                    model=self.tts_model,
                    voice="nova",
                    input=hook_text,
                    speed=1.0
                )
            except APIConnectionError as e:
                self.log(f"  ❌ TTS API Connection Error: Could not connect to {self.tts_client.base_url}")
                raise Exception(f"TTS API connection failed!\n\nCould not connect to: {self.tts_client.base_url}\nError: {e}")
            except RateLimitError as e:
                self.log(f"  ❌ TTS API Rate Limit: {e}")
                raise Exception(f"TTS API rate limit exceeded!\n\nPlease wait a moment and try again.\nDetails: {e}")
            except APIStatusError as e:
                self.log(f"  ❌ TTS API Error (HTTP {e.status_code}): {e.message}")
                self.log(f"     Model: {self.tts_model}, Base URL: {self.tts_client.base_url}")
                raise Exception(
                    f"TTS (Hook) API Error!\n\n"
                    f"Status: {e.status_code}\n"
                    f"Message: {e.message}\n"
                    f"Model: {self.tts_model}\n"
                    f"Base URL: {self.tts_client.base_url}\n\n"
                    f"Check your Hook Maker API settings."
                )
            except Exception as e:
                self.log(f"  ❌ TTS API Unexpected Error: {type(e).__name__}: {e}")
                raise Exception(f"TTS (Hook) generation failed!\n\nError: {type(e).__name__}: {e}\nModel: {self.tts_model}")
            tts_file = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False).name
            with open(tts_file, 'wb') as f:
                f.write(tts_response.content)
            probe_cmd = [self.ffmpeg_path, "-i", tts_file, "-f", "null", "-"]
            result = subprocess.run(probe_cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
            duration_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
            if duration_match:
                h, m, s = duration_match.groups()
                hook_duration = int(h) * 3600 + int(m) * 60 + float(s) + 0.5
            else:
                hook_duration = 3.0
        else:
            self.log("  ⊘ Hook skipped; Gemini TTS API key empty")
            return 0
        progress_callback(0.2)
        
        # Format hook text
        hook_upper = hook_text.upper()
        words = hook_upper.split()
        
        lines = []
        current_line = []
        for word in words:
            current_line.append(word)
            if len(current_line) >= 3:
                lines.append(' '.join(current_line))
                current_line = []
        if current_line:
            lines.append(' '.join(current_line))
        
        # Get input video info
        probe_cmd = [self.ffmpeg_path, "-i", input_path]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
        
        fps_match = re.search(r'(\d+(?:\.\d+)?)\s*fps', result.stderr)
        fps = float(fps_match.group(1)) if fps_match else 30
        
        res_match = re.search(r'(\d{3,4})x(\d{3,4})', result.stderr)
        if res_match:
            width, height = int(res_match.group(1)), int(res_match.group(2))
        else:
            width, height = 1080, 1920
        
        progress_callback(0.3)
        
        # Create hook video in our temp directory
        hook_video = str(self.temp_dir / f"hook_{int(time.time() * 1000)}.mp4")
        
        # Use a simpler approach: create static image with text, then combine with audio
        # This avoids complex FFmpeg filter escaping issues
        
        # First, create a simple background video from first frame using GPU/CPU encoder
        bg_video = str(self.temp_dir / f"hook_bg_{int(time.time() * 1000)}.mp4")
        
        encoder_args = self.get_video_encoder_args()
        bg_cmd = [
            self.ffmpeg_path, "-y",
            "-i", input_path,
            "-vf", f"trim=0:0.04,loop=loop=-1:size=1:start=0,setpts=N/{fps}/TB",
            "-t", str(hook_duration),
            *encoder_args,
            "-r", str(fps),
            "-s", f"{width}x{height}",
            "-pix_fmt", "yuv420p",
            "-an",
            bg_video
        ]
        
        self.log_ffmpeg_command(bg_cmd, "Create Hook Background")
        result = self._run_ffmpeg_subprocess(bg_cmd)
        if result.returncode != 0:
            self.log(f"Failed to create background video: {result.stderr}")
            raise Exception("Failed to create background video")
        
        # Verify background video was created successfully
        if not os.path.exists(bg_video) or os.path.getsize(bg_video) < 1000:
            raise Exception("Background video was not created properly")
        
        # === Render hook overlay using PIL (supports user-customized font, colors, corners) ===
        from PIL import Image, ImageDraw, ImageFont

        style = self.hook_style_settings or {}
        font_size_frac = float(style.get("font_size", 0.044))
        font_color_hex = style.get("font_color", "#247BA0")
        bg_color_hex = style.get("bg_color", "#FFFFFF")
        corner_radius = int(style.get("corner_radius", 0))
        pos_x = float(style.get("position_x", 0.5))
        pos_y = float(style.get("position_y", 0.333))
        user_font_path = style.get("font_path") or ""

        # Resolve font path with sensible fallbacks
        font_candidates = [user_font_path, self._find_system_font_bold()]
        pil_font = None
        font_px = max(20, int(font_size_frac * width))
        for candidate in font_candidates:
            if not candidate or not os.path.exists(candidate):
                continue
            try:
                pil_font = ImageFont.truetype(candidate, font_px)
                self.log(f"  Hook font: {candidate} @ {font_px}px")
                break
            except Exception as e:
                self.log(f"  ⚠ Failed to load font {candidate}: {e}")
        if pil_font is None:
            self.log("  ⚠ No usable TTF font found, using PIL default (will look basic)")
            pil_font = ImageFont.load_default()

        font_color_rgb = _hex_to_rgb(font_color_hex)
        bg_color_rgb = _hex_to_rgb(bg_color_hex)

        # Per-line geometry
        padding = max(10, int(font_px * 0.22))
        line_spacing = max(6, int(font_px * 0.25))

        line_metrics = []
        for line in lines:
            try:
                bbox = pil_font.getbbox(line)
            except AttributeError:
                w, h = pil_font.getsize(line)
                bbox = (0, 0, w, h)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            line_metrics.append({
                "text": line,
                "bbox": bbox,
                "box_w": text_w + padding * 2,
                "box_h": text_h + padding * 2,
            })

        total_h = sum(m["box_h"] for m in line_metrics)
        if len(line_metrics) > 1:
            total_h += line_spacing * (len(line_metrics) - 1)

        center_x = int(pos_x * width)
        center_y = int(pos_y * height)
        block_top = center_y - total_h // 2

        # Compose the static overlay (transparent everywhere except the hook boxes)
        overlay_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay_img)

        cur_y = block_top
        for m in line_metrics:
            box_w = m["box_w"]
            box_h = m["box_h"]
            box_x1 = center_x - box_w // 2
            box_y1 = cur_y
            box_x2 = box_x1 + box_w
            box_y2 = box_y1 + box_h

            if corner_radius > 0 and hasattr(draw, "rounded_rectangle"):
                # Clamp radius so it never exceeds half the smaller dimension
                r = min(corner_radius, box_w // 2, box_h // 2)
                draw.rounded_rectangle(
                    [box_x1, box_y1, box_x2, box_y2],
                    radius=r,
                    fill=(*bg_color_rgb, 255),
                )
            else:
                draw.rectangle(
                    [box_x1, box_y1, box_x2, box_y2],
                    fill=(*bg_color_rgb, 255),
                )

            # PIL draws text at the top-left of the glyph bounding box;
            # subtract bbox[0]/[1] so the glyphs sit cleanly inside the padding.
            text_x = box_x1 + padding - m["bbox"][0]
            text_y = box_y1 + padding - m["bbox"][1]
            draw.text(
                (text_x, text_y),
                m["text"],
                font=pil_font,
                fill=(*font_color_rgb, 255),
            )

            cur_y = box_y2 + line_spacing

        overlay_png = str(self.temp_dir / f"hook_overlay_{int(time.time() * 1000)}.png")
        overlay_img.save(overlay_png, "PNG")
        progress_callback(0.4)

        # Composite overlay on the (frozen) background video in one FFmpeg pass
        overlay_video = str(self.temp_dir / f"hook_overlay_video_{int(time.time() * 1000)}.mp4")
        encoder_args = self.get_video_encoder_args()
        overlay_cmd = [
            self.ffmpeg_path, "-y",
            "-i", bg_video,
            "-i", overlay_png,
            "-filter_complex", "[0:v][1:v]overlay=0:0[v]",
            "-map", "[v]",
            *encoder_args,
            "-pix_fmt", "yuv420p",
            "-an",
            overlay_video,
        ]
        self.log_ffmpeg_command(overlay_cmd, "Composite Hook Overlay (PIL)")
        result = self._run_ffmpeg_subprocess(overlay_cmd)
        if result.returncode != 0:
            self.log(f"Failed to composite hook overlay: {result.stderr}")
            raise Exception("Failed to composite hook overlay video")

        if not os.path.exists(overlay_video) or os.path.getsize(overlay_video) < 1000:
            raise Exception("Hook overlay video was not created properly")

        progress_callback(0.55)

        # Both names point at the same file so the rest of the pipeline (audio mux,
        # cleanup) keeps working without further changes.
        current_video = overlay_video
        reencoded_video = overlay_video

        
        # Finally, add audio to re-encoded video
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", reencoded_video,
            "-i", tts_file,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-ac", "2",
            "-shortest",
            hook_video
        ]
        
        # Hook creation is 30-60%
        self.run_ffmpeg_with_progress(cmd, hook_duration, 
            lambda p: progress_callback(0.3 + p * 0.3))
        
        # Re-encode main video (60-80%) using GPU/CPU encoder
        progress_callback(0.6)
        main_reencoded = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
        
        # Get main video duration
        probe_cmd = [self.ffmpeg_path, "-i", input_path, "-f", "null", "-"]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
        duration_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
        main_duration = 60
        if duration_match:
            h, m, s = duration_match.groups()
            main_duration = int(h) * 3600 + int(m) * 60 + float(s)
        
        encoder_args = self.get_video_encoder_args()
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", input_path,
            *encoder_args,
            "-r", str(fps),
            "-s", f"{width}x{height}",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-ac", "2",
            "-progress", "pipe:1",
            main_reencoded
        ]
        
        self.log_ffmpeg_command(cmd, "Re-encode Main Video for Hook Concat")
        self.run_ffmpeg_with_progress(cmd, main_duration,
            lambda p: progress_callback(0.6 + p * 0.2))
        
        # Concatenate (80-100%)
        progress_callback(0.8)
        concat_list = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False).name
        with open(concat_list, 'w') as f:
            f.write(f"file '{hook_video.replace(chr(92), '/')}'\n")
            f.write(f"file '{main_reencoded.replace(chr(92), '/')}'\n")
        
        cmd = [
            self.ffmpeg_path, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
        
        if result.returncode != 0:
            # Fallback to filter_complex using GPU/CPU encoder
            encoder_args = self.get_video_encoder_args()
            cmd = [
                self.ffmpeg_path, "-y",
                "-i", hook_video,
                "-i", main_reencoded,
                "-filter_complex",
                "[0:v:0][0:a:0][1:v:0][1:a:0]concat=n=2:v=1:a=1[outv][outa]",
                "-map", "[outv]",
                "-map", "[outa]",
                *encoder_args,
                "-c:a", "aac",
                "-b:a", "192k",
                "-progress", "pipe:1",
                output_path
            ]
            self.log_ffmpeg_command(cmd, "Concat Hook (filter_complex fallback - old)")
            total_duration = hook_duration + main_duration
            self.run_ffmpeg_with_progress(cmd, total_duration,
                lambda p: progress_callback(0.8 + p * 0.2))
        else:
            progress_callback(1.0)
        
        # Cleanup
        for path in (tts_file, hook_video, main_reencoded, concat_list,
                     bg_video, overlay_video, overlay_png):
            try:
                if path and os.path.exists(path) and "cache\\tts" not in path and "cache/tts" not in path.replace("\\", "/"):
                    os.unlink(path)
            except Exception:
                pass
        
        return hook_duration

    def add_captions_api_with_progress(self, input_path: str, output_path: str, audio_source: str = None, time_offset: float = 0, progress_callback=None):
        """Add CapCut-style captions using OpenAI Whisper API with progress"""
        
        if progress_callback:
            progress_callback(0.1)
        
        # Use audio_source if provided, otherwise use input_path
        transcribe_source = audio_source if audio_source else input_path
        
        # Extract audio from video
        audio_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", transcribe_source,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            audio_file
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
        
        if result.returncode != 0:
            self.log(f"  Warning: Audio extraction failed")
            import shutil
            shutil.copy(input_path, output_path)
            return
        
        if progress_callback:
            progress_callback(0.2)
        
        # Check if audio file exists
        if not os.path.exists(audio_file) or os.path.getsize(audio_file) < 1000:
            self.log(f"  Warning: Audio file too small or missing")
            import shutil
            shutil.copy(input_path, output_path)
            if os.path.exists(audio_file):
                os.unlink(audio_file)
            return
        
        # Get audio duration for token reporting
        probe_cmd = [self.ffmpeg_path, "-i", audio_file, "-f", "null", "-"]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
        duration_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
        audio_duration = 0
        if duration_match:
            h, m, s = duration_match.groups()
            audio_duration = int(h) * 3600 + int(m) * 60 + float(s)
            self.report_tokens(0, 0, audio_duration, 0)
        
        if progress_callback:
            progress_callback(0.3)
        
        try:
            transcript = self._whisper_transcribe_words(audio_file)
        except Exception:
            os.unlink(audio_file)
            raise
        
        os.unlink(audio_file)
        
        if progress_callback:
            progress_callback(0.5)
        
        # Create ASS subtitle file
        ass_file = tempfile.NamedTemporaryFile(mode='w', suffix='.ass', delete=False, encoding='utf-8').name
        event_count = self.create_ass_subtitle_capcut(transcript, ass_file, time_offset)
        self.log(f"  ASS events: {event_count}")
        if event_count <= 0:
            os.unlink(ass_file)
            raise Exception("Subtitle transcription produced 0 ASS events")
        
        if progress_callback:
            progress_callback(0.6)
        
        # Burn subtitles into video using GPU/CPU encoder
        ass_path_escaped = ass_file.replace('\\', '/').replace(':', '\\:')
        fonts_dir_escaped = str(Path(__file__).resolve().parent / "fonts").replace('\\', '/').replace(':', '\\:')
        
        # Get video duration for progress
        probe_cmd = [self.ffmpeg_path, "-i", input_path, "-f", "null", "-"]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
        duration_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
        video_duration = 60
        if duration_match:
            h, m, s = duration_match.groups()
            video_duration = int(h) * 3600 + int(m) * 60 + float(s)
        
        encoder_args = self.get_video_encoder_args()
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", input_path,
            "-vf", f"ass='{ass_path_escaped}':fontsdir='{fonts_dir_escaped}'",
            *encoder_args,
            "-c:a", "copy",
            "-progress", "pipe:1",
            output_path
        ]
        
        self.log_ffmpeg_command(cmd, "Burn Captions (old function)")
        
        # Caption burn is 60-100%
        self.run_ffmpeg_with_progress(cmd, video_duration,
            lambda p: progress_callback(0.6 + p * 0.4) if progress_callback else None)
        self.log("  Subtitle burn OK")
        
        os.unlink(ass_file)

    def add_watermark_with_progress(self, input_path: str, output_path: str, progress_callback):
        """Add watermark overlay to video with progress tracking"""
        
        watermark_path = self.watermark_settings.get("image_path", "")
        if not watermark_path or not Path(watermark_path).exists():
            self.log("  Warning: Watermark image not found, skipping")
            import shutil
            shutil.copy(input_path, output_path)
            return
        
        progress_callback(0.1)
        
        # Get video dimensions
        probe_cmd = [self.ffmpeg_path, "-i", input_path]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
        
        res_match = re.search(r'(\d{3,4})x(\d{3,4})', result.stderr)
        if res_match:
            video_width, video_height = int(res_match.group(1)), int(res_match.group(2))
        else:
            video_width, video_height = 1080, 1920
        
        progress_callback(0.2)
        
        # Calculate watermark size and position
        scale = self.watermark_settings.get("scale", 0.15)
        pos_x = self.watermark_settings.get("position_x", 0.85)
        pos_y = self.watermark_settings.get("position_y", 0.05)
        opacity = self.watermark_settings.get("opacity", 0.8)
        
        # Calculate watermark width in pixels
        watermark_width = int(video_width * scale)
        
        # Calculate position in pixels
        x_pixels = int(pos_x * video_width)
        y_pixels = int(pos_y * video_height)
        
        # Escape watermark path for FFmpeg (Windows paths)
        watermark_escaped = watermark_path.replace('\\', '/').replace(':', '\\:')
        
        # Build FFmpeg overlay filter with proper opacity control
        # Scale watermark, apply opacity via colorchannelmixer, then overlay
        filter_complex = (
            f"[1:v]scale={watermark_width}:-1,format=rgba,"
            f"colorchannelmixer=aa={opacity}[wm];"
            f"[0:v][wm]overlay={x_pixels}:{y_pixels}"
        )
        
        progress_callback(0.3)
        
        # Get video duration for progress
        duration_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
        video_duration = 60
        if duration_match:
            h, m, s = duration_match.groups()
            video_duration = int(h) * 3600 + int(m) * 60 + float(s)
        
        # Apply watermark using GPU/CPU encoder
        encoder_args = self.get_video_encoder_args()
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", input_path,
            "-i", watermark_path,
            "-filter_complex", filter_complex,
            *encoder_args,
            "-pix_fmt", "yuv420p",  # Ensure compatibility
            "-c:a", "copy",
            "-movflags", "+faststart",  # Enable streaming
            "-progress", "pipe:1",
            output_path
        ]
        
        self.log_ffmpeg_command(cmd, "Apply Watermark")
        
        # Watermark application is 30-100%
        self.run_ffmpeg_with_progress(cmd, video_duration,
            lambda p: progress_callback(0.3 + p * 0.7))
        
        if not Path(output_path).exists():
            raise Exception("Failed to apply watermark")

    def add_credit_watermark_with_progress(self, input_path: str, output_path: str, progress_callback):
        """Add credit text watermark (channel name) to video with progress tracking"""
        
        if not self.channel_name:
            self.log("  Warning: No channel name available, skipping credit")
            import shutil
            shutil.copy(input_path, output_path)
            return
        
        progress_callback(0.1)
        
        # Get video dimensions
        probe_cmd = [self.ffmpeg_path, "-i", input_path]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
        
        res_match = re.search(r'(\d{3,4})x(\d{3,4})', result.stderr)
        if res_match:
            video_width, video_height = int(res_match.group(1)), int(res_match.group(2))
        else:
            video_width, video_height = 1080, 1920
        
        progress_callback(0.2)
        
        # Get credit watermark settings
        size = self.credit_watermark_settings.get("size", 0.03)
        pos_x = self.credit_watermark_settings.get("position_x", 0.5)
        pos_y = self.credit_watermark_settings.get("position_y", 0.95)
        opacity = self.credit_watermark_settings.get("opacity", 0.7)
        
        font_size = max(22, int(video_height * size))
        
        # Calculate position in pixels
        x_pixels = int(pos_x * video_width)
        y_pixels = int(pos_y * video_height)
        
        # Prepare credit text
        credit_text = f"sc: {self.channel_name}"
        # Escape special characters for FFmpeg drawtext
        credit_text_escaped = credit_text.replace("'", "'\\''").replace(":", "\\:")
        
        # Build FFmpeg drawtext filter
        # Use fontfile for portable FFmpeg (avoids fontconfig dependency)
        # Try to find a system font, fallback to built-in if not available
        font_file = None
        if sys.platform == "win32":
            # Windows fonts directory
            windows_fonts = [
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/segoeui.ttf",
                "C:/Windows/Fonts/tahoma.ttf",
            ]
            for font in windows_fonts:
                if Path(font).exists():
                    font_file = font.replace("\\", "/").replace(":", "\\:")
                    break
        
        # Build filter string
        if font_file:
            filter_str = (
                f"drawtext=fontfile='{font_file}':"
                f"text='{credit_text_escaped}':"
                f"fontsize={font_size}:"
                f"fontcolor=white@{opacity}:"
                f"borderw=3:"
                f"bordercolor=black@0.75:"
                f"x={x_pixels}:"
                f"y={y_pixels}-(text_h/2)"
            )
        else:
            # Fallback without fontfile (may cause fontconfig warning but should still work)
            filter_str = (
                f"drawtext=text='{credit_text_escaped}':"
                f"fontsize={font_size}:"
                f"fontcolor=white@{opacity}:"
                f"borderw=3:"
                f"bordercolor=black@0.75:"
                f"x={x_pixels}:"
                f"y={y_pixels}-(text_h/2)"
            )
        
        progress_callback(0.3)
        
        # Get video duration for progress
        duration_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
        video_duration = 60
        if duration_match:
            h, m, s = duration_match.groups()
            video_duration = int(h) * 3600 + int(m) * 60 + float(s)
        
        # Apply credit text using GPU/CPU encoder
        encoder_args = self.get_video_encoder_args()
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", input_path,
            "-vf", filter_str,
            *encoder_args,
            "-c:a", "copy",
            "-movflags", "+faststart",
            "-progress", "pipe:1",
            output_path
        ]
        
        self.log_ffmpeg_command(cmd, "Apply Credit Watermark")
        
        # Credit application is 30-100%
        self.run_ffmpeg_with_progress(cmd, video_duration,
            lambda p: progress_callback(0.3 + p * 0.7))
        
        if not Path(output_path).exists():
            raise Exception("Failed to apply credit watermark")

    def process_selected_highlights(self, url: str, selected_highlights: list, 
                                   session_dir: Path, add_captions: bool = True, 
                                   add_hook: bool = True):
        """Phase 2: Download video sections and process selected highlights
        
        Args:
            url: YouTube video URL (for downloading sections)
            selected_highlights: List of highlight dicts to process
            session_dir: Session directory for output
            add_captions: Whether to add captions
            add_hook: Whether to add hook
        """
        if not selected_highlights:
            raise Exception("No highlights selected for processing")
        
        self.log(f"\n[Processing {len(selected_highlights)} selected clips]")
        
        # Ensure session_dir is Path object
        if isinstance(session_dir, str):
            session_dir = Path(session_dir)
        
        # Update output_dir to session clips folder
        clips_dir = session_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        
        # Update temp_dir to session-specific temp
        self.temp_dir = session_dir / "_temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Process each selected clip
        total_clips = len(selected_highlights)
        for i, highlight in enumerate(selected_highlights, 1):
            if self.is_cancelled():
                return
            
            # Step A: Download video section for this clip
            self.set_progress(f"Clip {i}/{total_clips}: Downloading video section...", 
                            0.05 + (0.9 * (i - 1) / total_clips))
            self.log(f"\n[Clip {i}/{total_clips}] Downloading: {highlight.get('title', 'Untitled')}")
            
            section_filename = f"section_{i:03d}.mp4"
            section_path = str(self.temp_dir / section_filename)
            
            try:
                video_path = self.download_video_section(
                    url, 
                    highlight["start_time"], 
                    highlight["end_time"],
                    section_path
                )
            except Exception as e:
                self.log(f"  ✗ Failed to download section: {e}")
                raise Exception(
                    f"Failed to download video section for clip {i}!\n\n"
                    f"Title: {highlight.get('title', 'Untitled')}\n"
                    f"Time: {highlight['start_time']} → {highlight['end_time']}\n\n"
                    f"Error: {str(e)}"
                )
            
            # Step B: Process the downloaded section
            # Create clip-specific folder
            clip_folder = clips_dir / f"clip_{i:03d}"
            clip_folder.mkdir(parents=True, exist_ok=True)
            
            # Temporarily override output_dir for this clip
            original_output_dir = self.output_dir
            self.output_dir = clip_folder.parent
            
            try:
                # Pass pre_cut=True since we downloaded the section already
                self.process_clip(video_path, highlight, i, total_clips, 
                                add_captions=add_captions, add_hook=add_hook,
                                pre_cut=True)
            finally:
                # Restore original output_dir
                self.output_dir = original_output_dir
            
            # Clean up section file after processing
            try:
                if Path(video_path).exists():
                    os.remove(video_path)
            except Exception:
                pass
        
        # Cleanup temp files
        self.set_progress("Cleaning up...", 0.95)
        self.cleanup()
        
        # Update session status to completed
        session_data_file = session_dir / "session_data.json"
        if session_data_file.exists():
            with open(session_data_file, "r", encoding="utf-8") as f:
                session_data = json.load(f)
            
            session_data["status"] = "completed"
            session_data["completed_at"] = datetime.now().isoformat()
            session_data["clips_processed"] = total_clips
            
            with open(session_data_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
        
        self.set_progress("Complete!", 1.0)
        self.log(f"\n✅ Created {total_clips} clips in: {clips_dir}")
