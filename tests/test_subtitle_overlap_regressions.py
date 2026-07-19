from clipper_shared import TimedTranscript, TimedWord
from config.editor_defaults import SUBTITLE_WORD_MAX
from subtitle_cues import build_subtitle_cues
from visual_style import sanitize_subtitle_token


def _transcript(words: list[TimedWord]) -> TimedTranscript:
    return {"duration": max(word["end"] for word in words), "words": words, "segments": []}


def test_hyphenated_repeated_words_keep_lexical_boundary():
    assert sanitize_subtitle_token("temen-temen") == "temen temen"
    assert sanitize_subtitle_token("tiba-tiba") == "tiba tiba"


def test_overlap_at_cue_boundary_does_not_drop_transcript_word():
    transcript = _transcript([
        {"word": "satu", "start": 0.0, "end": 0.1},
        {"word": "dua", "start": 0.1, "end": 0.2},
        {"word": "wah", "start": 0.2, "end": 0.5},
        {"word": "empat", "start": 0.2, "end": 0.6},
    ])

    cues = build_subtitle_cues(transcript)

    assert [word["text"] for cue in cues for word in cue["words"]] == ["SATU", "DUA", "WAH", "EMPAT"]
    assert all(cue["end"] <= next_cue["start"] for cue, next_cue in zip(cues, cues[1:]))


def test_word_cap_counts_words_inside_provider_token():
    transcript = _transcript([
        {"word": "ke investment", "start": 0.0, "end": 0.4},
        {"word": "juga", "start": 0.4, "end": 0.6},
        {"word": "nih", "start": 0.6, "end": 0.8},
    ])

    cues = build_subtitle_cues(transcript)

    assert all(len(cue["text"].split()) <= SUBTITLE_WORD_MAX for cue in cues)


def test_renderer_layer_does_not_invent_glued_or_sequential_repeat_tokens():
    transcript = _transcript([
        {"word": "alditanya", "start": 0.0, "end": 0.2},
        {"word": "Allah", "start": 0.2, "end": 0.4},
        {"word": "Allah", "start": 0.4, "end": 0.6},
    ])

    cues = build_subtitle_cues(transcript)

    assert [word["text"] for word in cues[0]["words"]] == ["ALDITANYA", "ALLAH", "ALLAH"]
    assert cues[0]["text"] == "ALDITANYA ALLAH ALLAH"
    assert all(len(cue["active_word_indexes"]) == len(cue["words"]) for cue in cues)


def test_exact_overlapping_duplicate_provider_token_is_collapsed():
    transcript = _transcript([
        {"word": "bentar!", "start": 0.0, "end": 0.88},
        {"word": "bentar!", "start": 0.04, "end": 0.86},
        {"word": "lanjut", "start": 0.88, "end": 1.0},
    ])

    cues = build_subtitle_cues(transcript)

    assert [word["text"] for cue in cues for word in cue["words"]] == ["BENTAR!", "LANJUT"]


def test_tail_word_survives_overlap_with_next_cue():
    transcript = _transcript([
        {"word": "awal", "start": 0.0, "end": 0.1},
        {"word": "masih", "start": 0.1, "end": 0.2},
        {"word": "ada", "start": 0.2, "end": 0.9},
        {"word": "tail", "start": 0.2, "end": 1.0},
        {"word": "tetap", "start": 1.0, "end": 1.2},
        {"word": "utuh", "start": 1.2, "end": 1.4},
    ])

    cues = build_subtitle_cues(transcript)

    assert [word["text"] for cue in cues for word in cue["words"]] == [
        "AWAL", "MASIH", "ADA", "TAIL", "TETAP", "UTUH",
    ]
    assert cues[-1]["end"] == 1.4
