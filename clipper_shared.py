import math
import subprocess
import sys
from typing import TypedDict


class TimedWord(TypedDict):
    word: str
    start: float
    end: float


class TimedSegment(TypedDict):
    text: str
    start: float
    end: float


class TimedTranscript(TypedDict):
    duration: float
    words: list[TimedWord]
    segments: list[TimedSegment]


def _timestamp(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    value = float(value)
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return value


def _timed_items(items, text_key):
    if not isinstance(items, list):
        raise ValueError(f"{text_key} items must be a list")
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{text_key} item must be a dictionary")
        text = item.get(text_key)
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{text_key} must not be empty")
        start = _timestamp(item.get("start"), "start")
        end = _timestamp(item.get("end"), "end")
        if end <= start:
            raise ValueError("end must be greater than start")
        normalized.append({text_key: text, "start": start, "end": end})
    return sorted(normalized, key=lambda item: (item["start"], item["end"]))


def validate_timed_transcript(transcript: TimedTranscript, require_words: bool = False) -> TimedTranscript:
    if not isinstance(transcript, dict):
        raise ValueError("transcript must be a dictionary")
    duration = _timestamp(transcript.get("duration"), "duration")
    words = _timed_items(transcript.get("words"), "word")
    segments = _timed_items(transcript.get("segments"), "text")
    if require_words and not words:
        raise ValueError("word timestamps are required")
    return {"duration": duration, "words": words, "segments": segments}


def _format_timestamp(seconds):
    total_milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(total_milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def timed_segments_to_prompt(transcript: TimedTranscript) -> str:
    transcript = validate_timed_transcript(transcript)
    return "\n".join(
        f"[{_format_timestamp(item['start'])} - {_format_timestamp(item['end'])}] {item['text']}"
        for item in transcript["segments"]
    )


def slice_timed_transcript(transcript: TimedTranscript, start: float, end: float) -> TimedTranscript:
    transcript = validate_timed_transcript(transcript)
    start = _timestamp(start, "start")
    end = _timestamp(end, "end")
    if end <= start:
        raise ValueError("end must be greater than start")

    def sliced(items, text_key):
        result = []
        for item in items:
            if item["end"] <= start or item["start"] >= end:
                continue
            item_start = round(max(item["start"], start) - start, 3)
            item_end = round(min(item["end"], end) - start, 3)
            if item_end > item_start:
                result.append({text_key: item[text_key], "start": item_start, "end": item_end})
        return result

    return {
        "duration": round(end - start, 3),
        "words": sliced(transcript["words"], "word"),
        "segments": sliced(transcript["segments"], "text"),
    }


SUBPROCESS_FLAGS = 0
if sys.platform == "win32":
    SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW

try:
    import yt_dlp
    YTDLP_MODULE_AVAILABLE = True
except ImportError:
    yt_dlp = None
    YTDLP_MODULE_AVAILABLE = False


class SubtitleNotFoundError(Exception):
    def __init__(self, message: str, video_path: str = None, video_info: dict = None, session_dir: str = None):
        super().__init__(message)
        self.video_path = video_path
        self.video_info = video_info or {}
        self.session_dir = session_dir


def _hex_to_rgb(hex_color: str):
    if not isinstance(hex_color, str):
        return (255, 255, 255)
    value = hex_color.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    if len(value) != 6:
        return (255, 255, 255)
    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return (255, 255, 255)
