from typing import Literal, TypedDict

from clipper_shared import TimedTranscript, validate_timed_transcript


class CueWord(TypedDict):
    text: str
    start: float
    end: float
    active_from: float
    active_until: float


class SubtitleCue(TypedDict):
    start: float
    end: float
    text: str
    words: list[CueWord]
    active_word_indexes: list[int]
    capability: Literal["word_highlight", "static_segments"]


def _transform(text: str, transform: str) -> str:
    transform = str(transform or "none").lower()
    if transform == "uppercase":
        return text.upper()
    if transform == "lowercase":
        return text.lower()
    if transform == "capitalize":
        return text.title()
    return text


def non_overlapping_segments(segments):
    by_start = {}
    for segment in segments:
        by_start[round(segment["start"], 3)] = segment
    ordered = [by_start[start] for start in sorted(by_start)]
    result = []
    for index, segment in enumerate(ordered):
        next_start = ordered[index + 1]["start"] if index + 1 < len(ordered) else segment["end"]
        end = min(segment["end"], next_start)
        if end > segment["start"]:
            result.append({**segment, "end": end})
    return result


def build_subtitle_cues(transcript: TimedTranscript, text_transform: str = "none") -> list[SubtitleCue]:
    transcript = validate_timed_transcript(transcript)
    if not transcript["words"]:
        return [{"start": segment["start"], "end": segment["end"], "text": _transform(segment["text"], text_transform), "words": [], "active_word_indexes": [], "capability": "static_segments"} for segment in non_overlapping_segments(transcript["segments"])]
    words = [{"text": _transform(word["word"], text_transform), "start": word["start"], "end": word["end"]} for word in transcript["words"]]
    chunks, chunk = [], []
    for index, word in enumerate(words):
        chunk.append(word)
        next_word = words[index + 1] if index + 1 < len(words) else None
        remaining = len(words) - index - 1
        should_flush = len(chunk) >= 3 and (not next_word or word["text"].rstrip().endswith((".", ",", "?", "!")) or next_word["start"] - word["end"] > 0.45 or len(chunk) >= (4 if remaining == 3 else 5))
        if should_flush:
            chunks.append(chunk)
            chunk = []
    if chunk:
        chunks.append(chunk)
    cues: list[SubtitleCue] = []
    for chunk in chunks:
        cue_start, cue_end = chunk[0]["start"], chunk[-1]["end"]
        cue_words = [{"text": word["text"], "start": word["start"], "end": word["end"], "active_from": cue_start if index == 0 else chunk[index - 1]["end"], "active_until": word["end"] if index < len(chunk) - 1 else cue_end} for index, word in enumerate(chunk)]
        cues.append({"start": cue_start, "end": cue_end, "text": " ".join(word["text"] for word in chunk), "words": cue_words, "active_word_indexes": list(range(len(cue_words))), "capability": "word_highlight"})
    return cues
