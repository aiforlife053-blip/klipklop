from typing import Literal, TypedDict

from clipper_shared import TimedTranscript, validate_timed_transcript
from config.editor_defaults import SUBTITLE_WORD_MAX, SUBTITLE_WORD_MIN
from visual_style import sanitize_subtitle_text, sanitize_subtitle_token


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


def build_subtitle_cues(transcript: TimedTranscript, text_transform: str = "uppercase") -> list[SubtitleCue]:
    transcript = validate_timed_transcript(transcript)
    if not transcript["words"]:
        cues = []
        for segment in non_overlapping_segments(transcript["segments"]):
            words = _transform(sanitize_subtitle_text(segment["text"]), text_transform).split()
            chunks = [words[index:index + SUBTITLE_WORD_MAX] for index in range(0, len(words), SUBTITLE_WORD_MAX)]
            duration = float(segment["end"]) - float(segment["start"])
            for index, chunk in enumerate(chunks):
                start = float(segment["start"]) + duration * index / len(chunks)
                end = float(segment["start"]) + duration * (index + 1) / len(chunks)
                cues.append({
                    "start": start, "end": end, "text": " ".join(chunk),
                    "words": [], "active_word_indexes": [], "capability": "static_segments",
                })
        return cues
    words = []
    for word in sorted(transcript["words"], key=lambda item: (item["start"], item["end"])):
        text = _transform(sanitize_subtitle_token(word["word"]), text_transform)
        if not text:
            continue
        words.append({"text": text, "start": word["start"], "end": word["end"]})
    chunks, chunk = [], []
    word_min = max(1, int(SUBTITLE_WORD_MIN))
    word_max = max(word_min, int(SUBTITLE_WORD_MAX))
    for index, word in enumerate(words):
        chunk.append(word)
        next_word = words[index + 1] if index + 1 < len(words) else None
        remaining = len(words) - index - 1
        # Groups of 3–4 words; no punctuation breakers (? , . stripped).
        should_flush = len(chunk) >= word_min and (
            not next_word
            or next_word["start"] - word["end"] > 0.45
            or len(chunk) >= word_max
            or (remaining == 0)
        )
        # Avoid leaving a dangling 1-word remainder when possible.
        if should_flush and next_word and remaining == 1 and len(chunk) < word_max:
            should_flush = False
        if should_flush:
            chunks.append(chunk)
            chunk = []
    if chunk:
        chunks.append(chunk)
    cues: list[SubtitleCue] = []
    for chunk in chunks:
        cue_start, cue_end = chunk[0]["start"], chunk[-1]["end"]
        cue_words = [
            {
                "text": word["text"],
                "start": word["start"],
                "end": word["end"],
                "active_from": word["start"],
                "active_until": chunk[index + 1]["start"] if index < len(chunk) - 1 else cue_end,
            }
            for index, word in enumerate(chunk)
        ]
        cues.append(
            {
                "start": cue_start,
                "end": cue_end,
                "text": " ".join(word["text"] for word in chunk),
                "words": cue_words,
                "active_word_indexes": list(range(len(cue_words))),
                "capability": "word_highlight",
            }
        )
    # Raw Whisper word ranges may overlap. Clamp adjacent cue/event boundaries
    # so ASS never draws two full subtitle lines at the same timestamp.
    for index in range(len(cues) - 1):
        next_start = float(cues[index + 1]["start"])
        cues[index]["end"] = min(float(cues[index]["end"]), next_start)
        if cues[index]["words"]:
            cues[index]["words"][-1]["active_until"] = cues[index]["end"]
        gap = next_start - float(cues[index]["end"])
        if 0 < gap <= 0.75:
            cues[index]["end"] = next_start
            if cues[index]["words"]:
                cues[index]["words"][-1]["active_until"] = cues[index]["end"]
    normalized_cues = []
    for cue in cues:
        normalized_words = []
        cursor = float(cue["start"])
        for word in cue["words"]:
            active_from = max(cursor, float(cue["start"]), float(word["active_from"]))
            active_until = min(float(cue["end"]), float(word["active_until"]))
            if active_until - active_from < 0.01:
                continue
            normalized_words.append({**word, "active_from": active_from, "active_until": active_until})
            cursor = active_until
        if not normalized_words:
            continue
        cue["words"] = normalized_words
        cue["text"] = " ".join(word["text"] for word in normalized_words)
        cue["active_word_indexes"] = list(range(len(normalized_words)))
        normalized_cues.append(cue)
    return normalized_cues
