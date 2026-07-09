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

from clipper_shared import SUBPROCESS_FLAGS, _hex_to_rgb
from clipper_base import ClipperBase
from utils.logger import debug_log


class ExportMixin(ClipperBase):
    def _render_size(self):
        try:
            width, height = (int(part) for part in getattr(self, "output_resolution", "720:1280").split(":"))
            return width, height
        except Exception:
            return (1280, 720) if getattr(self, "screen_size", "9:16") == "16:9" else (720, 1280)

    def _scale_from_preview_width(self, value: float, preview_px: float, width: int, minimum: int = 1) -> int:
        return max(minimum, int(float(value) * preview_px / 340 * width))

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
            
            debug_log(f"clip_progress: {status} (overall: {overall*100:.1f}%)")
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
                current_output = final_file
            
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
            "virality_score": int(highlight.get("virality_score", 5) or 5),
        }
        
        with open(clip_dir / "data.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        # Extract thumbnail from best moment of the clip (1 second in)
        try:
            thumbnail_path = clip_dir / "thumbnail.jpg"
            master_path = clip_dir / "master.mp4"
            if master_path.exists() and not thumbnail_path.exists():
                seek_time = min(1.0, highlight["duration_seconds"] * 0.1)
                thumb_cmd = [
                    self.ffmpeg_path, "-y",
                    "-ss", str(seek_time),
                    "-i", str(master_path),
                    "-frames:v", "1",
                    "-q:v", "3",
                    str(thumbnail_path)
                ]
                import subprocess as _sp
                _sp.run(thumb_cmd, capture_output=True, timeout=30)
                if thumbnail_path.exists():
                    self.log(f"  ✓ Thumbnail extracted: {thumbnail_path.name}")
        except Exception as e:
            self.log(f"  ⚠ Thumbnail extraction failed (non-fatal): {e}")

    def add_hook(self, input_path: str, hook_text: str, output_path: str) -> float:
        return self.add_hook_with_progress(input_path, hook_text, output_path, lambda _: None)

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
        font = str(style.get("font") or style.get("font_family") or "Plus Jakarta Sans").replace(",", " ")
        width, height = self._render_size()
        
        size_val = float(style.get("size") or 0.04)
        if size_val < 20:
            size = self._scale_from_preview_width(size_val, 500, width, minimum=max(12, int(12 / 340 * width)))
        else:
            size = int(size_val / 1080 * width) if width != 1080 else int(size_val)
            
        pos_x_ratio = float(style.get("position_x", 0.5))
        pos_y_ratio = float(style.get("position_y", 0.85))
        pos_x = int(pos_x_ratio * width)
        pos_y = int(pos_y_ratio * height)
        
        alignment = 5 # Middle-center anchor for precise \pos placement
            
        # Colors (ASS is &HAABBGGRR)
        color_hex = str(style.get("color") or "#ffffff").strip("#")
        bg_color_hex = str(style.get("bg_color") or "#000000").strip("#")
        bg_opacity = float(style.get("bg_opacity", 0.8))
        # Always use box if opacity > 0, ignoring old bg_box false flag
        bg_box = True if bg_opacity > 0 else False
        font_weight = int(style.get("font_weight", 800))
        
        if len(color_hex) == 6:
            r, g, b = color_hex[0:2], color_hex[2:4], color_hex[4:6]
            primary_colour = f"&H00{b}{g}{r}"
        else:
            primary_colour = "&H00FFFFFF"

        if len(bg_color_hex) == 6:
            r, g, b = bg_color_hex[0:2], bg_color_hex[2:4], bg_color_hex[4:6]
            alpha_hex = f"{int((1.0 - bg_opacity) * 255):02X}"
            back_colour = f"&H{alpha_hex}{b}{g}{r}"
        else:
            back_colour = "&H80000000"

        # BorderStyle: 1=Outline, 3=Opaque Box
        border_style = 1 # Force outline, no box
        outline = max(1, int(size * 0.05)) # Thin outline
        bold = -1 if font_weight >= 700 else 0

        ass_content = f"""[Script Info]
Title: Auto-generated captions
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,{back_colour},{bold},0,0,0,100,100,0,0,{border_style},{outline},0,{alignment},0,0,0,1

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
                chunk_start = chunk[0]['start']
                chunk_end = chunk[-1]['end']
                
                for i, word in enumerate(chunk):
                    # Event start is either the start of the chunk (for first word) or the end of the previous word
                    event_start = chunk_start if i == 0 else chunk[i-1]['end']
                    # Event end is the end of the current word, or the end of the chunk (for last word)
                    event_end = word['end'] if i < len(chunk) - 1 else chunk_end
                    
                    # Ensure event duration is at least 0.01s to avoid ASS errors
                    if event_end - event_start < 0.01:
                        event_end = event_start + 0.01
                    
                    # Format text: highlight the current word
                    text_parts = []
                    for j, w in enumerate(chunk):
                        if i == j:
                            # Active word: Blue/Custom color
                            text_parts.append(f"{{\\c{primary_colour}}}{w['text']}{{\\c&HFFFFFF&}}")
                        else:
                            # Inactive word: White
                            text_parts.append(f"{{\\c&HFFFFFF&}}{w['text']}")
                    
                    event_text = " ".join(text_parts)
                    
                    events.append({
                        'start': self.format_time(event_start + time_offset),
                        'end': self.format_time(event_end + time_offset),
                        'text': event_text
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
        text_transform = str(style.get("text_transform", "none")).lower()
        for event in events:
            raw_text = str(event['text']).replace('\n', ' ')
            # Apply transform outside tags or just transform words
            def _transform_word(match):
                word = match.group(0)
                if word.startswith("{\\c"):
                    return word
                if text_transform == "uppercase":
                    return word.upper()
                elif text_transform == "lowercase":
                    return word.lower()
                elif text_transform == "capitalize":
                    return word.title()
                return word
            
            # Split into tag / text tokens cleanly
            tokens = re.split(r'(\{\\c[^}]+\})', raw_text)
            transformed = "".join(_transform_word(re.match(r'.*', t)) for t in tokens)
            ass_content += f"Dialogue: 0,{event['start']},{event['end']},Default,,0,0,0,,{{\\pos({pos_x},{pos_y})}}{transformed}\n"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        return len(events)

    async def _generate_edge_tts_async(self, hook_text: str, output_path: str) -> None:
        import edge_tts
        voice = getattr(self, "tts_voice", "id-ID-ArdiNeural") or "id-ID-ArdiNeural"
        communicate = edge_tts.Communicate(hook_text, voice)
        await communicate.save(output_path)

    def _generate_edge_tts(self, hook_text: str) -> str:
        cache_root = Path(os.environ.get("KLIPKLOP_CACHE_DIR") or self.output_dir.parent / "cache") / "tts"
        cache_root.mkdir(parents=True, exist_ok=True)
        voice = getattr(self, "tts_voice", "id-ID-ArdiNeural") or "id-ID-ArdiNeural"
        cache_file = cache_root / f"{hashlib.sha1((voice + hook_text).encode('utf-8')).hexdigest()}.mp3"
        if cache_file.exists():
            self.log("  ✓ Using cached hook TTS")
            return str(cache_file)
        import asyncio
        asyncio.run(self._generate_edge_tts_async(hook_text, str(cache_file)))
        return str(cache_file)

    def add_hook_with_progress(self, input_path: str, hook_text: str, output_path: str, progress_callback) -> float:
        """Add hook scene as a title overlay for 4 seconds"""
        
        progress_callback(0.1)
        hook_duration = 4.0
        
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
        
        # === Render hook overlay using PIL ===
        from PIL import Image, ImageDraw, ImageFont

        style = self.hook_style_settings or {}
        font_size_frac = float(style.get("font_size", 0.05))
        font_color_hex = style.get("text_color") or style.get("font_color") or "#FFD700"
        pos_x = float(style.get("position_x", 0.5))
        pos_y = float(style.get("position_y", 0.2))
        user_font_path = style.get("font_path") or ""

        # Resolve font path with sensible fallbacks
        root = Path(__file__).resolve().parent
        font_family = str(style.get("font_family") or "")
        family_fonts = {
            "Plus Jakarta Sans": root / "fonts" / "PlusJakartaSans.ttf",
            "Poppins": root / "fonts" / "Poppins-Bold.ttf",
            "Super Kidpop": root / "fonts" / "SuperKidpop.ttf",
            "Capo Sfogliato": root / "fonts" / "CapoSfogliato.ttf",
        }
        font_candidates = [user_font_path, str(family_fonts.get(font_family, "")), self._find_system_font_bold()]
        pil_font = None
        font_px = self._scale_from_preview_width(font_size_frac, 500, width, minimum=max(12, int(12 / 340 * width)))
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

        # Compose the static overlay
        overlay_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay_img)

        cur_y = block_top
        stroke_width = max(1, int(font_px * 0.05))
        shadow_offset = max(2, int(font_px * 0.08))

        for m in line_metrics:
            box_w = m["box_w"]
            box_h = m["box_h"]
            box_x1 = center_x - box_w // 2
            box_y1 = cur_y
            
            text_x = box_x1 + padding - m["bbox"][0]
            text_y = box_y1 + padding - m["bbox"][1]

            # Draw Shadow
            draw.text(
                (text_x, text_y + shadow_offset),
                m["text"],
                font=pil_font,
                fill=(0, 0, 0, 180),
                stroke_width=stroke_width,
                stroke_fill=(0, 0, 0, 180),
            )

            # Draw Main Text with Stroke
            draw.text(
                (text_x, text_y),
                m["text"],
                font=pil_font,
                fill=(*font_color_rgb, 255),
                stroke_width=stroke_width,
                stroke_fill=(0, 0, 0, 255),
            )

            cur_y = box_y1 + box_h + line_spacing

        import time
        overlay_png = str(self.temp_dir / f"hook_overlay_{int(time.time() * 1000)}.png")
        overlay_img.save(overlay_png, "PNG")
        progress_callback(0.4)

        # Composite overlay on video
        encoder_args = self.get_video_encoder_args()
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", input_path,
            "-i", overlay_png,
            "-filter_complex", f"[0:v][1:v]overlay=0:0:enable='between(t,0,{hook_duration})'[v]",
            "-map", "[v]",
            "-map", "0:a",
            *encoder_args,
            "-c:a", "copy",
            "-progress", "pipe:1",
            output_path
        ]
        
        self.log_ffmpeg_command(cmd, "Apply Hook Title")
        
        # Get duration for progress
        duration_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
        video_duration = 60
        if duration_match:
            h, m, s = duration_match.groups()
            video_duration = int(h) * 3600 + int(m) * 60 + float(s)
            
        self.run_ffmpeg_with_progress(cmd, video_duration, lambda p: progress_callback(0.4 + p * 0.6))
        
        if not os.path.exists(output_path):
            raise Exception("Failed to apply hook title video")
            
        try:
            os.unlink(overlay_png)
        except Exception:
            pass
            
        progress_callback(1.0)
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
        finally:
            try:
                os.unlink(audio_file)
            except OSError:
                pass
        
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
        placeholder = not watermark_path or not Path(watermark_path).exists()
        if placeholder:
            self.log("  Watermark image not found, using LOGO placeholder")
        
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
        
        watermark_width = self._scale_from_preview_width(scale, 150, video_width, minimum=8)
        
        # Calculate position in pixels
        x_pixels = int(pos_x * video_width)
        y_pixels = int(pos_y * video_height)
        
        if placeholder:
            box_size = watermark_width
            font_size = max(8, int(box_size * 0.16))
            filter_complex = (
                f"drawbox=x='(w*{pos_x})-{box_size}/2':y='(h*{pos_y})-{box_size}/2':"
                f"w={box_size}:h={box_size}:color=black@{opacity}:t=fill,"
                f"drawtext=text='LOGO':fontcolor=white@{opacity}:fontsize={font_size}:"
                f"x='(w*{pos_x})-(text_w/2)':y='(h*{pos_y})-(text_h/2)'"
            )
        else:
            filter_complex = (
                f"[1:v]scale={watermark_width}:-1,format=rgba,"
                f"colorchannelmixer=aa={opacity}[wm];"
                f"[0:v][wm]overlay=x='(main_w*{pos_x})-(overlay_w/2)':y='(main_h*{pos_y})-(overlay_h/2)'"
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
        cmd = [self.ffmpeg_path, "-y", "-i", input_path]
        if not placeholder:
            cmd.extend(["-i", watermark_path])
        cmd.extend([
            "-filter_complex" if not placeholder else "-vf", filter_complex,
            *encoder_args,
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            "-progress", "pipe:1",
            output_path
        ])
        
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
        color = str(self.credit_watermark_settings.get("color", "#FFFFFF")).lstrip("#") or "FFFFFF"
        
        font_size = self._scale_from_preview_width(size, 320, video_width, minimum=max(10, int(10 / 340 * video_width)))
        
        # Calculate position in pixels
        x_pixels = int(pos_x * video_width)
        y_pixels = int(pos_y * video_height)
        
        # Prepare credit text
        channel_display = self.channel_name
        if not channel_display or channel_display == "{channel}":
            channel_display = "Local Video" # Fallback for local files without youtube channel
            
        credit_text = str(self.credit_watermark_settings.get("text") or "sc : {channel}").replace("{channel}", channel_display)
        # Escape special characters for FFmpeg drawtext
        credit_text_escaped = credit_text.replace("\\", "\\\\").replace("'", "'\\''").replace(":", "\\:")
        
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
        
        shadow_x = max(1, int(1 / 340 * video_width))
        shadow_y = max(1, int(1 / 340 * video_width))

        # Build filter string
        if font_file:
            filter_str = (
                f"drawtext=fontfile='{font_file}':"
                f"text='{credit_text_escaped}':"
                f"fontsize={font_size}:"
                f"fontcolor=0x{color}@{opacity}:"
                f"shadowcolor=0x000000@0.5:shadowx={shadow_x}:shadowy={shadow_y}:"
                f"x=(w*{pos_x})-(text_w/2):"
                f"y=(h*{pos_y})-(text_h/2)"
            )
        else:
            # Fallback without fontfile (may cause fontconfig warning but should still work)
            filter_str = (
                f"drawtext=text='{credit_text_escaped}':"
                f"fontsize={font_size}:"
                f"fontcolor=0x{color}@{opacity}:"
                f"shadowcolor=0x000000@0.5:shadowx={shadow_x}:shadowy={shadow_y}:"
                f"x=(w*{pos_x})-(text_w/2):"
                f"y=(h*{pos_y})-(text_h/2)"
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
