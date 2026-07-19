import json
import math
import mimetypes
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

from clipper_shared import SUBPROCESS_FLAGS, SubtitleNotFoundError, TimedTranscript, timed_segments_to_prompt, validate_timed_transcript
from clipper_base import ClipperBase
from config.editor_defaults import HARD_CLIP_MAX, HARD_CLIP_MIN, TARGET_CLIP_MAX, TARGET_CLIP_MIN
from visual_style import normalize_generated_hook_text, normalize_hook_text

# V3 clip duration contract (seconds)
MIN_CLIP_DURATION = HARD_CLIP_MIN
MAX_CLIP_DURATION = HARD_CLIP_MAX
MAX_GROQ_UPLOAD_BYTES = 20 * 1024 * 1024


def ensure_five_hashtags(description: str, *context: str) -> str:
    text = str(description or "").strip()
    tags = []
    for tag in re.findall(r"(?<!\w)#[\w]+", text, flags=re.UNICODE):
        normalized = "#" + re.sub(r"[^\w]", "", tag[1:], flags=re.UNICODE)
        if len(normalized) > 1 and normalized.casefold() not in {item.casefold() for item in tags}:
            tags.append(normalized)
    body = re.sub(r"(?<!\w)#[\w]+", "", text, flags=re.UNICODE).strip()
    stopwords = {"yang", "dan", "atau", "dari", "untuk", "dengan", "jadi", "ini", "itu", "ada", "karena", "saat", "bikin", "akhirnya"}
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+", " ".join(context), flags=re.UNICODE)
    for word in words:
        clean = re.sub(r"[^\w]", "", word, flags=re.UNICODE)
        if len(clean) < 4 or clean.casefold() in stopwords:
            continue
        tag = "#" + clean.title()
        if tag.casefold() not in {item.casefold() for item in tags}:
            tags.append(tag)
        if len(tags) == 5:
            break
    for tag in ("#Shorts", "#PodcastIndonesia", "#KlipViral", "#VideoViral", "#KontenIndonesia"):
        if tag.casefold() not in {item.casefold() for item in tags}:
            tags.append(tag)
        if len(tags) == 5:
            break
    return f"{body}\n\n{' '.join(tags[:5])}".strip()


class AiMixin(ClipperBase):
    def get_default_prompt(self=None):
        """Get default system prompt for highlight detection"""
        return """Kamu adalah EDITOR SHORT-FORM TIER A untuk konten PODCAST viral (TikTok / Reels / Shorts).

OUTPUT ANDA AKAN LANGSUNG DIGUNAKAN UNTUK PRODUKSI.
Kesalahan durasi atau format = GAGAL TOTAL.

==================================================
TUGAS UTAMA (NON-NEGOTIABLE)
============================

Dari transcript di bawah, HASILKAN TEPAT {num_clips} segment.

* TIDAK BOLEH kurang.
* TIDAK BOLEH lebih.
* ARRAY KOSONG DILARANG DALAM KONDISI APAPUN.

Jika kesulitan menemukan segmen bagus, WAJIB tetap menghasilkan {num_clips} dengan strategi penggabungan/perpanjangan.

==================================================
PRINSIP PEMILIHAN CLIP (WAJIB DIPRIORITASKAN)
=============================================

PRIORITAS UTAMA: cari MOMEN LUCU, punchline, reaksi spontan, atau kejadian komedi yang jelas terlebih dahulu.
URUTAN ARRAY WAJIB mengikuti prioritas ini: semua momen lucu yang layak harus berada sebelum konflik, pengakuan, opini, atau edukasi. Object pertama WAJIB momen lucu terbaik jika transcript memiliki satu saja momen lucu yang layak.
Jika tidak ada momen lucu yang layak dan kontekstual, baru gunakan fallback berikut:

1. Ada KONFLIK, ketegangan, kontroversi.
2. Ada PENGAKUAN personal / vulnerability.
3. Ada STATEMENT tajam / opini berani.
4. Ada cerita lengkap (setup → buildup → payoff).
5. Ada kalimat yang bisa berdiri sendiri sebagai hook viral.

Hindari:

* Obrolan filler
* Basa-basi
* Transisi topik tanpa payoff
* Penjelasan teknis panjang tanpa emosi

Jika harus memilih, utamakan EMOSI & KONFLIK dibanding edukasi netral.

==================================================
ATURAN DURASI (KRITIS – TIDAK BOLEH DILANGGAR)
==============================================

* Target durasi tiap clip: 50–70 detik.
* Minimum absolut: 40 detik.
* Maksimum absolut: 70 detik.
* Hitung durasi dari timestamp transcript.
* JANGAN estimasi berdasarkan panjang teks.

Jika momen inti < 50 detik:
→ PERPANJANG konteks sebelum/sesudah sampai 50–70 detik.

Jika momen inti < 40 detik:
→ PERPANJANG minimal sampai 40 detik (target tetap 50–70).

Jika durasi > 70 detik:
→ Pangkas bagian yang tidak relevan TANPA merusak alur cerita.

==================================================
STRATEGI WAJIB JIKA SEGMENT IDEAL TIDAK ADA
===========================================

Lakukan salah satu atau kombinasi berikut:

1. Gabungkan beberapa bagian berurutan yang masih satu topik.
2. Tambahkan setup sebelum punchline agar dramatis.
3. Tambahkan payoff setelah cerita agar terasa lengkap.
4. Pangkas filler tapi jaga alur cerita tetap utuh.

DILARANG:

* Menghasilkan clip < 40 detik
* Mengurangi jumlah clip
* Mengabaikan timestamp asli
* Mengarang timestamp

==================================================
STRUKTUR NARATIF YANG DIWAJIBKAN
================================

Setiap clip harus terasa seperti mini-story:

• Awal: Setup / pernyataan pemicu
• Tengah: Konflik / insight / cerita
• Akhir: Punchline / payoff / statement kuat

Jika tidak ada payoff, tambahkan konteks hingga ada.

==================================================
FIELD WAJIB (PERSIS 6 FIELD – TIDAK BOLEH LEBIH/KURANG)
=======================================================

Setiap object HARUS memiliki:

1. "start_time" (string) → Format: "HH:MM:SS,mmm"
2. "end_time" (string) → Format: "HH:MM:SS,mmm"
3. "title" (string) → Maks 60 karakter, padat & click-worthy
4. "description" (string) → Maks 150 karakter, jelaskan kenapa viral
5. "virality_score" (integer) → 1–10 (HARUS ANGKA, BUKAN STRING)
6. "hook_text" (string) → Bahasa Indonesia, maksimal 6 kata; nama orang wajib ada dan ditandai [NAMA]; gunakan headline deklaratif kontekstual

Jika segment termasuk momen lucu/komedi, awali description dengan marker internal "[LUCU] ". Marker wajib untuk setiap momen lucu dan dilarang untuk non-komedi. Marker akan dibuang sebelum ditampilkan.

DILARANG:

* Field tambahan
* Field "reason"
* virality_score dalam bentuk string
* Komentar atau teks di luar JSON

==================================================
VIRALITY SCORE (WAJIB OBJEKTIF)
===============================

8–10:

* Kontroversial
* Emosional kuat
* Confession pribadi
* Statement berani
* Punchline keras
* Momen lucu yang jelas, reaksi spontan, atau payoff komedi

5–7:

* Insight menarik
* Cerita cukup engaging
* Insight menarik tanpa emosi kuat

1–4:

* Informasi biasa
* Tidak ada emosi
* Tidak ada hook kuat

Jangan kasih semua clip skor tinggi.
Nilai dengan rasional.

==================================================
HOOK TEXT (HARUS TAJAM & MENJUAL)
=================================

WAJIB:

* Bahasa Indonesia
* Maksimal 6 kata
* Tanpa emoji
* WAJIB berupa headline deklaratif, bukan kalimat tanya
* WAJIB satu kalimat utuh, natural, dan enak dibaca
* Nama orang wajib ada, tetapi nama boleh berada di posisi mana pun dalam kalimat
* Nama sedikit lebih besar dan cyan; isi lain putih
* Tandai hanya nama orang dengan kurung siku agar render bisa mewarnainya; kurung tidak tampil dan tidak dibaca TTS
* Jangan merangkai potongan transcript yang tidak membentuk kalimat utuh
* Harus memberi konteks inti klip, bukan curiosity gap kosong
* Kata penentu konteks bersifat opsional: sering, selalu, berulang kali, pertama kali, diam-diam, hampir, atau kata setara
* DILARANG menambah kata penentu konteks jika tidak dinyatakan atau tidak didukung transcript
* Jika kata tersebut didukung transcript dan penting bagi makna, pertahankan; jika tidak penting, jangan dipaksakan
* Bisa berupa statement tajam atau punchline

Contoh benar:
"ALASAN [ALDI TAHER] SERING TERLAMBAT"
"[RADITYA DIKA] KEBANYAKAN BACA HARUS FISIOTERAPI"

Contoh salah:
"RADITYA DIKA: GUA HAMPIR BANGKRUT"
"KENAPA [ALDI TAHER] TELAT TERUS?" — kalimat tanya tanpa konteks
"[ALDI TAHER] UNGKAP ALASAN TERLAMBAT" — menghilangkan konteks bahwa kejadian sering berulang

Hook harus bisa berdiri sendiri sebagai headline viral.

==================================================
SELF-VALIDATION (WAJIB SEBELUM RETURN)
======================================

Periksa:

1. Jumlah segment = {num_clips} ?
2. Semua durasi 40–70 detik (target 50–70) ?
3. Semua punya tepat 6 field ?
4. virality_score berupa integer 1–10 ?
5. hook_text maksimal 6 kata, berupa headline deklaratif kontekstual, dan berisi nama bertanda [NAMA] di posisi natural ?
6. Tidak ada field lain ?
7. Tidak ada teks di luar JSON ?

Jika ada kesalahan → PERBAIKI sebelum output.

==================================================
OUTPUT FORMAT (STRICT)
======================

Return HANYA JSON array.
Tanpa markdown.
Tanpa penjelasan.
Tanpa komentar.

Format EXACT seperti ini:

[{{"start_time":"HH:MM:SS,mmm","end_time":"HH:MM:SS,mmm","title":"...","description":"...","virality_score":8,"hook_text":"..."}}]

==================================================
KONTEN
======

{video_context}

Transcript:
{transcript}"""

    def find_highlights(self, transcript: str, video_info: dict, num_clips: int) -> list:
        filtered = self._prefilter_transcript_for_ai(transcript)
        if filtered != transcript:
            self.log(f"  Fast AI mode: transcript dipangkas {len(transcript)} → {len(filtered)} chars")
        return self._find_highlights_single(filtered, video_info, num_clips)

    def _prefilter_transcript_for_ai(self, transcript: str, max_chars: int = 35000) -> str:
        if len(transcript or "") <= max_chars:
            return transcript
        keywords = (
            "lucu", "ngakak", "ketawa", "tertawa", "wkwk", "haha", "kocak", "lawak", "joke", "becanda", "bercanda",
            "bangkrut", "takut", "marah", "sedih", "stres", "stress", "trauma", "gagal", "salah", "masalah",
            "konflik", "ribut", "berantem", "putus", "pacar", "cinta", "selingkuh", "uang", "bayaran", "mahal",
            "murah", "viral", "kontroversi", "jujur", "pengakuan", "rahasia", "ternyata", "kenapa", "gimana",
            "cerita", "pernah", "hampir", "akhirnya", "tapi", "karena", "gue", "aku", "saya", "dia",
        )
        lines = [line for line in (transcript or "").splitlines() if line.strip()]
        scored = []
        for idx, line in enumerate(lines):
            text = line.lower()
            words = re.findall(r"[\w']+", text)
            if len(words) < 4:
                continue
            score = sum(3 for kw in keywords if kw in text)
            score += 2 if "?" in line else 0
            score += 1 if "!" in line else 0
            score += min(3, len(words) // 12)
            if score > 0:
                scored.append((score, idx))
        if not scored:
            return "\n".join(lines[: max(1, max_chars // 120)])
        keep = set()
        size = 0
        for _, idx in sorted(scored, reverse=True):
            window = list(range(max(0, idx - 2), min(len(lines), idx + 3)))
            window_size = sum(len(lines[i]) + 1 for i in window if i not in keep)
            if keep and size + window_size > max_chars:
                continue
            keep.update(window)
            size += window_size
            if size >= max_chars:
                break
        selected = [lines[i] for i in sorted(keep)]
        return "\n".join(selected) or transcript[:max_chars]

    def _find_highlights_single(self, transcript: str, video_info: dict, num_clips: int, allow_chunking: bool = True) -> list:
        """Find highlights using AI (OpenAI-compatible API)"""
        self.log(f"[2/4] Finding highlights (using {self.model})...")
        
        request_clips = num_clips if not allow_chunking else num_clips + 5
        
        video_context = ""
        if video_info:
            video_context = f"""INFO VIDEO:
- Judul: {video_info.get('title', 'Unknown')}
- Channel: {video_info.get('channel', 'Unknown')}
- Deskripsi: {video_info.get('description', '')[:500]}"""
        
        # Replace placeholders safely (avoid .format() which breaks on user's curly braces)
        prompt = self.system_prompt.replace("{num_clips}", str(request_clips))
        prompt = prompt.replace("{video_context}", video_context)
        prompt = prompt.replace("{transcript}", transcript)
        
        # Warn if required placeholders are missing
        if "{transcript}" in self.system_prompt and "{transcript}" in prompt:
            self.log("  ⚠ Warning: {transcript} placeholder not replaced - check your system prompt")
        if "{num_clips}" in self.system_prompt and "{num_clips}" in prompt:
            self.log("  ⚠ Warning: {num_clips} placeholder not replaced - check your system prompt")

        import random
        seed = random.randint(1000, 9999)
        variety_hint = f"\n\n[SISTEM: Generate dengan variasi baru (Seed: {seed}). Prioritaskan segmen/timestamp yang BERBEDA dari yang biasanya paling jelas. Cari hidden gems atau momen unik yang sebelumnya mungkin terlewat.]"
        duration_hint = f"\n\n[SISTEM: Timestamp WAJIB target {TARGET_CLIP_MIN}-{TARGET_CLIP_MAX} detik (minimum {HARD_CLIP_MIN}, maksimum {HARD_CLIP_MAX}). Jangan pilih satu kalimat pendek. Jika momen inti pendek, perluas konteks sebelum/sesudah. hook_text maksimal 6 kata; nama orang WAJIB ada dan ditandai [NAMA], tetapi boleh berada di posisi mana pun yang natural. Hook WAJIB satu headline deklaratif kontekstual, bukan kalimat tanya, dan tidak boleh merangkai potongan transcript yang rusak. Kata penentu seperti sering/selalu/berulang kali OPSIONAL dan DILARANG ditambah jika tidak didukung transcript; jangan format 'Nama: kalimat'. Setiap description WAJIB diakhiri tepat 5 hashtag yang spesifik dan relevan dengan isi segmen.]"
        prompt += variety_hint + duration_hint

        # Use OpenAI-compatible API for all providers
        self.log(f"  Using API: {self.highlight_client.base_url}")
        try:
            response = self.highlight_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
            )
            
            # Validate response structure
            if not response:
                raise Exception("API returned empty response")
            
            if not hasattr(response, 'choices') or not response.choices:
                # Log response structure for debugging
                self.log(f"  ⚠ Unexpected API response structure: {type(response)}")
                self.log(f"  Response attributes: {dir(response)}")
                raise Exception(
                    "API response missing 'choices' field.\n\n"
                    "This usually happens with custom API providers that don't follow OpenAI format.\n\n"
                    "Please check:\n"
                    "1. API key is valid and has credits\n"
                    "2. Base URL is correct for your provider\n"
                    "3. Model name is supported by your provider\n"
                    "4. Provider follows OpenAI-compatible API format"
                )
            
            if not response.choices[0].message or not response.choices[0].message.content:
                raise Exception(
                    "API returned empty content.\n\n"
                    "Possible causes:\n"
                    "1. Model refused to generate content (content filter)\n"
                    "2. API quota exceeded\n"
                    "3. Model doesn't support this type of request"
                )
            
            # Report token usage (input and output separately)
            if hasattr(response, 'usage') and response.usage:
                self.report_tokens(response.usage.prompt_tokens, response.usage.completion_tokens, 0, 0)
            
            result = response.choices[0].message.content.strip()
            
        except Exception as e:
            # Check if it's our custom exception
            if "API response missing" in str(e) or "API returned empty" in str(e):
                raise
            
            # Otherwise, wrap with more context
            self.log(f"  ❌ API Error: {e}")
            raise Exception(
                f"Failed to get highlights from AI model.\n\n"
                f"Error: {str(e)}\n\n"
                f"Please check:\n"
                f"1. API key is valid and loaded\n"
                f"2. Base URL is correct: {self.highlight_client.base_url}\n"
                f"3. Model exists: {self.model}\n"
                f"4. You have sufficient credits/quota"
            )
        
        # Log raw response for debugging
        self.log(f"  Raw AI response (first 500 chars):\n{result[:500]}")
        
        if result.startswith("```"):
            result = re.sub(r"```json?\n?", "", result)
            result = re.sub(r"```\n?", "", result)
        
        try:
            highlights = json.loads(result)
        except json.JSONDecodeError as e:
            # Log full response on error
            self.log(f"\n❌ JSON Parse Error: {e}")
            self.log(f"\n📄 Full GPT Response:\n{result}")
            self.log(f"\n💡 Error position: line {e.lineno}, column {e.colno}")
            raise Exception(f"Failed to parse GPT response as JSON: {e}\n\nFull response logged above.")
        
        # Filter by duration (target around 60s)
        valid = []
        for h in highlights:
            # Fallback: convert "reason" to "description" if exists
            if "reason" in h and "description" not in h:
                h["description"] = h.pop("reason")
                self.log(f"  ⚠ Converted 'reason' to 'description' for '{h.get('title', 'Unknown')}'")
            
            start_seconds = self.parse_timestamp(h["start_time"])
            end_seconds = self.parse_timestamp(h["end_time"])
            duration = end_seconds - start_seconds
            if duration < MIN_CLIP_DURATION:
                # Expand toward target 50–70s window
                need = max(TARGET_CLIP_MIN, MIN_CLIP_DURATION) - duration
                pad_before = min(25.0, need * 0.4)
                pad_after = need - pad_before
                start_seconds = max(0, start_seconds - pad_before)
                end_seconds = end_seconds + pad_after
                # Clamp to hard max
                if end_seconds - start_seconds > MAX_CLIP_DURATION:
                    end_seconds = start_seconds + MAX_CLIP_DURATION
                h["start_time"] = self.format_timestamp(start_seconds)
                h["end_time"] = self.format_timestamp(end_seconds)
                duration = end_seconds - start_seconds
                self.log(f"  ↻ Expanded short highlight '{h.get('title', 'Unknown')}' to {duration:.0f}s")
            h["duration_seconds"] = round(duration, 1)
            
            # Ensure virality_score exists (default to 5 if missing)
            if "virality_score" not in h:
                h["virality_score"] = 5
                self.log(f"  ⚠ Missing virality_score for '{h.get('title', 'Unknown')}', defaulting to 5")
            
            # Ensure description exists
            if "description" not in h:
                h["description"] = h.get("title", "No description")
                self.log(f"  ⚠ Missing description for '{h.get('title', 'Unknown')}', using title")
            if "hook_text" not in h:
                raise ValueError("AI highlight wajib memiliki hook_text dengan [NAMA]")
            h["hook_text"] = normalize_generated_hook_text(h["hook_text"])
            
            if duration > MAX_CLIP_DURATION:
                h["end_time"] = self.format_timestamp(self.parse_timestamp(h["start_time"]) + MAX_CLIP_DURATION)
                h["duration_seconds"] = MAX_CLIP_DURATION
                valid.append(h)
                self.log(f"  ✓ {h['title']} ({duration:.0f}s → {MAX_CLIP_DURATION}s) trimmed")
            elif duration >= MIN_CLIP_DURATION:
                valid.append(h)
                virality = h.get("virality_score", 5)
                self.log(f"  ✓ {h['title']} ({duration:.0f}s) [{virality}/10]")
            else:
                self.log(f"  ✗ {h['title']} ({duration:.0f}s) - Too short, skipped")
            

        if len(valid) < num_clips:
            self.log(f"\n⚠️ WARNING: Only found {len(valid)} valid clips out of {num_clips} requested; filling from transcript.")
            used = [(self.parse_timestamp(h["start_time"]), self.parse_timestamp(h["end_time"])) for h in valid]
            for fallback in self._fallback_highlights_from_transcript(transcript, num_clips - len(valid), used):
                valid.append(fallback)
                if len(valid) >= num_clips:
                    break
        
        def is_funny(highlight):
            return str(highlight.get("description", "")).lstrip().upper().startswith("[LUCU]")

        valid.sort(
            key=lambda h: (
                is_funny(h),
                float(h.get("virality_score", 0) or 0),
            ),
            reverse=True,
        )
        for highlight in valid:
            description = re.sub(r"^\s*\[LUCU\]\s*", "", str(highlight.get("description", "")), flags=re.IGNORECASE)
            highlight["description"] = ensure_five_hashtags(
                description,
                str(highlight.get("title", "")),
                str(highlight.get("hook_text", "")),
                description,
            )
        return valid[:num_clips]

    def _fallback_highlights_from_transcript(self, transcript: str, count: int, used: list) -> list:
        matches = list(re.finditer(r"\[(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\]", transcript or ""))
        if not matches:
            return []
        spans = [(self.parse_timestamp(m.group(1)), self.parse_timestamp(m.group(2))) for m in matches]
        total_end = max(end for _, end in spans)
        out = []
        cursor = 0.0
        while len(out) < count and cursor < total_end:
            start = cursor
            end = min(start + TARGET_CLIP_MIN, total_end)
            cursor += TARGET_CLIP_MIN
            if end - start < MIN_CLIP_DURATION:
                continue
            if any(start < u_end and end > u_start for u_start, u_end in used):
                continue
            item = {
                "title": f"Highlight tambahan {len(out) + 1}",
                "description": "Segmen tambahan dari transcript karena AI mengembalikan terlalu sedikit klip.",
                "start_time": self.format_timestamp(start),
                "end_time": self.format_timestamp(end),
                "duration_seconds": round(end - start, 1),
                "virality_score": 4,
                "hook_text": normalize_hook_text(f"Highlight tambahan {len(out) + 1}"),
            }
            out.append(item)
            used.append((start, end))
        return out

    def format_timestamp(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace(".", ",")

    def _groq_retry_delay(self, response, attempt: int) -> float:
        value = response.headers.get("Retry-After") if response is not None else None
        if value:
            try:
                delay = float(value)
            except (TypeError, ValueError):
                try:
                    retry_at = parsedate_to_datetime(value)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=timezone.utc)
                    delay = (retry_at - datetime.now(timezone.utc)).total_seconds()
                except (TypeError, ValueError, OverflowError):
                    delay = 2 ** attempt
        else:
            delay = 2 ** attempt
        if not math.isfinite(delay) or delay < 0:
            delay = 2 ** attempt
        return min(delay, 30.0)

    def _transcribe_groq_chunk(self, audio_path: str, time_offset: float = 0.0) -> TimedTranscript:
        if not getattr(self, "caption_client", None) or not getattr(self.caption_client, "api_key", None):
            raise Exception("Caption Maker API key belum diisi")
        if isinstance(time_offset, bool) or not isinstance(time_offset, (int, float)) or not math.isfinite(time_offset) or time_offset < 0:
            raise ValueError("time_offset must be a finite non-negative number")
        time_offset = float(time_offset)
        base_url = str(self.caption_client.base_url).rstrip("/")
        model = str(self.whisper_model)
        url = f"{base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.caption_client.api_key}"}
        form_data = [
            ("model", model),
            ("response_format", "verbose_json"),
            ("timestamp_granularities[]", "word"),
            ("timestamp_granularities[]", "segment"),
        ]
        language = str(getattr(self, "subtitle_language", "") or "").strip()
        if language.lower() not in {"", "none", "auto"}:
            form_data.append(("language", language))
        mime = mimetypes.guess_type(audio_path)[0] or "application/octet-stream"
        response = None
        started = time.time()
        self.log(f"  Uploading {os.path.getsize(audio_path) / (1024 * 1024):.2f}MB to Groq ({model})...")
        for attempt in range(3):
            if self.is_cancelled():
                raise Exception("Groq transcription cancelled")
            try:
                with open(audio_path, "rb") as audio_file:
                    response = requests.post(
                        url,
                        headers=headers,
                        data=form_data,
                        files={"file": (os.path.basename(audio_path), audio_file, mime)},
                        timeout=(15, 120),
                    )
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt == 2:
                    raise Exception(f"Groq transcription request failed after 3 attempts at {base_url} using {model}") from exc
                time.sleep(2 ** attempt)
                continue
            if response.status_code == 200:
                break
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt == 2:
                    raise Exception(f"Groq transcription failed with HTTP {response.status_code} at {base_url} using {model}")
                time.sleep(self._groq_retry_delay(response, attempt))
                continue
            raise Exception(f"Groq transcription failed with HTTP {response.status_code} at {base_url} using {model}")
        try:
            data = response.json()
        except ValueError as exc:
            raise Exception(f"Groq transcription returned invalid JSON at {base_url} using {model}") from exc
        if not isinstance(data, dict):
            raise ValueError("Groq transcription response must be a dictionary")
        if not data.get("segments"):
            raise ValueError("Groq transcription response requires segment timestamps")
        local = validate_timed_transcript(
            {
                "duration": data.get("duration"),
                "words": [item for item in (data.get("words") or []) if isinstance(item, dict) and str(item.get("word") or "").strip()],
                "segments": [item for item in (data.get("segments") or []) if isinstance(item, dict) and str(item.get("text") or "").strip()],
            }
        )
        result = validate_timed_transcript(
            {
                "duration": local["duration"] + time_offset,
                "words": [
                    {"word": item["word"], "start": item["start"] + time_offset, "end": item["end"] + time_offset}
                    for item in local["words"]
                ],
                "segments": [
                    {"text": item["text"], "start": item["start"] + time_offset, "end": item["end"] + time_offset}
                    for item in local["segments"]
                ],
            }
        )
        self.log(f"  Groq transcription completed in {time.time() - started:.1f}s")
        return result

    def _probe_media_duration(self, audio_path: str) -> float:
        ffmpeg_path = Path(str(self.ffmpeg_path))
        ffprobe_path = ffmpeg_path.with_name("ffprobe.exe" if ffmpeg_path.suffix.lower() == ".exe" else "ffprobe")
        result = subprocess.run(
            [str(ffprobe_path), "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True,
            text=True,
            creationflags=SUBPROCESS_FLAGS,
        )
        try:
            duration = float(result.stdout.strip())
        except (TypeError, ValueError) as exc:
            raise Exception(f"Failed to probe media duration: {result.stderr[:200]}") from exc
        if result.returncode != 0 or not math.isfinite(duration) or duration <= 0:
            raise Exception(f"Failed to probe media duration: {result.stderr[:200]}")
        return duration

    def _create_groq_chunks(self, audio_path: str, duration: float, chunk_count: int, chunk_paths: list[str]) -> list[tuple[str, float]]:
        chunks = []
        chunk_duration = duration / chunk_count
        for index in range(chunk_count):
            chunk_start = index * chunk_duration
            handle = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            chunk_path = handle.name
            handle.close()
            chunk_paths.append(chunk_path)
            result = subprocess.run(
                [
                    self.ffmpeg_path,
                    "-y",
                    "-ss",
                    str(chunk_start),
                    "-i",
                    audio_path,
                    "-t",
                    str(min(chunk_duration, duration - chunk_start)),
                    "-vn",
                    "-acodec",
                    "libmp3lame",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-b:a",
                    "32k",
                    chunk_path,
                ],
                capture_output=True,
                text=True,
                creationflags=SUBPROCESS_FLAGS,
            )
            if result.returncode != 0 or not os.path.exists(chunk_path) or os.path.getsize(chunk_path) == 0:
                raise Exception(f"Failed to create Groq audio chunk: {result.stderr[:200]}")
            chunks.append((chunk_path, chunk_start))
        return chunks

    def transcribe_audio_with_timestamps(self, audio_path: str, require_words: bool = False) -> TimedTranscript:
        duration = self._probe_media_duration(audio_path)
        self.report_tokens(0, 0, duration, 0)
        chunk_paths = []
        try:
            if self.is_cancelled():
                raise Exception("Groq transcription cancelled")
            size = os.path.getsize(audio_path)
            if size <= MAX_GROQ_UPLOAD_BYTES:
                self.set_progress("Transcribing audio with Groq...", 0.3)
                transcript = self._transcribe_groq_chunk(audio_path)
                return validate_timed_transcript(
                    {"duration": duration, "words": transcript["words"], "segments": transcript["segments"]},
                    require_words=require_words,
                )
            chunk_count = math.ceil(size / MAX_GROQ_UPLOAD_BYTES)
            chunks = self._create_groq_chunks(audio_path, duration, chunk_count, chunk_paths)
            words = []
            segments = []
            for index, (chunk_path, time_offset) in enumerate(chunks):
                if self.is_cancelled():
                    raise Exception("Groq transcription cancelled")
                self.set_progress(f"Transcribing Groq audio chunk {index + 1}/{chunk_count}...", 0.3 + 0.2 * (index + 1) / chunk_count)
                transcript = self._transcribe_groq_chunk(chunk_path, time_offset)
                words.extend(transcript["words"])
                segments.extend(transcript["segments"])
            return validate_timed_transcript(
                {"duration": duration, "words": words, "segments": segments},
                require_words=require_words,
            )
        finally:
            for chunk_path in chunk_paths:
                Path(chunk_path).unlink(missing_ok=True)

