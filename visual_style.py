"""V3 hook/subtitle text normalization helpers."""
from __future__ import annotations

import re
import unicodedata

from config.editor_defaults import HOOK_MAX_LINES, HOOK_MAX_WORDS

_WORD_RE = re.compile(r"\S+")
_ALLOWED_SUBTITLE_PUNCT = set("!")
# Legacy "Name: body" — keep only for cleanup, not as preferred generate format.
_HOOK_NAME_SPLIT_RE = re.compile(r"^(.{1,48}?)\s*:\s+(.+)$", re.DOTALL)
_HOOK_MARKED_NAME_RE = re.compile(r"\[([^\[\]]{1,48})\]")
_TITLE_NAME_RE = re.compile(
    r"\b((?:DR|DOKTER|PAK|BU|IBU|MAS|MBAK|PROF|USTADZ?|KYAI)\.?\s+[A-Za-z][A-Za-z.'-]{1,24})\b",
    re.IGNORECASE,
)

def marked_hook_name(text: str) -> str:
    """Person name marked by AI as [Name]; markers are internal only."""
    match = _HOOK_MARKED_NAME_RE.search(str(text or ""))
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def strip_hook_colon(text: str) -> str:
    """Strip internal name markers and legacy 'Name: body' colon."""
    cleaned = _HOOK_MARKED_NAME_RE.sub(r"\1", str(text or ""))
    cleaned = re.sub(r"\s+", " ", cleaned.strip())
    if not cleaned:
        return ""
    match = _HOOK_NAME_SPLIT_RE.match(cleaned)
    if not match:
        return cleaned
    name, body = match.group(1).strip(), match.group(2).strip()
    name_words = name.split()
    if not name or not body or len(name_words) > 5 or re.fullmatch(r"[\d\W]+", name):
        return cleaned.replace(":", " ")
    return f"{name} {body}"


def split_hook_name_body(text: str) -> tuple[str, str]:
    """Legacy helper: (name, body) if 'Name: body', else ('', full)."""
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    if not cleaned:
        return "", ""
    match = _HOOK_NAME_SPLIT_RE.match(cleaned)
    if not match:
        return "", cleaned
    name, body = match.group(1).strip(), match.group(2).strip()
    if not name or not body:
        return "", cleaned
    name_words = name.split()
    if len(name_words) > 5 or re.fullmatch(r"[\d\W]+", name):
        return "", cleaned
    return name, body


def normalize_generated_hook_text(text: str, max_words: int = HOOK_MAX_WORDS) -> str:
    """Validate AI hook while preserving its required inline name marker."""
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    name = marked_hook_name(cleaned)
    if not name:
        raise ValueError("Hook AI wajib menandai nama orang dengan [NAMA]")
    if name.strip().upper() in {"NAMA", "NAMA ORANG", "NAME", "PERSON"}:
        raise ValueError("Hook AI wajib memakai nama orang nyata, bukan placeholder")
    cleaned = re.sub(
        r"^(\[[^\[\]]+\])\s+SEBUT\s+ISI\s+(\S+)\s+(.+)$",
        r"\1 BILANG \2 BERISI \3",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^(\[[^\[\]]+\])\s+SEBUT\s+(\S+)\s+BERISI\s+(.+)$",
        r"\1 BILANG \2 BERISI \3",
        cleaned,
        flags=re.IGNORECASE,
    )
    words = _WORD_RE.findall(strip_hook_colon(cleaned))
    if not words or len(words) > max(1, int(max_words)):
        raise ValueError(f"Hook AI maksimal {max_words} kata")
    return cleaned.upper()


def normalize_hook_text(text: str, max_words: int = HOOK_MAX_WORDS, max_lines: int = HOOK_MAX_LINES) -> str:
    """One uppercase sentence; strip legacy colon; wrap ≤ max_lines."""
    cleaned = strip_hook_colon(text)
    laughing = "🤣" in cleaned
    cleaned = "".join(ch for ch in cleaned if not unicodedata.category(ch).startswith(("S", "C")))
    if not cleaned:
        return "MOMEN INI WAJIB DITONTON!"
    words = _WORD_RE.findall(cleaned)
    words = words[: max(1, int(max_words))]
    if not words[-1].endswith(("?", "!")):
        words[-1] += "!"
    plain = " ".join(words).upper()
    max_lines = max(1, int(max_lines))
    if len(words) <= 1 or max_lines <= 1:
        return plain
    n = len(words)
    lines = max_lines
    base = n // lines
    rem = n % lines
    chunks = []
    idx = 0
    for line_i in range(lines):
        take = base + (1 if line_i < rem else 0)
        if take <= 0:
            continue
        chunks.append(" ".join(words[idx:idx + take]).upper())
        idx += take
    chunks = [c for c in chunks if c]
    rendered = "\n".join(chunks)
    return f"{rendered} 🤣" if laughing else rendered


def validate_hook_text(text: str) -> str:
    """Validate user-authored hooks while preserving an inline name marker."""
    raw = str(text or "").strip()
    cleaned = "".join(ch for ch in strip_hook_colon(raw) if not unicodedata.category(ch).startswith(("S", "C")))
    words = _WORD_RE.findall(cleaned)
    if not words:
        raise ValueError("Hook text kosong")
    if len(words) > HOOK_MAX_WORDS:
        raise ValueError(f"Hook maksimal {HOOK_MAX_WORDS} kata")
    if marked_hook_name(raw):
        return re.sub(r"\s+", " ", raw).upper()
    return normalize_hook_text(cleaned)


def hook_name_from_title(hook_text: str, title: str) -> str:
    """Infer a leading person name repeated by both AI hook and clip title."""
    hook_words = normalize_hook_text(hook_text).replace("\n", " ").split()
    title_words = normalize_hook_text(title).replace("\n", " ").split()
    shared = []
    for hook_word, title_word in zip(hook_words, title_words):
        if _hook_token_key(hook_word) != _hook_token_key(title_word) or len(shared) >= 3:
            break
        shared.append(hook_word)
    non_name_leads = {"KETIKA", "TERNYATA", "DETIKDETIK", "MOMEN", "ALASAN", "FAKTA", "AKHIRNYA"}
    # Without an explicit AI marker, only a two-token shared prefix is strong
    # enough evidence. Longer generic shared phrases are not person names.
    if len(shared) != 2 or _hook_token_key(shared[0]) in non_name_leads:
        return ""
    return " ".join(shared)


def hook_tts_text(text: str) -> str:
    """Spoken hook: same words as overlay, single line, no colon."""
    return re.sub(r"\s+", " ", normalize_hook_text(text).replace("\n", " ")).strip()


def candidate_hook_names(text: str, known_names=None) -> list[str]:
    """Ordered name candidates to highlight inside the hook sentence."""
    names = []
    marked = marked_hook_name(text)
    if marked:
        names.append(marked.upper())
    for raw in list(known_names or []):
        cleaned = re.sub(r"\s+", " ", str(raw or "").strip())
        cleaned = re.sub(r"^@+", "", cleaned)
        if cleaned:
            names.append(cleaned.upper())
    # Legacy colon prefix still a strong signal for which tokens are the name.
    legacy_name, _ = split_hook_name_body(text)
    if legacy_name:
        names.append(legacy_name.upper())
    # Common Indonesian honorific + name when AI marker already stripped.
    for match in _TITLE_NAME_RE.finditer(str(text or "")):
        names.append(re.sub(r"\s+", " ", match.group(1)).strip().upper())
    # Prefer longer names first for matching.
    uniq = []
    seen = set()
    for name in sorted(names, key=lambda value: (-len(value.split()), -len(value))):
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(name)
    return uniq


def _hook_token_key(token: str) -> str:
    """Compare hook tokens ignoring trailing punctuation like DR. vs DR"""
    return re.sub(r"[^\w]+$", "", str(token or "").upper())


def find_hook_name_span(words: list[str], known_names=None, original_text: str = "") -> tuple[int, int] | None:
    """Return [start, end) word indices of the first matched person name in uppercase words."""
    if not words:
        return None
    upper_words = [str(word).upper() for word in words]
    keys = [_hook_token_key(word) for word in upper_words]
    for name in candidate_hook_names(original_text or " ".join(upper_words), known_names):
        name_words = [_hook_token_key(part) for part in name.split() if _hook_token_key(part)]
        if not name_words or len(name_words) > len(keys):
            continue
        for start in range(0, len(keys) - len(name_words) + 1):
            if keys[start:start + len(name_words)] == name_words:
                return start, start + len(name_words)
    return None


def sanitize_subtitle_token(token: str) -> str:
    """Keep letters/numbers/! and ASS-relevant symbols; strip ? , . and quotes/dashes."""
    text = str(token or "")
    out = []
    for ch in text:
        if ch.isalnum() or ch.isspace() or ch in _ALLOWED_SUBTITLE_PUNCT or ch in {"\\", "{", "}"}:
            out.append(ch)
        elif ch in {"-", "—"}:
            out.append(" ")
        elif ch in {".", ",", "?", ";", ":", "\"", "'", "“", "”", "‘", "’", "…"}:
            continue
        # drop other symbols
    return "".join(out)


def sanitize_subtitle_text(text: str) -> str:
    parts = [sanitize_subtitle_token(part) for part in str(text or "").split()]
    return " ".join(part for part in parts if part).strip()
