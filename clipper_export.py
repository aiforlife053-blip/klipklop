import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

from clipper_shared import SUBPROCESS_FLAGS, TimedTranscript, _hex_to_rgb, validate_timed_transcript
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
        return max(minimum, int(round(float(value) * preview_px / 340 * width)))

    def _wrap_preview_text(self, text: str, font, max_width: int) -> list[str]:
        words = str(text).split()
        if not words:
            return [""]
        lines = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            try:
                candidate_width = font.getlength(candidate)
            except AttributeError:
                candidate_width = font.getbbox(candidate)[2]
            if candidate_width <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _probe_render_input(self, input_path: str):
        result = subprocess.run(
            [self.ffmpeg_path, "-i", input_path],
            capture_output=True,
            text=True,
            creationflags=SUBPROCESS_FLAGS,
        )
        dimensions = re.search(r'(\d{3,4})x(\d{3,4})', result.stderr)
        duration_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
        width, height = (int(dimensions.group(1)), int(dimensions.group(2))) if dimensions else self._render_size()
        duration = 60.0
        if duration_match:
            hours, minutes, seconds = duration_match.groups()
            duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        return width, height, duration

    def _has_audio_stream(self, input_path: str):
        result = subprocess.run(
            [self.ffmpeg_path, "-i", input_path],
            capture_output=True,
            text=True,
            creationflags=SUBPROCESS_FLAGS,
        )
        return "Audio:" in result.stderr

    def _create_hook_overlay(self, hook_text: str, width: int, height: int, output_path: Path):
        from PIL import Image, ImageDraw, ImageFont

        style = self.hook_style_settings or {}
        font_size_frac = float(style.get("font_size", 0.05))
        root = Path(__file__).resolve().parent
        font_family = str(style.get("font_family") or "Plus Jakarta Sans")
        font_weight = max(100, min(900, int(style.get("font_weight") or 800)))
        family_fonts = {
            "Plus Jakarta Sans": root / "fonts" / "PlusJakartaSans.ttf",
            "Poppins": root / "fonts" / ("Poppins-Bold.ttf" if font_weight >= 600 else "Poppins-Regular.ttf"),
        }
        font_candidates = [str(family_fonts.get(font_family, family_fonts["Plus Jakarta Sans"])), str(family_fonts["Plus Jakarta Sans"])]
        font_px = max(1, int(max(16, font_size_frac * 500) / 340 * width))
        font = None
        for candidate in font_candidates:
            if not candidate or not os.path.exists(candidate):
                continue
            try:
                font = ImageFont.truetype(candidate, font_px)
                if hasattr(font, "set_variation_by_axes") and "PlusJakartaSans" in Path(candidate).name:
                    font.set_variation_by_axes([max(200, min(800, font_weight))])
                break
            except Exception:
                continue
        if font is None:
            font = ImageFont.load_default()
        lines = self._wrap_preview_text(str(hook_text).upper(), font, int(width * 0.9))
        line_height = int(font_px * 1.2)
        total_height = line_height * len(lines)
        center_x = float(style.get("position_x", 0.5)) * width
        center_y = float(style.get("position_y", 0.2)) * height
        block_top = center_y - total_height / 2
        stroke_width = max(0, int(round(float(style.get("outline_thickness", 1.5)) / 340 * width)))
        text_color = _hex_to_rgb(str(style.get("text_color") or "#FFD700"))
        outline_color = _hex_to_rgb(str(style.get("outline_color") or "#000000"))
        shadow_y = max(1, int(round(3 / 340 * width)))
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for line_index, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)
            text_x = center_x - (bbox[2] - bbox[0]) / 2 - bbox[0]
            text_y = block_top + line_index * line_height - bbox[1]
            draw.text((text_x, text_y + shadow_y), line, font=font, fill=(0, 0, 0, 128), stroke_width=stroke_width, stroke_fill=(0, 0, 0, 128))
            draw.text((text_x, text_y), line, font=font, fill=(*text_color, 255), stroke_width=stroke_width, stroke_fill=(*outline_color, 255))
        overlay.save(output_path, "PNG")

    def _create_credit_overlay(self, width: int, height: int, output_path: Path):
        from PIL import Image, ImageDraw, ImageFilter, ImageFont

        settings = self.credit_watermark_settings or {}
        size = float(settings.get("size", 0.03))
        opacity = float(settings.get("opacity", 0.7))
        font_size = self._scale_from_preview_width(size, 320, width, minimum=max(10, int(round(10 / 340 * width))))
        font = ImageFont.truetype(str(Path(__file__).resolve().parent / "fonts" / "PlusJakartaSans.ttf"), font_size)
        if hasattr(font, "set_variation_by_axes"):
            font.set_variation_by_axes([600])
        channel = self.channel_name if self.channel_name and self.channel_name != "{channel}" else "Local Video"
        text = str(settings.get("text") or "sc : {channel}").replace("{channel}", channel)
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        shadow = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        shadow_draw = ImageDraw.Draw(shadow)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_x = float(settings.get("position_x", 0.5)) * width - (bbox[2] - bbox[0]) / 2 - bbox[0]
        text_y = float(settings.get("position_y", 0.95)) * height - (bbox[3] - bbox[1]) / 2 - bbox[1]
        shadow_draw.text((text_x, text_y + width / 340), text, font=font, fill=(0, 0, 0, int(255 * 0.5 * opacity)))
        overlay.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(3 / 340 * width)))
        draw.text((text_x, text_y), text, font=font, fill=(*_hex_to_rgb(str(settings.get("color") or "#FFFFFF")), int(255 * opacity)))
        overlay.save(output_path, "PNG")

    def _create_caption_ass(
        self,
        input_path: str,
        clip_dir: Path,
        transcript: TimedTranscript | None = None,
    ) -> Path | None:
        if transcript is not None:
            transcript = validate_timed_transcript(transcript, require_words=True)
        else:
            audio_file = clip_dir / "caption_audio.mp3"
            result = subprocess.run(
                [
                    self.ffmpeg_path,
                    "-y",
                    "-i",
                    input_path,
                    "-vn",
                    "-acodec",
                    "libmp3lame",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-b:a",
                    "32k",
                    str(audio_file),
                ],
                capture_output=True,
                text=True,
                creationflags=SUBPROCESS_FLAGS,
            )
            if result.returncode != 0 or not audio_file.exists() or audio_file.stat().st_size < 1000:
                audio_file.unlink(missing_ok=True)
                raise Exception("Caption audio extraction failed")
            try:
                transcript = self.transcribe_audio_with_timestamps(str(audio_file), require_words=True)
            finally:
                audio_file.unlink(missing_ok=True)
        ass_file = clip_dir / "captions.ass"
        event_count = self.create_ass_subtitle_capcut(transcript, str(ass_file), 0)
        if event_count <= 0:
            ass_file.unlink(missing_ok=True)
            raise Exception("Subtitle transcription produced 0 ASS events")
        self.log(f"  ASS events: {event_count}")
        return ass_file

    def _escape_filter_path(self, path: Path):
        return str(path).replace('\\', '/').replace(':', '\\:').replace("'", "\\'")

    def _build_composite_command(self, input_path: str, output_path: str, duration: float, audio_source=None, hook_overlay=None, ass_file=None, watermark_path=None, watermark_placeholder=False, credit_overlay=None):
        inputs = [input_path]
        audio_index = 0
        if audio_source and Path(audio_source).resolve() != Path(input_path).resolve():
            audio_index = len(inputs)
            inputs.append(str(audio_source))
        filters = ["[0:v]setpts=PTS-STARTPTS[v0]"]
        current = "v0"
        layer = 1
        if hook_overlay:
            input_index = len(inputs)
            inputs.append(str(hook_overlay))
            filters.append(f"[{input_index}:v]format=rgba[hook]")
            filters.append(f"[{current}][hook]overlay=0:0:enable='between(t,0,{max(1.0, min(10.0, float((self.hook_style_settings or {}).get('duration', 5.0)))):.3f})'[v{layer}]")
            current = f"v{layer}"
            layer += 1
        if ass_file:
            fonts_dir = self._escape_filter_path(Path(__file__).resolve().parent / "fonts")
            ass_path = self._escape_filter_path(Path(ass_file))
            filters.append(f"[{current}]ass='{ass_path}':fontsdir='{fonts_dir}'[v{layer}]")
            current = f"v{layer}"
            layer += 1
        if watermark_path:
            input_index = len(inputs)
            inputs.append(str(watermark_path))
            settings = self.watermark_settings or {}
            watermark_width = self._scale_from_preview_width(float(settings.get("scale", 0.15)), 150, self._render_size()[0], minimum=8)
            opacity = float(settings.get("opacity", 0.8))
            pos_x = float(settings.get("position_x", 0.85))
            pos_y = float(settings.get("position_y", 0.05))
            filters.append(f"[{input_index}:v]scale={watermark_width}:-1,format=rgba,colorchannelmixer=aa={opacity}[wm]")
            filters.append(f"[{current}][wm]overlay=x='(main_w*{pos_x})-(overlay_w/2)':y='(main_h*{pos_y})-(overlay_h/2)'[v{layer}]")
            current = f"v{layer}"
            layer += 1
        elif watermark_placeholder:
            settings = self.watermark_settings or {}
            box_size = self._scale_from_preview_width(float(settings.get("scale", 0.15)), 150, self._render_size()[0], minimum=8)
            opacity = float(settings.get("opacity", 0.8))
            pos_x = float(settings.get("position_x", 0.85))
            pos_y = float(settings.get("position_y", 0.05))
            font_size = max(8, int(box_size * 0.16))
            filters.append(f"[{current}]drawbox=x='(w*{pos_x})-{box_size}/2':y='(h*{pos_y})-{box_size}/2':w={box_size}:h={box_size}:color=black@{opacity}:t=fill,drawtext=text='LOGO':fontcolor=white@{opacity}:fontsize={font_size}:x='(w*{pos_x})-(text_w/2)':y='(h*{pos_y})-(text_h/2)'[v{layer}]")
            current = f"v{layer}"
            layer += 1
        if credit_overlay:
            input_index = len(inputs)
            inputs.append(str(credit_overlay))
            filters.append(f"[{input_index}:v]format=rgba[credit]")
            filters.append(f"[{current}][credit]overlay=0:0[v{layer}]")
            current = f"v{layer}"
        filters.append(f"[{current}]format=yuv420p[vout]")
        if audio_source:
            filters.append(f"[{audio_index}:a]asetpts=PTS-STARTPTS[aout]")
        cmd = [self.ffmpeg_path, "-y"]
        for media_input in inputs:
            cmd.extend(["-i", media_input])
        cmd.extend(["-filter_complex", ";".join(filters), "-map", "[vout]"])
        if audio_source:
            cmd.extend(["-map", "[aout]"])
        cmd.extend([*self.get_video_encoder_args(), "-pix_fmt", "yuv420p"])
        if audio_source:
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        cmd.extend(["-t", f"{duration:.3f}", "-movflags", "+faststart", "-progress", "pipe:1", output_path])
        return cmd

    def process_clip(
        self,
        video_path: str,
        highlight: dict,
        index: int,
        total_clips: int = 1,
        add_captions: bool = True,
        add_hook: bool = True,
        pre_cut: bool = False,
        caption_transcript: TimedTranscript | None = None,
    ):
        if self.is_cancelled():
            return
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{index:02d}"
        clip_dir = self.output_dir / timestamp
        clip_dir.mkdir(parents=True, exist_ok=True)
        start = highlight["start_time"].replace(",", ".")
        end = highlight["end_time"].replace(",", ".")
        duration = self.parse_timestamp(end) - self.parse_timestamp(start)
        self.log(f"  Output folder: {clip_dir}")
        self.log(f"\n[Clip {index}] {highlight['title']}")

        def clip_progress(label, value):
            overall = 0.3 + (0.6 * ((index - 1 + max(0.0, min(1.0, value))) / total_clips))
            self.set_progress(f"Clip {index}/{total_clips}: {label}", overall)

        landscape_file = clip_dir / "temp_landscape.mp4"
        portrait_file = clip_dir / "temp_portrait.mp4"
        hook_overlay = clip_dir / "hook.png"
        credit_overlay = clip_dir / "credit.png"
        final_temp = clip_dir / "master.tmp.mp4"
        ass_file = None
        cleanup_paths = [landscape_file, portrait_file, hook_overlay, credit_overlay, final_temp]
        actual_hook = bool(add_hook)
        actual_captions = False
        actual_watermark = bool(self.watermark_settings.get("enabled"))
        actual_credit = bool(self.credit_watermark_settings.get("enabled") and self.channel_name)
        try:
            if pre_cut:
                source_file = Path(video_path)
                clip_progress("Section siap", 0.08)
            else:
                clip_progress("Memotong video", 0.02)
                cmd = [self.ffmpeg_path, "-y", "-ss", start, "-i", video_path, "-t", str(duration), *self.get_video_encoder_args(), "-c:a", "aac", "-b:a", "192k", "-progress", "pipe:1", str(landscape_file)]
                self.run_ffmpeg_with_progress(cmd, duration, lambda progress: clip_progress("Memotong video", progress * 0.15))
                source_file = landscape_file
            if add_captions:
                ass_file = self._create_caption_ass(str(source_file), clip_dir, caption_transcript)
                actual_captions = True
                cleanup_paths.append(ass_file)
            if getattr(self, "screen_size", "9:16") == "16:9":
                render_input = source_file
                clip_progress("Menyiapkan overlay", 0.55)
            else:
                clip_progress("Menyusun video portrait", 0.15)
                self.convert_to_portrait_with_progress(str(source_file), str(portrait_file), lambda progress: clip_progress("Menyusun video portrait", 0.15 + progress * 0.4))
                render_input = portrait_file
            width, height, render_duration = self._probe_render_input(str(render_input))
            final_duration = min(duration, render_duration) if render_duration > 0 else duration
            audio_source = str(source_file) if self._has_audio_stream(str(source_file)) else None
            if actual_hook:
                self._create_hook_overlay(highlight.get("hook_text", highlight["title"]), width, height, hook_overlay)
            if actual_credit:
                self._create_credit_overlay(width, height, credit_overlay)
            watermark_image = str(self.watermark_settings.get("image_path") or "") if actual_watermark else ""
            watermark_path = Path(watermark_image) if watermark_image and Path(watermark_image).exists() else None
            clip_progress("Merender hasil akhir", 0.7)
            cmd = self._build_composite_command(
                str(render_input),
                str(final_temp),
                final_duration,
                audio_source=audio_source,
                hook_overlay=hook_overlay if actual_hook else None,
                ass_file=ass_file,
                watermark_path=watermark_path,
                watermark_placeholder=actual_watermark and watermark_path is None,
                credit_overlay=credit_overlay if actual_credit else None,
            )
            self.log_ffmpeg_command(cmd, "Final Composite")
            self.run_ffmpeg_with_progress(cmd, final_duration, lambda progress: clip_progress("Merender hasil akhir", 0.7 + progress * 0.28))
            if not final_temp.exists() or final_temp.stat().st_size < 1000:
                raise Exception("Final render failed: output file not found")
            final_file = clip_dir / "master.mp4"
            os.replace(final_temp, final_file)
            metadata = {
                "title": highlight["title"],
                "description": highlight.get("description", ""),
                "source_title": self.video_info.get("title", ""),
                "source_description": self.video_info.get("description", ""),
                "hook_text": highlight.get("hook_text", highlight["title"]),
                "start_time": highlight["start_time"],
                "end_time": highlight["end_time"],
                "duration_seconds": highlight["duration_seconds"],
                "has_hook": actual_hook,
                "has_captions": actual_captions,
                "has_watermark": actual_watermark,
                "has_credit": actual_credit,
                "channel_name": self.channel_name,
                "virality_score": int(highlight.get("virality_score", 5) or 5),
            }
            (clip_dir / "data.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                thumbnail_path = clip_dir / "thumbnail.jpg"
                subprocess.run([self.ffmpeg_path, "-y", "-ss", str(min(1.0, duration * 0.1)), "-i", str(final_file), "-frames:v", "1", "-q:v", "3", str(thumbnail_path)], capture_output=True, timeout=30)
            except Exception as exc:
                self.log(f"  Thumbnail extraction failed (non-fatal): {exc}")
            clip_progress("Selesai", 1.0)
        finally:
            for path in cleanup_paths:
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    pass

    def create_ass_subtitle_capcut(self, transcript: TimedTranscript, output_path: str, time_offset: float = 0):
        """Create ASS subtitle file with CapCut-style word-by-word highlighting"""
        transcript = validate_timed_transcript(transcript)
        
        style = getattr(self, "subtitle_style", {}) or {}
        font = str(style.get("font_family") or style.get("font") or "Plus Jakarta Sans")
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
        color_hex = str(style.get("color") or "#00BFFF").strip("#")
        text_color_hex = str(style.get("text_color") or "#FFFFFF").strip("#")
        outline_color_hex = str(style.get("outline_color") or "#000000").strip("#")
        bg_color_hex = str(style.get("bg_color") or "#000000").strip("#")
        bg_opacity = float(style.get("bg_opacity", 0.0))
        font_weight = int(style.get("font_weight") or 800)

        def ass_color(value, fallback):
            if len(value) != 6:
                return fallback
            r, g, b = value[0:2], value[2:4], value[4:6]
            return f"&H00{b}{g}{r}"

        highlight_colour = ass_color(color_hex, "&H00FFBF00")
        primary_colour = ass_color(text_color_hex, "&H00FFFFFF")
        outline_colour = ass_color(outline_color_hex, "&H00000000")

        if len(bg_color_hex) == 6:
            r, g, b = bg_color_hex[0:2], bg_color_hex[2:4], bg_color_hex[4:6]
            alpha_hex = f"{int((1.0 - bg_opacity) * 255):02X}"
            back_colour = f"&H{alpha_hex}{b}{g}{r}"
        else:
            back_colour = "&H80000000"

        border_style = 1
        outline = max(0, int(round(float(style.get("outline_thickness", 1.0)) / 340 * width)))
        bold = -1 if font_weight >= 600 else 0

        ass_content = f"""[Script Info]
Title: Auto-generated captions
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},{primary_colour},{primary_colour},{outline_colour},{back_colour},{bold},0,0,0,100,100,0,0,{border_style},{outline},0,{alignment},0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        events = []
        text_transform = str(style.get("text_transform", "none")).lower()

        def ass_text(value):
            value = str(value)
            if text_transform == "uppercase":
                value = value.upper()
            elif text_transform == "lowercase":
                value = value.lower()
            elif text_transform == "capitalize":
                value = value.title()
            return value.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\r", " ").replace("\n", " ")

        if transcript["words"]:
            words = [
                {"text": ass_text(word["word"]), "start": word["start"], "end": word["end"]}
                for word in transcript["words"]
            ]
            chunk = []
            chunks = []
            for index, word in enumerate(words):
                chunk.append(word)
                next_word = words[index + 1] if index + 1 < len(words) else None
                remaining = len(words) - index - 1
                should_flush = False
                if len(chunk) >= 3:
                    should_flush = not next_word or word["text"].rstrip().endswith((".", ",", "?", "!")) or next_word["start"] - word["end"] > 0.45 or len(chunk) >= (4 if remaining == 3 else 5)
                if should_flush:
                    chunks.append(chunk)
                    chunk = []
            if chunk:
                chunks.append(chunk)
            for chunk in chunks:
                chunk_start = chunk[0]["start"]
                chunk_end = chunk[-1]["end"]
                for i, word in enumerate(chunk):
                    event_start = chunk_start if i == 0 else chunk[i - 1]["end"]
                    event_end = word["end"] if i < len(chunk) - 1 else chunk_end
                    if event_end - event_start < 0.01:
                        event_end = event_start + 0.01
                    text_parts = []
                    for j, chunk_word in enumerate(chunk):
                        if i == j:
                            text_parts.append(f"{{\\c{highlight_colour}}}{chunk_word['text']}{{\\c{primary_colour}}}")
                        else:
                            text_parts.append(f"{{\\c{primary_colour}}}{chunk_word['text']}")
                    events.append({
                        "start": self.format_time(event_start + time_offset),
                        "end": self.format_time(event_end + time_offset),
                        "text": " ".join(text_parts),
                    })
        else:
            for segment in transcript["segments"]:
                start = segment["start"] + time_offset
                end = segment["end"] + time_offset
                words = segment["text"].split()
                parts = [" ".join(words[i:i + 4]) for i in range(0, len(words), 4)]
                span = max(0.25, (end - start) / len(parts))
                for index, part in enumerate(parts):
                    part_start = start + index * span
                    part_end = end if index == len(parts) - 1 else min(end, part_start + span)
                    events.append({
                        "start": self.format_time(part_start),
                        "end": self.format_time(part_end),
                        "text": ass_text(part),
                    })

        for event in events:
            ass_content += f"Dialogue: 0,{event['start']},{event['end']},Default,,0,0,0,,{{\\pos({pos_x},{pos_y})}}{event['text']}\n"

        with open(output_path, "w", encoding="utf-8") as file:
            file.write(ass_content)
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

