import base64
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
import time
import wave
from datetime import datetime
from pathlib import Path

from clipper_shared import SUBPROCESS_FLAGS, TimedTranscript, _hex_to_rgb, validate_timed_transcript
from clipper_base import ClipperBase
from gaming_layout import GamingLayoutError, validate_roi
from layout_modes import build_filtergraph, output_geometry
from subtitle_cues import build_subtitle_cues, non_overlapping_segments
from visual_style import find_hook_name_span, hook_name_from_title, hook_tts_text, normalize_hook_text
from speaker_tracking import detect_split_person_rois, split_rois_are_distinct
from config.editor_defaults import HOOK_PAUSE_SECONDS, HOOK_SLIDE_SECONDS

HOOK_TTS_TEMPO = 1.0

from utils.logger import debug_log


def _write_json_atomic(path, data):
    # ponytail: duplicates job_manager._write_json_atomic (which has retry).
    # Export path writes once per clip — no concurrent access, retry not needed.
    # Merge into clipper_shared if a 3rd caller appears.
    path = Path(path)
    temporary = path.with_name(f"{path.stem}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


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
        result = self._run_probe_subprocess(
            [self.ffmpeg_path, "-i", input_path],
            capture_output=True,
            text=True,
            creationflags=SUBPROCESS_FLAGS,
        )
        dimensions = re.search(r'(\d{3,4})x(\d{3,4})', result.stderr or "")
        duration_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr or "")
        width, height = (int(dimensions.group(1)), int(dimensions.group(2))) if dimensions else self._render_size()
        duration = 60.0
        if duration_match:
            hours, minutes, seconds = duration_match.groups()
            duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        return width, height, duration

    def _has_audio_stream(self, input_path: str):
        result = self._run_probe_subprocess(
            [self.ffmpeg_path, "-i", input_path],
            capture_output=True,
            text=True,
            creationflags=SUBPROCESS_FLAGS,
        )
        return "Audio:" in (result.stderr or "")

    def _probe_media_duration(self, input_path: str) -> float:
        probe = Path(self.ffmpeg_path).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        result = self._run_probe_subprocess([str(probe), "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(input_path)], capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
        try:
            duration = float((result.stdout or "").strip())
        except ValueError as exc:
            raise RuntimeError("Durasi audio hook tidak valid") from exc
        if result.returncode != 0 or not math.isfinite(duration) or duration <= 0:
            raise RuntimeError("Durasi audio hook tidak valid")
        return duration

    @staticmethod
    def _tts_text(hook_text: str) -> str:
        text = re.sub(r"[^\w\s.,!?;!'\"()\-]", "", hook_tts_text(hook_text), flags=re.UNICODE)
        return re.sub(r"\s+", " ", text.replace(",", " ")).strip()

    @staticmethod
    def _tts_pronunciation_text(spoken_text: str) -> str:
        """Add minimal phonetic guidance without changing overlay metadata."""
        return re.sub(r"\bJIGONG\b", "ji-gong", spoken_text, flags=re.IGNORECASE)

    def _generate_hook_tts(self, hook_text: str, clip_dir: Path) -> tuple[Path, float]:
        import requests
        api_keys = list(dict.fromkeys(
            str(key) for key in (getattr(self, "tts_api_keys", None) or [getattr(self, "tts_api_key", "")]) if key
        ))
        if not api_keys:
            raise ValueError("Gemini API key diperlukan untuk suara hook")
        model = str(getattr(self, "tts_model", "") or "gemini-3.1-flash-tts-preview")
        voice = str(getattr(self, "tts_voice", "") or "Charon")
        base_url = str(getattr(self, "tts_base_url", "") or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        spoken_text = self._tts_text(hook_text)
        digest = hashlib.sha256(f"{model}|{voice}|plain_v1|{spoken_text}".encode("utf-8")).hexdigest()[:20]
        # Shared tenant cache: survives across runs; still keyed by model/voice/style/text.
        output_root = Path(getattr(self, "output_dir", clip_dir))
        cache_dir = output_root.parent / "cache" / "hook-tts"
        if not cache_dir.parent.exists():
            cache_dir = output_root / ".hook-tts-cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        output = cache_dir / f"{digest}.wav"
        if not output.is_file():
            payload = {
                "contents": [{"parts": [{"text": spoken_text}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
                },
            }
            response = requests.Response()
            for index, api_key in enumerate(api_keys):
                response = requests.post(f"{base_url}/models/{model}:generateContent", headers={"x-goog-api-key": api_key, "Content-Type": "application/json"}, json=payload, timeout=90)
                if getattr(response, "status_code", 200) not in {401, 403, 429, 500, 502, 503, 504} or index == len(api_keys) - 1:
                    response.raise_for_status()
                    break
            parts = (((response.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
            audio = next((part.get("inlineData") or part.get("inline_data") for part in parts if part.get("inlineData") or part.get("inline_data")), {})
            encoded = audio.get("data") or ""
            if not encoded:
                raise RuntimeError("Gemini TTS tidak menghasilkan audio")
            mime = str(audio.get("mimeType") or audio.get("mime_type") or "")
            if mime and not mime.lower().startswith("audio/l16"):
                raise RuntimeError(f"Format audio Gemini TTS tidak didukung: {mime}")
            pcm = base64.b64decode(encoded)
            temporary = output.with_suffix(".tmp.wav")
            with wave.open(str(temporary), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(24000)
                handle.writeframes(pcm)
            os.replace(temporary, output)
        return output, self._probe_media_duration(str(output)) / HOOK_TTS_TEMPO

    def _create_hook_overlay(self, hook_text: str, width: int, height: int, output_path: Path, known_names=None):
        from PIL import Image, ImageDraw, ImageFont

        style = self.hook_style_settings or {}
        font_size_frac = float(style.get("font_size", 0.056))
        root = Path(__file__).resolve().parent
        font_weight = max(100, min(900, int(style.get("font_weight") or 700)))
        family_fonts = {
            "Plus Jakarta Sans": root / "fonts" / "PlusJakartaSans.ttf",
            "Poppins": root / "fonts" / ("Poppins-Bold.ttf" if font_weight >= 600 else "Poppins-Regular.ttf"),
        }
        font_candidates = [str(family_fonts["Poppins"]), str(family_fonts["Plus Jakarta Sans"])]
        body_px = max(1, int(max(16, font_size_frac * 500) / 340 * width))
        name_px = max(body_px + 1, int(round(body_px * 1.18)))
        min_hook_px = max(10, int(round(20 / 1080 * width)))
        letter_spacing = float(style.get("letter_spacing", 0.0)) * width

        def load_font(size_px: int):
            for candidate in font_candidates:
                if not candidate or not os.path.exists(candidate):
                    continue
                try:
                    font = ImageFont.truetype(candidate, size_px)
                    if hasattr(font, "set_variation_by_axes") and "PlusJakartaSans" in Path(candidate).name:
                        try:
                            font.set_variation_by_axes([max(200, min(800, font_weight))])
                        except OSError:
                            pass
                    return font
                except Exception:
                    continue
            return ImageFont.load_default()

        display = normalize_hook_text(hook_text)
        plain = " ".join(line for line in display.split("\n") if line.strip()) or "MOMEN INI WAJIB DITONTON"
        words = plain.split()
        name_span = find_hook_name_span(words, known_names=known_names, original_text=hook_text)

        stroke_width = max(0, int(round(float(style.get("outline_thickness", 1.0)) / 340 * width)))
        max_text_width = max(40, int(width * 0.86) - 2 * stroke_width)
        max_lines = max(1, int(style.get("max_lines", 3)))
        body_font = load_font(body_px)
        name_font = load_font(name_px) if name_span else body_font
        space_w = 0

        def measure(word: str, is_name: bool) -> float:
            font = name_font if is_name else body_font
            try:
                width_px = sum(float(font.getlength(char)) for char in word)
            except AttributeError:
                width_px = sum(float(font.getbbox(char)[2]) for char in word)
            return width_px + letter_spacing * max(0, len(word) - 1)

        def draw_word(draw, position, word, font, fill, stroke_width, stroke_fill):
            x, baseline = position
            for char in word:
                draw.text((x, baseline), char, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill, anchor="ls")
                try:
                    x += float(font.getlength(char)) + letter_spacing
                except AttributeError:
                    x += float(font.getbbox(char)[2]) + letter_spacing

        def wrap_words(word_list, name_range):
            lines = []
            current = []
            current_w = 0.0
            for idx, word in enumerate(word_list):
                is_name = bool(name_range and name_range[0] <= idx < name_range[1])
                word_w = measure(word, is_name)
                gap = space_w if current else 0.0
                if current and current_w + gap + word_w > max_text_width:
                    lines.append(current)
                    current = [(word, is_name)]
                    current_w = word_w
                else:
                    current.append((word, is_name))
                    current_w += gap + word_w
            if current:
                lines.append(current)
            return lines

        for _ in range(40):
            try:
                space_w = float(body_font.getlength(" "))
            except AttributeError:
                space_w = float(body_font.getbbox(" ")[2])
            all_lines = wrap_words(words, name_span)
            lines = all_lines
            too_many = len(lines) > max_lines
            too_wide = False
            for line in lines[:max_lines]:
                width_line = 0.0
                for i, (word, is_name) in enumerate(line):
                    width_line += measure(word, is_name)
                    if i:
                        width_line += space_w
                if width_line > max_text_width + 1:
                    too_wide = True
                    break
            if not too_wide and not too_many:
                break
            if body_px <= min_hook_px:
                if len(lines) > max_lines:
                    # Keep every spoken word visible. Balance overflow across
                    # the fixed line count instead of dropping trailing words.
                    flat = [item for row in lines for item in row]
                    per_line = max(1, (len(flat) + max_lines - 1) // max_lines)
                    lines = [flat[index:index + per_line] for index in range(0, len(flat), per_line)]
                break
            body_px = max(min_hook_px, body_px - max(1, int(round(6 / 1080 * width))))
            name_px = max(body_px + 1, int(round(body_px * 1.18))) if name_span else body_px
            body_font = load_font(body_px)
            name_font = load_font(name_px) if name_span else body_font

        if not lines:
            lines = [[(plain, False)]]

        line_heights = [int(max(name_px if is_name else body_px for _, is_name in line) * 0.98) for line in lines]
        total_height = sum(line_heights)
        center_x = float(style.get("position_x", 0.5)) * width
        center_y = float(style.get("position_y", 0.62)) * height
        block_top = center_y - total_height / 2
        outline_width = max(0, int(round(float(style.get("outline_thickness", 1.0)) / 340 * width)))
        stroke_width = outline_width
        body_color = _hex_to_rgb(str(style.get("text_color") or "#FFFFFF"))
        name_color = _hex_to_rgb("#2CCDE7")
        outline_color = _hex_to_rgb(str(style.get("outline_color") or "#000000"))
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        body_metrics = getattr(body_font, "getmetrics", None)
        name_metrics = getattr(name_font, "getmetrics", None)
        line_top = block_top
        for line_index, line in enumerate(lines):
            line_w = 0.0
            for i, (word, is_name) in enumerate(line):
                line_w += measure(word, is_name)
                if i:
                    line_w += space_w
            x = center_x - line_w / 2
            uses_name = any(is_name for _, is_name in line)
            metrics = name_metrics if uses_name else body_metrics
            baseline_y = line_top + (metrics()[0] if metrics else (name_px if uses_name else body_px))
            for i, (word, is_name) in enumerate(line):
                font = name_font if is_name else body_font
                fill = name_color if is_name else body_color
                bbox = draw.textbbox((0, 0), word, font=font, stroke_width=stroke_width, anchor="ls")
                text_x = min(max(x, stroke_width - bbox[0]), width - bbox[2] - stroke_width)
                draw_word(draw, (text_x, baseline_y), word, font, (*fill, 255), stroke_width, (*outline_color, 255))
                x += measure(word, is_name) + space_w
            line_top += line_heights[line_index]
        overlay.save(output_path, "PNG")

    def _create_credit_overlay(self, width: int, height: int, output_path: Path):
        from PIL import Image, ImageDraw, ImageFont

        settings = self.credit_watermark_settings or {}
        size = float(settings.get("size", 0.028))
        opacity = float(settings.get("opacity", 0.85))
        font_size = self._scale_from_preview_width(size, 320, width, minimum=max(10, int(round(10 / 340 * width))))
        root = Path(__file__).resolve().parent
        font_path = root / "fonts" / "Poppins-Regular.ttf"
        if not font_path.is_file():
            font_path = root / "fonts" / "PlusJakartaSans.ttf"
        font = ImageFont.truetype(str(font_path), font_size)
        if hasattr(font, "set_variation_by_axes"):
            try:
                font.set_variation_by_axes([400])
            except OSError:
                # Static Poppins fonts expose the method but reject axes.
                pass
        channel = self.channel_name if self.channel_name and self.channel_name != "{channel}" else "Local Video"
        channel = re.sub(r"^@+", "", str(channel).strip()) or "channel"
        text = "sc: @" + channel
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        stroke_width = max(0, int(round(float(settings.get("outline_thickness", 0.0)) / 340 * width)))
        letter_spacing = max(0.0, float(settings.get("letter_spacing", 0.0)) * width)
        text_width = sum(float(font.getlength(char)) for char in text) + letter_spacing * max(0, len(text) - 1)
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
        # Top-right small credit
        margin_x = width * 0.04
        margin_y = height * 0.035
        text_x = width - margin_x - text_width
        text_y = margin_y - bbox[1]
        color = _hex_to_rgb(str(settings.get("color") or "#FFFFFF"))
        alpha = int(255 * opacity)
        for char in text:
            draw.text(
                (text_x, text_y), char, font=font, fill=(*color, alpha),
                stroke_width=stroke_width, stroke_fill=(*color, alpha),
            )
            text_x += float(font.getlength(char)) + letter_spacing
        overlay.save(output_path, "PNG")

    def _create_caption_ass(
        self,
        input_path: str,
        clip_dir: Path,
        transcript: TimedTranscript | None = None,
        time_offset: float = 0.0,
    ) -> Path | None:
        if transcript is not None:
            transcript = validate_timed_transcript(transcript)
            if not transcript["words"] and not transcript["segments"]:
                raise ValueError("Subtitle transcript has no timestamped content")
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
        event_count = self.create_ass_subtitle_capcut(transcript, str(ass_file), time_offset)
        if event_count <= 0:
            ass_file.unlink(missing_ok=True)
            raise Exception("Subtitle transcription produced 0 ASS events")
        self.log(f"  ASS events: {event_count}")
        return ass_file

    def _escape_filter_path(self, path: Path):
        return str(path).replace('\\', '/').replace(':', '\\:').replace("'", "\\'")

    def _build_composite_command(self, input_path: str, output_path: str, duration: float, audio_source=None, hook_overlay=None, ass_file=None, watermark_path=None, watermark_placeholder=False, credit_overlay=None, portrait_filters=None, output_size=None, profile="final", tts_source=None, intro_duration=0.0):
        inputs = [input_path]
        audio_index = 0
        if audio_source and Path(audio_source).resolve() != Path(input_path).resolve():
            audio_index = len(inputs)
            inputs.append(str(audio_source))
        tts_index = None
        if tts_source:
            tts_index = len(inputs)
            inputs.append(str(tts_source))
        filters = list(portrait_filters or ["[0:v]setpts=PTS-STARTPTS[v0]"])
        current = "v0"
        layer = 1
        intro_duration = max(0.0, float(intro_duration or 0.0))
        if tts_index is not None and intro_duration > 0:
            filters.extend([f"[{current}]split=2[vholdsrc][vmain]", f"[vholdsrc]trim=start_frame=0:end_frame=1,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={intro_duration:.3f},trim=duration={intro_duration:.3f}[vfreeze]", "[vmain]setpts=PTS-STARTPTS[vplay]", "[vfreeze][vplay]concat=n=2:v=1:a=0[vintro]"])
            current = "vintro"
        if hook_overlay:
            input_index = len(inputs)
            inputs.append(str(hook_overlay))
            filters.append(f"[{input_index}:v]format=rgba[hook]")
            hook_duration = intro_duration if intro_duration > 0 else max(1.0, min(10.0, float((self.hook_style_settings or {}).get("duration", 5.0))))
            filters.append(f"[{current}][hook]overlay=0:0:enable='between(t,0,{hook_duration:.3f})'[v{layer}]")
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
        if output_size:
            filters.append(f"[{current}]scale={output_size[0]}:{output_size[1]}[vscaled]")
            current = "vscaled"
        filters.append(f"[{current}]format=yuv420p[vout]")
        if tts_index is not None and intro_duration > 0:
            filters.append(f"[{tts_index}:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,apad=pad_dur={HOOK_PAUSE_SECONDS + HOOK_SLIDE_SECONDS:.3f},atrim=duration={intro_duration:.3f},asetpts=PTS-STARTPTS[atts]")
            if audio_source:
                filters.append(f"[{audio_index}:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS[aoriginal]")
            else:
                filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={duration:.3f},asetpts=PTS-STARTPTS[aoriginal]")
            # volume=1 forces clean frame sizing before loudnorm; avoids 1-sample AAC packets that YouTube speeds up.
            filters.append("[atts][aoriginal]concat=n=2:v=0:a=1,volume=1,loudnorm=I=-14:LRA=7:TP=-1,asetpts=PTS-STARTPTS[aout]")
        elif audio_source:
            filters.append(f"[{audio_index}:a]asetpts=PTS-STARTPTS,volume=1,loudnorm=I=-14:LRA=7:TP=-1,asetpts=PTS-STARTPTS[aout]")
        cmd = [self.ffmpeg_path, "-y"]
        for media_input in inputs:
            cmd.extend(["-i", media_input])
        cmd.extend(["-filter_complex", ";".join(filters), "-map", "[vout]"])
        has_output_audio = bool(audio_source or tts_index is not None)
        if has_output_audio:
            cmd.extend(["-map", "[aout]"])
        cmd.extend([*self.get_video_encoder_args(), "-pix_fmt", "yuv420p"])
        if has_output_audio:
            cmd.extend(["-c:a", "aac", "-b:a", "192k", "-ar", "48000"])
        cmd.extend(["-t", f"{duration + intro_duration:.3f}", "-movflags", "+faststart", "-progress", "pipe:1", output_path])
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
            reframe_started = time.monotonic()
            if getattr(self, "screen_size", "9:16") == "16:9":
                render_input = source_file
                clip_progress("Menyiapkan draft", 0.55)
            else:
                clip_progress("Menyusun video portrait", 0.15)
                self.convert_to_portrait_with_progress(str(source_file), str(portrait_file), lambda progress: clip_progress("Menyusun video portrait", 0.15 + progress * 0.4))
                render_input = portrait_file
            self.log(f"  Reframe elapsed: {time.monotonic() - reframe_started:.1f}s")
            if getattr(self, "draft_only", False):
                if add_captions and caption_transcript is None:
                    raise ValueError("Subtitle transcript tidak tersedia")
                source_output = clip_dir / "source.mp4"
                draft_output = clip_dir / "draft.mp4"
                shutil.copyfile(source_file, source_output)
                shutil.copyfile(render_input, draft_output)
                caption_transcript = validate_timed_transcript(caption_transcript) if caption_transcript else {"duration": max(0.0, duration), "words": [], "segments": []}
                has_timed_transcript = bool(caption_transcript["words"] or caption_transcript["segments"])
                (clip_dir / "transcript.json").write_text(json.dumps(caption_transcript, ensure_ascii=False), encoding="utf-8")
                thumbnail_path = clip_dir / "thumbnail.jpg"
                result = self._run_probe_subprocess([self.ffmpeg_path, "-y", "-ss", str(min(1.0, duration * 0.1)), "-i", str(draft_output), "-frames:v", "1", "-q:v", "3", str(thumbnail_path)], capture_output=True)
                if result.returncode != 0 or not thumbnail_path.is_file():
                    raise RuntimeError("Thumbnail draft gagal dibuat")
                metadata = {
                    "clip_id": uuid.uuid4().hex,
                    "generation_id": self.output_dir.name,
                    "created_at": datetime.now().astimezone().isoformat(),
                    "status": "needs_edit",
                    "title": highlight["title"],
                    "description": highlight.get("description", ""),
                    "source_title": self.video_info.get("title", ""),
                    "source_description": self.video_info.get("description", ""),
                    "hook_text": highlight.get("hook_text", highlight["title"]),
                    "start_time": highlight["start_time"],
                    "end_time": highlight["end_time"],
                    "duration_seconds": highlight["duration_seconds"],
                    "channel_name": self.channel_name,
                    "virality_score": int(highlight.get("virality_score", 5) or 5),
                    "source_path": "source.mp4",
                    "draft_path": "draft.mp4",
                    "final_path": "master.mp4",
                    "transcript_path": "transcript.json" if has_timed_transcript else "",
                    "draft_settings": {
                        "landscape_blur": bool(getattr(self, "landscape_blur", False)),
                        "blur_background": dict(getattr(self, "blur_background_settings", {}) or {}),
                        "video_quality": str(getattr(self, "video_quality", "720")),
                        "screen_size": str(getattr(self, "screen_size", "9:16")),
                    },
                    "render_revision": 0,
                }
                _write_json_atomic(clip_dir / "data.json", metadata)
                clip_progress("Siap diedit", 1.0)
                return
            if add_captions:
                ass_file = self._create_caption_ass(str(source_file), clip_dir, caption_transcript)
                actual_captions = True
                cleanup_paths.append(ass_file)
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
            _write_json_atomic(clip_dir / "data.json", metadata)
            try:
                thumbnail_path = clip_dir / "thumbnail.jpg"
                from clipper_ffmpeg import _FFMPEG_PROCESS_LOCK
                with _FFMPEG_PROCESS_LOCK:
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

    def render_existing_clip(self, clip_dir: Path, metadata: dict, settings: dict, output_path: Path, preview: bool = False):
        # V3 locked style: ignore client blur/watermark toggles
        watermark_settings = {**(settings.get("watermark") or {}), "enabled": False}
        credit_settings = {**(settings.get("credit_watermark") or {}), "enabled": True, "text": "sc: @{channel}"}
        hook_settings = {**(settings.get("hook_style") or {}), "enabled": True, "font_family": "Poppins"}
        subtitle_settings = {
            **(settings.get("subtitle") or {}),
            "enabled": True,
            "text_transform": "none",
            "font_family": "Poppins",
            "font_weight": 700,
            "color": "#2CCDE7",
            "text_color": "#FFFFFF",
            "outline_color": "#000000",
            "outline_thickness": float((settings.get("subtitle") or {}).get("outline_thickness", 2.0)),
            "size": float((settings.get("subtitle") or {}).get("size", 0.068)),
            "shadow": 0,
        }
        blur_settings = {**(settings.get("blur_background") or {}), "enabled": False}
        self.watermark_settings = watermark_settings
        self.credit_watermark_settings = credit_settings
        self.hook_style_settings = hook_settings
        self.blur_background_settings = blur_settings
        self.subtitle_style = subtitle_settings
        source_file = clip_dir / "source.mp4"
        if not source_file.is_file():
            raise ValueError("Source klip tidak tersedia")
        name = Path(str(metadata.get("transcript_path") or "transcript.json")).name
        if name != "transcript.json":
            name = "transcript.json"
        transcript_path = (clip_dir / name).resolve()
        try:
            transcript_path.relative_to(clip_dir.resolve())
        except ValueError:
            transcript_path = clip_dir / "transcript.json"
        transcript = json.loads(transcript_path.read_text(encoding="utf-8")) if transcript_path.is_file() else None
        operation_id = uuid.uuid4().hex[:12]
        hook_overlay, credit_overlay, ass_file = (clip_dir / f"render-{operation_id}.hook.png"), (clip_dir / f"render-{operation_id}.credit.png"), None
        temporary = [hook_overlay, credit_overlay]
        try:
            source_width, source_height, duration = self._probe_render_input(str(source_file))
            layout = settings.get("video_layout", {}) or {}
            quality = str(settings.get("video_quality") or getattr(self, "video_quality", "1080") or "1080")
            width, height = output_geometry(quality)
            self.output_resolution = f"{width}:{height}"
            self.video_quality = quality
            mode = str(layout.get("mode") or "normal")
            if mode in {"normal", "vertical_full"}:
                mode = "vertical_full"
            elif mode not in {"gaming", "split_middle"}:
                mode = "vertical_full"
            roi = None
            tracked_source = None
            if mode == "gaming":
                roi = validate_roi({"x": layout.get("facecam_x"), "y": layout.get("facecam_y"), "width": layout.get("facecam_width"), "height": layout.get("facecam_height")})
                if not roi:
                    raise GamingLayoutError("Facecam tidak ditemukan. Gunakan video dengan facecam yang terlihat jelas, lalu coba lagi.")
            elif mode == "split_middle":
                stored_rois = layout.get("person_rois") or metadata.get("split_person_rois")
                if isinstance(stored_rois, dict) and split_rois_are_distinct(stored_rois):
                    roi = stored_rois
                else:
                    roi = detect_split_person_rois(str(source_file)) or None
                    if roi and split_rois_are_distinct(roi):
                        metadata["split_person_rois"] = roi
                    elif not (roi and split_rois_are_distinct(roi)):
                        roi = None
                # Subtitle center for split
                subtitle_settings["position_y"] = 0.5
            else:
                subtitle_settings["position_y"] = float(subtitle_settings.get("position_y") or 0.78)
            self.subtitle_style = subtitle_settings
            render_input = source_file
            portrait_filters = None
            tracked_source = None
            raw_hook = str(metadata.get("hook_text") or metadata.get("title", "") or "")
            known = [
                hook_name_from_title(raw_hook, str(metadata.get("title") or "")),
                metadata.get("channel_name"),
                getattr(self, "channel_name", ""),
            ]

            # Prefetch TTS while portrait work runs; falls back to sequential if executor fails.
            from concurrent.futures import ThreadPoolExecutor
            tts_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hook-tts")
            tts_future = tts_executor.submit(self._generate_hook_tts, raw_hook, clip_dir)
            try:
                if mode == "vertical_full" and source_width > source_height:
                    draft_file = clip_dir / "draft.mp4"
                    reused_draft = False
                    # Reuse draft only when stamped with current tracker version
                    # (loop engineering / tracker upgrades must re-track).
                    try:
                        from speaker_tracking import TRACKER_VERSION as _TRACKER_VERSION
                    except Exception:
                        _TRACKER_VERSION = ""
                    draft_stamp = clip_dir / "draft.tracker"
                    stamp_ok = (
                        draft_stamp.is_file()
                        and draft_stamp.read_text(encoding="utf-8").strip() == str(_TRACKER_VERSION)
                    )
                    if draft_file.is_file() and draft_file.stat().st_size >= 1000 and stamp_ok:
                        try:
                            draft_w, draft_h, _ = self._probe_render_input(str(draft_file))
                        except Exception:
                            draft_w, draft_h = 0, 0
                        # Draft already holds speaker-tracked portrait from generate stage.
                        if draft_w > 0 and draft_h > draft_w:
                            render_input = draft_file
                            source_width, source_height = draft_w, draft_h
                            portrait_filters = [
                                f"[0:v]setpts=PTS-STARTPTS,scale={width}:{height}:flags=lanczos,setsar=1[v0]"
                            ]
                            reused_draft = True
                            self.log("  Reusing tracked draft portrait (skip re-track)")
                    if not reused_draft:
                        tracked_source = clip_dir / f"render-{operation_id}.tracked.mp4"
                        temporary.append(tracked_source)
                        try:
                            self.convert_to_portrait_with_progress(
                                str(source_file),
                                str(tracked_source),
                                lambda _value: None,
                            )
                        except Exception as exc:
                            self.log(f"  Speaker tracking fallback to static crop: {exc}")
                            tracked_source = None
                        if tracked_source and tracked_source.is_file() and tracked_source.stat().st_size >= 1000:
                            render_input = tracked_source
                            source_width, source_height, _ = self._probe_render_input(str(tracked_source))
                            portrait_filters = [
                                f"[0:v]setpts=PTS-STARTPTS,scale={width}:{height}:flags=lanczos,setsar=1[v0]"
                            ]
                            # Refresh draft + stamp so next final render can reuse safely.
                            try:
                                import shutil as _shutil
                                _shutil.copyfile(tracked_source, draft_file)
                                draft_stamp.write_text(str(_TRACKER_VERSION), encoding="utf-8")
                            except OSError:
                                pass
                        else:
                            portrait_filters, _ = build_filtergraph(mode, source_width, source_height, roi=roi, out_w=width, out_h=height)
                else:
                    portrait_filters, _ = build_filtergraph(mode, source_width, source_height, roi=roi, out_w=width, out_h=height)

                tts_source, spoken_duration = tts_future.result()
            finally:
                tts_executor.shutdown(wait=False, cancel_futures=True)

            intro_duration = spoken_duration + HOOK_PAUSE_SECONDS + HOOK_SLIDE_SECONDS
            self._create_hook_overlay(raw_hook, width, height, hook_overlay, known_names=known)
            if not transcript:
                raise ValueError("Transcript subtitle tidak tersedia")
            ass_file = clip_dir / f"render-{operation_id}.captions.ass"
            generated_ass = self._create_caption_ass(str(source_file), clip_dir, transcript, intro_duration)
            os.replace(generated_ass, ass_file)
            temporary.append(ass_file)
            self.channel_name = metadata.get("channel_name", "")
            self._create_credit_overlay(width, height, credit_overlay)
            preview_size = (540, 960) if preview else None
            command = self._build_composite_command(
                str(render_input), str(output_path), duration,
                audio_source=str(source_file) if self._has_audio_stream(str(source_file)) else None,
                hook_overlay=hook_overlay, ass_file=ass_file, watermark_path=None,
                credit_overlay=credit_overlay, portrait_filters=portrait_filters,
                output_size=preview_size, profile="preview_fast" if preview else "final",
                tts_source=tts_source, intro_duration=intro_duration,
            )
            self.run_ffmpeg_with_progress(command, duration + intro_duration, lambda progress: self.set_progress("Menyusun video", progress), timeout=getattr(self, "render_timeout", 900))
            if not output_path.is_file() or output_path.stat().st_size < 1000:
                raise RuntimeError("Final render gagal")
            thumbnail_runner = getattr(self, "_run_probe_subprocess", None)
            if thumbnail_runner is not None:
                thumbnail_path = clip_dir / "thumbnail.jpg"
                result = thumbnail_runner(
                    [self.ffmpeg_path, "-y", "-i", str(output_path), "-frames:v", "1", "-q:v", "3", str(thumbnail_path)],
                    capture_output=True,
                )
                if result.returncode != 0 or not thumbnail_path.is_file():
                    self.log("  Thumbnail frame pertama gagal dibuat (non-fatal)")
        finally:
            for path in temporary:
                Path(path).unlink(missing_ok=True)

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
        letter_spacing = max(0.0, float(style.get("letter_spacing", 0.0)) * width)
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
Style: Default,{font},{size},{primary_colour},{primary_colour},{outline_colour},{back_colour},{bold},0,0,0,100,100,{letter_spacing:.2f},0,{border_style},{outline},0,{alignment},0,0,0,1

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

        cues = build_subtitle_cues(transcript, text_transform=text_transform)
        for cue in cues:
            if cue["words"]:
                for i, word in enumerate(cue["words"]):
                    event_start = float(word["active_from"])
                    event_end = float(word["active_until"])
                    if event_end - event_start < 0.01:
                        event_end = event_start + 0.01
                    text_parts = []
                    for j, cue_word in enumerate(cue["words"]):
                        color = highlight_colour if i == j else primary_colour
                        text_parts.append(f"{{\\c{color}}}{ass_text(cue_word['text'])}")
                    events.append({
                        "start": self.format_time(event_start + time_offset),
                        "end": self.format_time(event_end + time_offset),
                        "text": " ".join(text_parts),
                    })
            else:
                events.append({
                    "start": self.format_time(float(cue["start"]) + time_offset),
                    "end": self.format_time(float(cue["end"]) + time_offset),
                    "text": ass_text(cue["text"]),
                })

        for event in events:
            ass_content += f"Dialogue: 0,{event['start']},{event['end']},Default,,0,0,0,,{{\\pos({pos_x},{pos_y})\\b{font_weight}}}{event['text']}\n"

        with open(output_path, "w", encoding="utf-8") as file:
            file.write(ass_content)
        return len(events)

