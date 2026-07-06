import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from openai import APIConnectionError, APIError, APIStatusError, RateLimitError

from clipper_shared import SUBPROCESS_FLAGS, SubtitleNotFoundError, YTDLP_MODULE_AVAILABLE, _hex_to_rgb, yt_dlp
from utils.helpers import get_deno_path, get_ffmpeg_path, is_ytdlp_module_available
from utils.logger import debug_log


class AiMixin:
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

Prioritaskan segmen dengan karakteristik berikut:

1. Ada KONFLIK, ketegangan, kontroversi.
2. Ada PENGAKUAN personal / vulnerability.
3. Ada STATEMENT tajam / opini berani.
4. Ada punchline atau momen lucu kuat.
5. Ada cerita lengkap (setup → buildup → payoff).
6. Ada kalimat yang bisa berdiri sendiri sebagai hook viral.

Hindari:

* Obrolan filler
* Basa-basi
* Transisi topik tanpa payoff
* Penjelasan teknis panjang tanpa emosi

Jika harus memilih, utamakan EMOSI & KONFLIK dibanding edukasi netral.

==================================================
ATURAN DURASI (KRITIS – TIDAK BOLEH DILANGGAR)
==============================================

* Setiap clip HARUS 60–120 detik.
* Target ideal: 85–95 detik.
* Hitung durasi dari timestamp transcript.
* JANGAN estimasi berdasarkan panjang teks.

Jika durasi < 60 detik:
→ PERPANJANG dengan konteks sebelum atau sesudahnya.

Jika durasi > 120 detik:
→ Pangkas bagian yang tidak relevan TANPA merusak alur cerita.

==================================================
STRATEGI WAJIB JIKA SEGMENT IDEAL TIDAK ADA
===========================================

Lakukan salah satu atau kombinasi berikut:

1. Gabungkan beberapa bagian berurutan yang masih satu topik.
2. Tambahkan setup sebelum punchline agar dramatis.
3. Tambahkan payoff setelah cerita agar terasa lengkap.
4. Pangkas filler tapi jaga minimal 60 detik.

DILARANG:

* Menghasilkan clip < 60 detik
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
6. "hook_text" (string) → Maks 15 kata

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

5–7:

* Insight menarik
* Cerita cukup engaging
* Momen lucu ringan

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

* Maksimal 15 kata
* Bahasa Indonesia casual
* TANPA emoji
* WAJIB menyebut NAMA ORANG yang berbicara
* Harus berupa kutipan, statement tajam, atau punchline

Contoh benar:
"Andre Taulany: Gua hampir bangkrut gara-gara ini"
"Deddy Corbuzier: Banyak podcaster cuma pura-pura sukses"

Hook harus bisa berdiri sendiri sebagai headline viral.

==================================================
SELF-VALIDATION (WAJIB SEBELUM RETURN)
======================================

Periksa:

1. Jumlah segment = {num_clips} ?
2. Semua durasi 60–120 detik ?
3. Semua punya tepat 6 field ?
4. virality_score berupa integer 1–10 ?
5. Tidak ada field lain ?
6. Tidak ada teks di luar JSON ?

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
        """Find highlights using AI (OpenAI-compatible API)"""
        self.log(f"[2/4] Finding highlights (using {self.model})...")
        
        request_clips = num_clips + 3
        
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
        
        # Filter by duration (min 58s, max 120s)
        valid = []
        for h in highlights:
            # Fallback: convert "reason" to "description" if exists
            if "reason" in h and "description" not in h:
                h["description"] = h.pop("reason")
                self.log(f"  ⚠ Converted 'reason' to 'description' for '{h.get('title', 'Unknown')}'")
            
            duration = self.parse_timestamp(h["end_time"]) - self.parse_timestamp(h["start_time"])
            h["duration_seconds"] = round(duration, 1)
            
            # Ensure virality_score exists (default to 5 if missing)
            if "virality_score" not in h:
                h["virality_score"] = 5
                self.log(f"  ⚠ Missing virality_score for '{h.get('title', 'Unknown')}', defaulting to 5")
            
            # Ensure description exists
            if "description" not in h:
                h["description"] = h.get("title", "No description")
                self.log(f"  ⚠ Missing description for '{h.get('title', 'Unknown')}', using title")
            
            if 58 <= duration <= 120:
                valid.append(h)
                virality = h.get("virality_score", 5)
                self.log(f"  ✓ {h['title']} ({duration:.0f}s) [🔥 {virality}/10]")
            elif duration > 120:
                self.log(f"  ✗ {h['title']} ({duration:.0f}s) - Too long, skipped")
            elif duration < 58:
                self.log(f"  ✗ {h['title']} ({duration:.0f}s) - Too short, skipped")
            
            if len(valid) >= num_clips:
                break
        
        # If we don't have enough valid clips, warn user
        if len(valid) < num_clips:
            self.log(f"\n⚠️ WARNING: Only found {len(valid)} valid clips out of {num_clips} requested!")
            self.log(f"   AI returned many segments that were too short (< 58s).")
            self.log(f"   Consider using a better AI model or adjusting the prompt.")
        
        return valid[:num_clips]

    def find_highlights_with_transcription(self, video_path: str, video_info: dict, 
                                            num_clips: int, session_dir: str = None) -> dict:
        """Find highlights by first transcribing the video with Whisper API.
        
        This is the fallback path when no subtitle is available.
        Uses Caption Maker (Whisper) to generate transcript, then feeds it
        to Highlight Finder (GPT) as usual.
        
        Returns:
            dict: Same session_data format as find_highlights_only
        """
        from datetime import datetime
        
        # Use existing session_dir or create new one
        if session_dir:
            session_dir = Path(session_dir)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_dir = self.output_dir / "sessions" / timestamp
            session_dir.mkdir(parents=True, exist_ok=True)
        
        # Update temp_dir to session-specific temp
        self.temp_dir = session_dir / "_temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Step 1: Transcribe with Whisper
        self.set_progress("Transcribing video with AI...", 0.3)
        transcript = self.transcribe_full_video(video_path)
        
        if self.is_cancelled():
            return None
        
        # Step 2: Find highlights using the transcript
        self.set_progress("Finding highlights with AI...", 0.6)
        highlights = self.find_highlights(transcript, video_info, num_clips)
        
        if self.is_cancelled():
            return None
        
        if not highlights:
            raise Exception(
                "No valid highlights found!\n\n"
                "Possible causes:\n"
                "1. AI model failed to generate highlights\n"
                "2. Video transcript too short or not suitable\n"
                "3. AI model configuration issue\n\n"
                "Try:\n"
                "- Using a different AI model\n"
                "- Checking AI API settings\n"
                "- Using a longer video with more content"
            )
        
        self.set_progress("Highlights found!", 1.0)
        self.log(f"\n✅ Found {len(highlights)} highlights (via AI transcription)")
        
        # Save session data
        session_data_file = session_dir / "session_data.json"
        session_data = {
            "session_dir": str(session_dir),
            "video_path": video_path,
            "srt_path": None,
            "highlights": highlights,
            "video_info": video_info,
            "created_at": datetime.now().isoformat(),
            "status": "highlights_found",
            "transcription_method": "whisper_api"
        }
        
        with open(session_data_file, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)
        
        self.log(f"Session data saved to: {session_data_file}")
        
        return session_data

    def find_highlights_only(self, url: str, num_clips: int = 5) -> dict:
        """Phase 1: Download subtitle only and find highlights (no video download)
        
        Returns:
            dict with keys:
                - 'session_dir': Path to session directory
                - 'url': YouTube video URL (for later section download)
                - 'srt_path': Path to subtitle file
                - 'highlights': List of highlight dicts with metadata + transcript
                - 'video_info': Video metadata (title, channel, etc.)
        """
        # Create session directory with timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = self.output_dir / "sessions" / timestamp
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Update temp_dir to session-specific temp
        self.temp_dir = session_dir / "_temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        self.log(f"Session directory: {session_dir}")
        
        # Step 1: Download subtitle only (no video!)
        self.set_progress("Downloading subtitle...", 0.1)
        srt_path, video_info = self.download_subtitle_only(url)
        
        # Store channel name for credit watermark
        self.channel_name = video_info.get("channel", "") if video_info else ""
        
        if self.is_cancelled():
            return None
        
        if not srt_path:
            raise SubtitleNotFoundError(
                f"No subtitle available for language: {self.subtitle_language.upper()}",
                video_path=None,
                video_info=video_info,
                session_dir=str(session_dir)
            )
        
        # Step 2: Find highlights
        self.set_progress("Finding highlights with AI...", 0.5)
        transcript = self.parse_srt(srt_path)
        highlights = self.find_highlights(transcript, video_info, num_clips)
        
        if self.is_cancelled():
            return None
        
        if not highlights:
            raise Exception(
                "❌ No valid highlights found!\n\n"
                "Possible causes:\n"
                "1. AI model failed to generate highlights\n"
                "2. Video transcript too short or not suitable\n"
                "3. AI model configuration issue\n\n"
                "Try:\n"
                "- Using a different AI model (GPT-4, Gemini, etc.)\n"
                "- Checking AI API settings\n"
                "- Using a longer video with more content"
            )
        
        # Extract transcript text for each highlight
        for h in highlights:
            h["transcript_text"] = self.extract_transcript_for_highlight(srt_path, h)
        
        self.set_progress("Highlights found!", 1.0)
        self.log(f"\n✅ Found {len(highlights)} highlights")
        
        # Save session data to JSON for resume capability
        session_data_file = session_dir / "session_data.json"
        session_data = {
            "session_dir": str(session_dir),
            "url": url,
            "srt_path": srt_path,
            "highlights": highlights,
            "video_info": video_info,
            "created_at": datetime.now().isoformat(),
            "status": "highlights_found"
        }
        
        with open(session_data_file, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)
        
        self.log(f"Session data saved to: {session_data_file}")
        
        return session_data

    def transcribe_full_video(self, video_path: str) -> str:
        """Transcribe full video audio using Whisper API (Caption Maker).
        
        Extracts audio from the video, compresses to mp3, splits into chunks
        if needed (Whisper API has ~25MB limit), and returns a transcript
        formatted like parse_srt output so find_highlights can consume it directly.
        
        Returns:
            str: Transcript with timestamps in SRT-like format:
                 [HH:MM:SS,mmm - HH:MM:SS,mmm] text
        """
        self.log("[AI Transcription] Transcribing full video with Whisper API...")
        
        # Check Caption Maker is configured
        cm_config = self.ai_providers.get("caption_maker", {})
        if not cm_config.get("api_key"):
            raise Exception(
                "Caption Maker is not configured!\n\n"
                "Please set up Caption Maker in:\n"
                "Settings → AI API Settings → Caption Maker"
            )
        
        # Extract audio as compressed mp3 to minimize file size
        audio_file = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False).name
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "libmp3lame",
            "-ar", "16000",
            "-ac", "1",
            "-b:a", "64k",
            audio_file
        ]
        self.log("  Extracting audio from video...")
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
        
        if result.returncode != 0:
            if os.path.exists(audio_file):
                os.unlink(audio_file)
            raise Exception(f"Failed to extract audio from video:\n{result.stderr[:200]}")
        
        file_size_mb = os.path.getsize(audio_file) / (1024 * 1024)
        self.log(f"  Audio file size: {file_size_mb:.1f} MB")
        
        # Get total audio duration
        probe_cmd = [self.ffmpeg_path, "-i", audio_file, "-f", "null", "-"]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
        duration_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe_result.stderr)
        total_duration = 0
        if duration_match:
            h, m, s = duration_match.groups()
            total_duration = int(h) * 3600 + int(m) * 60 + float(s)
        
        self.log(f"  Audio duration: {total_duration:.0f}s ({total_duration/60:.1f} min)")
        
        # Report Whisper usage
        self.report_tokens(0, 0, total_duration, 0)
        
        # Split into chunks if file is too large (>4MB to avoid proxy timeout)
        MAX_CHUNK_SIZE_MB = 4
        all_segments = []
        
        if file_size_mb <= MAX_CHUNK_SIZE_MB:
            # Single file, transcribe directly
            self.log("  Sending to Whisper API...")
            self.set_progress("Transcribing audio with AI...", 0.3)
            segments = self._whisper_transcribe_file(audio_file, 0)
            all_segments.extend(segments)
        else:
            # Split into chunks by duration
            chunk_count = int(file_size_mb / MAX_CHUNK_SIZE_MB) + 1
            chunk_duration = total_duration / chunk_count
            self.log(f"  File too large, splitting into {chunk_count} chunks (~{chunk_duration:.0f}s each)...")
            
            for i in range(chunk_count):
                if self.is_cancelled():
                    os.unlink(audio_file)
                    return ""
                
                chunk_start = i * chunk_duration
                chunk_file = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False).name
                
                cmd = [
                    self.ffmpeg_path, "-y",
                    "-i", audio_file,
                    "-ss", str(chunk_start),
                    "-t", str(chunk_duration),
                    "-acodec", "libmp3lame",
                    "-ar", "16000",
                    "-ac", "1",
                    "-b:a", "64k",
                    chunk_file
                ]
                subprocess.run(cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
                
                chunk_size = os.path.getsize(chunk_file) / (1024 * 1024)
                self.log(f"  Transcribing chunk {i+1}/{chunk_count} ({chunk_size:.1f}MB, ~{chunk_duration:.0f}s)...")
                self.set_progress(f"Transcribing audio chunk {i+1}/{chunk_count}...", 
                                  0.3 + (0.2 * (i + 1) / chunk_count))
                
                segments = self._whisper_transcribe_file(chunk_file, chunk_start)
                all_segments.extend(segments)
                
                try:
                    os.unlink(chunk_file)
                except Exception:
                    pass
        
        # Cleanup main audio file
        try:
            os.unlink(audio_file)
        except Exception:
            pass
        
        if not all_segments:
            raise Exception("Whisper API returned empty transcription. The video may have no speech.")
        
        # Format segments into SRT-like transcript (same format as parse_srt output)
        lines = []
        for seg in all_segments:
            start_ts = self._seconds_to_srt_timestamp(seg["start"])
            end_ts = self._seconds_to_srt_timestamp(seg["end"])
            text = seg["text"].strip()
            if text:
                lines.append(f"[{start_ts} - {end_ts}] {text}")
        
        transcript = "\n".join(lines)
        self.log(f"  ✓ Transcription complete: {len(lines)} segments")
        
        return transcript

    def _whisper_transcribe_file(self, audio_path: str, time_offset: float = 0) -> list:
        """Transcribe a single audio file with Whisper API.
        
        Uses raw httpx POST instead of OpenAI SDK for better proxy compatibility.
        
        Args:
            audio_path: Path to audio file
            time_offset: Offset in seconds to add to all timestamps (for chunked files)
        
        Returns:
            list of dicts with 'start', 'end', 'text' keys
        """
        import time as _time
        import requests as _requests
        
        if not self.caption_client:
            raise Exception("Caption Maker API key belum diisi")
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        base_url = str(self.caption_client.base_url).rstrip("/")
        api_key = self.caption_client.api_key
        
        self.log(f"    Uploading {file_size_mb:.1f}MB to Whisper API ({self.whisper_model})...")
        self.log(f"    Base URL: {base_url}")
        
        # Build multipart form data
        url = f"{base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {api_key}"}
        
        form_data = {
            "model": self.whisper_model,
            "response_format": "verbose_json",
        }
        if self.subtitle_language and self.subtitle_language != "none":
            form_data["language"] = self.subtitle_language
        
        # Run API call in a thread so we can log heartbeat while waiting
        response_data = None
        api_error = None
        
        def _call_api():
            nonlocal response_data, api_error
            try:
                with open(audio_path, "rb") as f:
                    files = {"file": (os.path.basename(audio_path), f, "audio/mpeg")}
                    resp = _requests.post(url, headers=headers, data=form_data, files=files, timeout=600)
                    resp.raise_for_status()
                    response_data = resp.json()
            except Exception as e:
                api_error = e
        
        api_thread = threading.Thread(target=_call_api, daemon=True)
        start_time = _time.time()
        api_thread.start()
        
        # Heartbeat: log every 15s so user knows it's still working
        TIMEOUT_SECONDS = 300  # 5 minutes max per chunk
        while api_thread.is_alive():
            api_thread.join(timeout=15)
            if api_thread.is_alive():
                elapsed = _time.time() - start_time
                
                # Check cancellation
                if self.is_cancelled():
                    self.log(f"    ⚠️ Cancelled by user during Whisper API call")
                    return []
                
                if elapsed > TIMEOUT_SECONDS:
                    self.log(f"    ⏱️ Whisper API timed out after {TIMEOUT_SECONDS}s")
                    raise Exception(
                        f"Whisper API timed out after {TIMEOUT_SECONDS}s.\n\n"
                        "Possible causes:\n"
                        "1. Your AI API provider may not support the Whisper audio endpoint\n"
                        "2. The server may be overloaded or unreachable\n"
                        "3. Network connection issue\n\n"
                        "Try:\n"
                        "- Check if your Caption Maker API supports audio transcription\n"
                        "- Try again later\n"
                        "- Use a different API provider for Caption Maker"
                    )
                self.log(f"    ⏳ Waiting for Whisper API response... ({elapsed:.0f}s elapsed)")
                self.set_progress(f"Transcribing with AI... waiting for response ({elapsed:.0f}s)", 0.35)
        
        elapsed = _time.time() - start_time
        
        if api_error:
            self.log(f"  ❌ Whisper API error after {elapsed:.1f}s: {api_error}")
            raise Exception(f"Whisper transcription failed:\n{str(api_error)}")
        
        if response_data is None:
            self.log(f"  ❌ Whisper API returned no response after {elapsed:.1f}s")
            raise Exception("Whisper API returned no response. The endpoint may not support audio transcription.")
        
        self.log(f"    ✓ Whisper API responded in {elapsed:.1f}s")
        
        segments = []
        if "segments" in response_data and response_data["segments"]:
            for seg in response_data["segments"]:
                segments.append({
                    "start": seg.get("start", 0) + time_offset,
                    "end": seg.get("end", 0) + time_offset,
                    "text": seg.get("text", "")
                })
        
        return segments

    def _whisper_transcribe_words_api(self, audio_path: str):
        """Transcribe an audio file with word-level timestamps using raw HTTP.

        Compresses the audio to MP3 before uploading (the ytclip proxy drops
        connections for large WAV files >~1MB). Uses ``requests`` instead of
        the OpenAI SDK for proxy compatibility. Tries with
        ``timestamp_granularities[]=word`` first; if the proxy rejects it
        (400), retries without that field (still gets segments).

        Returns an object exposing ``.words`` and ``.segments`` (mirroring the
        SDK response shape consumed by ``create_ass_subtitle_capcut``), or
        raises on failure.
        """
        import requests as _requests
        from types import SimpleNamespace

        if not self.caption_client:
            raise Exception("Caption Maker API key belum diisi")
        base_url = str(self.caption_client.base_url).rstrip("/")
        api_key = self.caption_client.api_key
        url = f"{base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {api_key}"}

        lang = getattr(self, "subtitle_language", None) or "id"

        # Compress WAV → MP3 to reduce upload size (proxy rejects large bodies)
        upload_path = audio_path
        mp3_tmp = None
        if audio_path.lower().endswith(".wav"):
            mp3_tmp = audio_path.rsplit(".", 1)[0] + "_upload.mp3"
            cmd = [
                self.ffmpeg_path, "-y",
                "-i", audio_path,
                "-acodec", "libmp3lame",
                "-b:a", "64k",
                "-ar", "16000",
                "-ac", "1",
                mp3_tmp
            ]
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    creationflags=SUBPROCESS_FLAGS)
            if result.returncode == 0 and os.path.exists(mp3_tmp):
                upload_path = mp3_tmp
                self.log(f"  [Caption] Compressed WAV→MP3: "
                         f"{os.path.getsize(audio_path)/1024:.0f}KB → "
                         f"{os.path.getsize(mp3_tmp)/1024:.0f}KB")
            else:
                self.log("  [Caption] MP3 compression failed, uploading WAV as-is")
                mp3_tmp = None

        file_size_mb = os.path.getsize(upload_path) / (1024 * 1024)
        mime = "audio/mpeg" if upload_path.endswith(".mp3") else "audio/wav"
        self.log(f"  [Caption] Uploading {file_size_mb:.2f}MB to Whisper ({self.whisper_model})...")

        # Attempt 1: with word-level granularity
        form_data = [
            ("model", self.whisper_model),
            ("response_format", "verbose_json"),
            ("timestamp_granularities[]", "word"),
            ("timestamp_granularities[]", "segment"),
        ]
        if lang and lang != "none":
            form_data.append(("language", lang))

        resp = None
        for attempt in range(2):
            with open(upload_path, "rb") as f:
                files = {"file": (os.path.basename(upload_path), f, mime)}
                resp = _requests.post(url, headers=headers, data=form_data,
                                      files=files, timeout=600)

            if resp.status_code == 200:
                break

            # Log the actual error body for debugging
            self.log(f"  [Caption] Attempt {attempt+1} failed: HTTP {resp.status_code}")
            try:
                self.log(f"  [Caption] Response: {resp.text[:300]}")
            except Exception:
                pass

            if attempt == 0:
                # Retry without timestamp_granularities (proxy may not support it)
                self.log("  [Caption] Retrying without timestamp_granularities...")
                form_data = [
                    ("model", self.whisper_model),
                    ("response_format", "verbose_json"),
                ]
                if lang and lang != "none":
                    form_data.append(("language", lang))
            else:
                # Both attempts failed — clean up and raise
                if mp3_tmp and os.path.exists(mp3_tmp):
                    os.unlink(mp3_tmp)
                raise Exception(
                    f"Whisper API returned HTTP {resp.status_code}: "
                    f"{resp.text[:300]}"
                )

        # Clean up temp mp3
        if mp3_tmp and os.path.exists(mp3_tmp):
            os.unlink(mp3_tmp)

        data = resp.json()
        self.log(f"  [Caption] Whisper OK, text length: {len(data.get('text', ''))}")

        words = [
            SimpleNamespace(
                word=w.get("word", ""),
                start=w.get("start", 0.0),
                end=w.get("end", 0.0),
            )
            for w in (data.get("words") or [])
        ]
        segments = data.get("segments") or []
        self.log(f"  [Caption] Got {len(words)} words, {len(segments)} segments")
        return SimpleNamespace(words=words, segments=segments,
                               text=data.get("text", ""))

    def _seconds_to_srt_timestamp(seconds: float) -> str:
        """Convert seconds to SRT timestamp format HH:MM:SS,mmm"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        ms = int((s - int(s)) * 1000)
        return f"{h:02d}:{m:02d}:{int(s):02d},{ms:03d}"
