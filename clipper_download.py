import json
import re
import subprocess
import time
from pathlib import Path

from clipper_shared import SUBPROCESS_FLAGS, TimedTranscript, YTDLP_MODULE_AVAILABLE, validate_timed_transcript, yt_dlp
from clipper_base import ClipperBase
from utils.helpers import get_deno_path, get_ffmpeg_path


class DownloadMixin(ClipperBase):
    def _format_selector(self):
        quality = str(getattr(self, "video_quality", "720") or "720")
        max_height = {"480": 480, "720": 720, "1080": 1080, "1440": 1440, "2160": 2160}.get(quality, 720)
        return f"bestvideo[height<={max_height}][fps<=30]+bestaudio/best[height<={max_height}][fps<=30]/bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]"

    def _format_sort(self):
        return ["res", "vcodec:h264", "fps:30", "br"]

    def _cookies_path(self):
        path = getattr(self, "cookies_path", None)
        return Path(path) if path and Path(path).is_file() else None

    def _apply_common_ytdlp_options(self, options):
        deno_path = get_deno_path()
        ffmpeg_path = get_ffmpeg_path()
        if deno_path and Path(deno_path).exists():
            options["js_runtimes"] = {"deno": {"path": deno_path}}
            options["remote_components"] = ["ejs:github"]
        if ffmpeg_path and Path(ffmpeg_path).exists():
            options["ffmpeg_location"] = str(Path(ffmpeg_path).parent)
        if cookies_path := self._cookies_path():
            options["cookiefile"] = str(cookies_path)
        return options

    def download_audio_only(self, url):
        self.log("  Downloading audio-only fallback (MP3 16kHz mono 32kbps)...")
        if YTDLP_MODULE_AVAILABLE and self.ytdlp_path == "yt_dlp_module":
            return self._download_audio_only_module(url)
        return self._download_audio_only_subprocess(url)

    def _download_audio_only_module(self, url):
        output_path = self.temp_dir / "source_audio.mp3"
        last_percent = -1.0

        def progress_hook(status):
            nonlocal last_percent
            if self.is_cancelled():
                raise InterruptedError("Stopped")
            if status.get("status") != "downloading":
                return
            match = re.search(r"(\d+\.?\d*)%", status.get("_percent_str", ""))
            if match and float(match.group(1)) + 0.05 >= last_percent:
                last_percent = float(match.group(1))
                self.set_progress(f"Downloading audio-only fallback... {last_percent:.1f}%", 0.18 + last_percent / 100 * 0.08)

        options = self._apply_common_ytdlp_options({"format": "bestaudio/best", "outtmpl": str(self.temp_dir / "source_audio.%(ext)s"), "progress_hooks": [progress_hook], "quiet": True, "no_warnings": False, "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "32"}], "postprocessor_args": ["-ac", "1", "-ar", "16000", "-b:a", "32k"]})
        with yt_dlp.YoutubeDL(options) as downloader:
            downloader.download([url])
        return self._find_output("source_audio", {".mp3"})

    def _download_audio_only_subprocess(self, url):
        result = self._run_cancelable_subprocess([self.ytdlp_path, "-f", "bestaudio/best", "-x", "--audio-format", "mp3", "--postprocessor-args", "ffmpeg:-ac 1 -ar 16000 -b:a 32k", "-o", str(self.temp_dir / "source_audio.%(ext)s"), url], capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS, timeout=900)
        if result.returncode:
            raise RuntimeError(f"Audio-only download failed:\n{result.stderr}")
        return self._find_output("source_audio", {".mp3"})

    def download_subtitle_only(self, url):
        self.log("[1/2] Downloading subtitle only...")
        if YTDLP_MODULE_AVAILABLE and self.ytdlp_path == "yt_dlp_module":
            return self._download_subtitle_only_module(url)
        return self._download_subtitle_only_subprocess(url)

    def _subtitle_options(self):
        return self._apply_common_ytdlp_options({"skip_download": True, "writesubtitles": True, "writeautomaticsub": True, "subtitleslangs": [self.subtitle_language], "subtitlesformat": "srt", "outtmpl": str(self.temp_dir / "source.%(ext)s"), "quiet": True, "no_warnings": False, "socket_timeout": 30, "retries": 3, "extractor_retries": 3, "postprocessors": [{"key": "FFmpegSubtitlesConvertor", "format": "srt"}]})

    def _video_info(self, info):
        return {"title": info.get("title", ""), "description": (info.get("description", "") or "")[:2000], "channel": info.get("channel", "")} if info else {}

    def _download_subtitle_only_module(self, url):
        def cancel(_):
            if self.is_cancelled():
                raise InterruptedError("Stopped")
        options = self._subtitle_options()
        options["progress_hooks"] = [cancel]
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(url, download=True)
        except Exception as exc:
            if "403" in str(exc) or "Forbidden" in str(exc):
                raise RuntimeError("YouTube menolak akses subtitle. Perbarui cookies.txt.") from exc
            self.log("  Subtitle unavailable, will transcribe locally")
            return None, {}
        subtitle = self.temp_dir / f"source.{self.subtitle_language}.srt"
        return (str(subtitle) if subtitle.is_file() else None), self._video_info(info)

    def _download_subtitle_only_subprocess(self, url):
        cookies = self._cookies_path()
        metadata = [self.ytdlp_path, "--dump-json", "--no-download"]
        if cookies:
            metadata.extend(["--cookies", str(cookies)])
        metadata.append(url)
        result = subprocess.run(metadata, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS, timeout=30)
        try:
            info = self._video_info(json.loads(result.stdout)) if result.returncode == 0 else {}
        except json.JSONDecodeError:
            info = {}
        command = [self.ytdlp_path, "--skip-download", "--write-sub", "--write-auto-sub", "--sub-lang", self.subtitle_language, "--convert-subs", "srt", "-o", str(self.temp_dir / "source.%(ext)s")]
        if cookies:
            command.extend(["--cookies", str(cookies)])
        result = self._run_cancelable_subprocess([*command, url], capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS, timeout=900)
        if result.returncode:
            if "403" in result.stderr or "Forbidden" in result.stderr:
                raise RuntimeError("YouTube menolak akses subtitle. Perbarui cookies.txt.")
            return None, info
        subtitle = self.temp_dir / f"source.{self.subtitle_language}.srt"
        return (str(subtitle) if subtitle.is_file() else None), info

    def download_video_section(self, url, start_time, end_time, output_path):
        start = start_time.replace(",", ".")
        end = end_time.replace(",", ".")
        started = time.monotonic()
        try:
            if YTDLP_MODULE_AVAILABLE and self.ytdlp_path == "yt_dlp_module":
                return self._download_section_module(url, start, end, output_path)
            return self._download_section_subprocess(url, start, end, output_path)
        finally:
            self.log(f"  Section download elapsed: {time.monotonic() - started:.1f}s")

    def _download_section_module(self, url, start_time, end_time, output_path):
        def progress_hook(status):
            if self.is_cancelled():
                raise InterruptedError("Stopped")
            match = re.search(r"(\d+\.?\d*)%", status.get("_percent_str", "")) if status.get("status") == "downloading" else None
            if match:
                self.set_progress(f"Downloading video section... {match.group(1)}%", 0.32 + float(match.group(1)) / 100 * 0.08)
        options = self._apply_common_ytdlp_options({
            "format": self._format_selector(),
            "format_sort": self._format_sort(),
            "format_sort_force": True,
            "merge_output_format": "mp4",
            "outtmpl": output_path,
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": False,
            "download_ranges": yt_dlp.utils.download_range_func(None, [(self.parse_timestamp(start_time), self.parse_timestamp(end_time))]),
            'concurrent_fragment_downloads': 4,
            "fragment_retries": 5,
            "retries": 5,
        })
        with yt_dlp.YoutubeDL(options) as downloader:
            downloader.download([url])
        return self._find_output(Path(output_path).stem, {".mp4", ".mkv", ".webm"}, output_path)

    def _download_section_subprocess(self, url, start_time, end_time, output_path):
        command = [self.ytdlp_path, "-f", self._format_selector(), "--format-sort", ",".join(self._format_sort()), "--format-sort-force", "--download-sections", f"*{start_time}-{end_time}", "--concurrent-fragments", "4", "--fragment-retries", "5", "--retries", "5", "--newline", "--merge-output-format", "mp4", "-o", output_path]
        if cookies := self._cookies_path():
            command.extend(["--cookies", str(cookies)])
        process = subprocess.Popen([*command, url], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=SUBPROCESS_FLAGS)
        lines = []
        for line in process.stdout or []:
            if self.is_cancelled():
                process.terminate()
                raise InterruptedError("Stopped")
            lines.append(line.strip())
            match = re.search(r"(\d+\.?\d*)%", line) if "[download]" in line else None
            if match:
                self.set_progress(f"Downloading video section... {match.group(1)}%", 0.32 + float(match.group(1)) / 100 * 0.08)
        if process.wait() != 0:
            raise RuntimeError(f"Failed to download video section:\n{' '.join(lines[-20:])[-400:]}")
        return self._find_output(Path(output_path).stem, {".mp4", ".mkv", ".webm"}, output_path)

    def _find_output(self, stem, suffixes, exact=None):
        if exact and Path(exact).is_file():
            return str(exact)
        for candidate in self.temp_dir.glob(f"{stem}.*"):
            if candidate.suffix.lower() in suffixes:
                return str(candidate)
        raise RuntimeError(f"Downloaded output not found: {stem}")

    def parse_srt_timed(self, srt_path):
        content = Path(srt_path).read_text(encoding="utf-8-sig")
        timestamp = r"(\d{1,}):(\d{2}):(\d{2})[,.](\d{1,3})"
        pattern = re.compile(rf"^\s*{timestamp}\s*-->\s*{timestamp}(?:\s+.*)?$")

        def seconds(parts):
            hours, minutes, value, milliseconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + int(value) + int(milliseconds.ljust(3, "0")[:3]) / 1000

        segments = []
        for block in re.split(r"\n\s*\n", content.strip()):
            lines = block.splitlines()
            if lines and lines[0].strip().isdigit():
                lines = lines[1:]
            if not lines or not (match := pattern.match(lines[0])):
                continue
            text = " ".join(line.strip() for line in lines[1:] if line.strip())
            if text:
                segments.append({"text": text, "start": seconds(match.groups()[:4]), "end": seconds(match.groups()[4:])})
        if not segments:
            raise ValueError("SRT contains no valid subtitle segments")
        return validate_timed_transcript({"duration": max(item["end"] for item in segments), "words": [], "segments": segments})
