"""V3 hook/subtitle text normalization helpers."""
from __future__ import annotations

import re

from config.editor_defaults import HOOK_MAX_LINES, HOOK_MAX_WORDS

_WORD_RE = re.compile(r"\S+")
_ALLOWED_PUNCT = set("?!,")


def normalize_hook_text(text: str, max_words: int = HOOK_MAX_WORDS, max_lines: int = HOOK_MAX_LINES) -> str:
    """Force Indonesian-style short hook: max words, max 2 lines, whole-word cut."""
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    if not cleaned:
        return "Momen ini wajib ditonton"
    words = _WORD_RE.findall(cleaned)
    words = words[: max(1, int(max_words))]
    if len(words) <= 4 or max_lines <= 1:
        return " ".join(words)
    # Prefer balanced 2-line split near middle
    split_at = max(1, min(len(words) - 1, (len(words) + 1) // 2))
    line1 = " ".join(words[:split_at])
    line2 = " ".join(words[split_at:])
    return f"{line1}\n{line2}"


def sanitize_subtitle_token(token: str) -> str:
    """Keep letters/numbers plus only ? ! , punctuation."""
    text = str(token or "")
    out = []
    for ch in text:
        if ch.isalnum() or ch.isspace() or ch in _ALLOWED_PUNCT:
            out.append(ch)
        elif ch in {".", ";", ":", "\"", "'", "“", "”", "‘", "’", "-", "—", "…"}:
            continue
        # drop other symbols
    return "".join(out)


def sanitize_subtitle_text(text: str) -> str:
    parts = [sanitize_subtitle_token(part) for part in str(text or "").split()]
    return " ".join(part for part in parts if part).strip()
