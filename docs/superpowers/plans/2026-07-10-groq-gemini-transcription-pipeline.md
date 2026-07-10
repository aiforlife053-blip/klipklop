# Groq–Gemini Transcription Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven development or execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gunakan Gemini untuk memilih highlight, Groq Whisper untuk STT/timestamp, reuse timestamp Groq untuk caption, lalu hapus `faster-whisper` lokal.

**Architecture:** Pipeline tetap mencoba subtitle YouTube lebih dahulu. Jika SRT tersedia, SRT dikirim ke Gemini dan Groq hanya mentranskripsi audio setiap klip terpilih untuk caption final. Jika SRT tidak tersedia, audio penuh diunduh dan ditranskripsi Groq satu kali secara logis; segment timestamp dikirim ke Gemini, sedangkan word timestamp dipotong serta di-rebase untuk caption klip tanpa STT ulang.

**Tech Stack:** Python 3.12, `requests`, OpenAI-compatible Gemini API, Groq Audio Transcriptions API, FFmpeg, yt-dlp, React 19, TypeScript, Vite.

## Global Constraints

- Gemini Highlight Finder tetap memakai `gemini-2.5-flash` dan endpoint yang sekarang.
- Groq Caption Maker default: `https://api.groq.com/openai/v1`, model `whisper-large-v3-turbo`.
- Permintaan Groq memakai `response_format=verbose_json` serta granularitas `word` dan `segment`.
- Tidak menambah Groq SDK; gunakan `requests` yang sudah terpasang.
- Tidak ada fallback ke model lokal. Konfigurasi Groq tidak valid harus gagal jelas sebelum render yang bergantung padanya.
- API key tidak boleh masuk log, respons API, metadata klip, transcript cache, atau pesan error.
- Tidak membuat persistent transcript cache pada iterasi ini. Transcript penuh disimpan immutable di memori selama satu job.
- Transcript panjang tetap melewati prefilter Gemini yang sudah ada di `clipper_ai.py:208-250`.
- Captions mati + SRT tersedia: nol panggilan Groq.
- Captions mati + SRT tidak tersedia: satu tahap Groq penuh tetap diperlukan agar Gemini mendapat transcript.
- Captions hidup + SRT tersedia: satu panggilan Groq per klip terpilih.
- Captions hidup + SRT tidak tersedia: satu tahap Groq penuh; nol STT ulang per klip.
- Audio lebih dari batas upload boleh menghasilkan beberapa request chunk. Ini tetap satu tahap transkripsi logis.
- Cleanup untuk VPS wajib berbasis bukti: hapus hanya package, file, folder, function, dan kode yang terbukti tidak dipakai lewat search/import/build/test.
- Jangan commit perubahan tanpa permintaan eksplisit.

---

## Stage Map

1. **Kontrak transcript bertimestamp** → tipe JSON-safe, validasi, formatting untuk Gemini, slicing/rebase teruji.
2. **Klien Groq tunggal** → audio kecil/besar menghasilkan transcript word+segment konsisten, retry terbatas, cleanup teruji.
3. **Pipeline hybrid dan caption reuse** → kedua jalur SRT/no-SRT memenuhi jumlah panggilan Groq yang ditetapkan.
4. **Konfigurasi backend dan penghapusan local Whisper** → default/migrasi Groq aman, secret terpisah, dependency lokal hilang.
5. **UI dua provider** → Gemini dan Groq dapat disimpan, dicek, diganti, dan dihapus independen.
6. **Cleanup VPS** → package, file, folder, function, dan kode mati terhapus hanya setelah bukti pemakaian negatif dan checks lolos.
7. **Verifikasi penuh** → backend tests, compile, frontend lint/build, smoke test dua jalur, dan manifest deployment bersih lolos.

## File Map

- Modify `clipper_shared.py`: tipe dan pure functions transcript bertimestamp.
- Modify `clipper_ai.py`: request Groq, chunking, retry, normalisasi respons.
- Modify `clipper_core.py`: orkestrasi SRT/no-SRT serta distribusi transcript per klip.
- Modify `clipper_export.py`: buat ASS dari transcript supplied atau Groq per klip.
- Modify `clipper_base.py`: hapus atribut local Whisper yang usang.
- Modify `job_manager.py`: default Groq, engine API, provider check, key lifecycle.
- Modify `config/config_manager.py`: default dan migrasi provider.
- Modify `frontend/src/components/layout/DashboardLayout.tsx`: state settings Gemini/Groq.
- Modify `frontend/src/pages/Settings.tsx`: UI dan aksi kedua provider.
- Modify `requirements.txt`: hapus `faster-whisper`.
- Modify `PRODUCT.md`: ubah kontrak produk dari local Whisper ke Groq.
- Modify `README.md`: dokumentasikan dua provider dan dua API key.
- Modify `tests/test_job_manager.py`: contract, flow, config, cleanup, dan regression tests.
- Audit/delete unused packages, files, folders, functions, and dead code before VPS deployment.

---

### Task 1: Timed Transcript Contract

**Files:**
- Modify: `clipper_shared.py:1-35`
- Test: `tests/test_job_manager.py`

**Interfaces:**

```python
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


def validate_timed_transcript(transcript: TimedTranscript, require_words: bool = False) -> TimedTranscript: ...
def timed_segments_to_prompt(transcript: TimedTranscript) -> str: ...
def slice_timed_transcript(transcript: TimedTranscript, start: float, end: float) -> TimedTranscript: ...
```

**Contract:**

- Semua timestamp berupa detik media sumber.
- Full transcript memakai waktu absolut dari awal audio.
- Hasil `slice_timed_transcript` memakai waktu relatif dari awal klip.
- Item overlap memakai interval setengah-terbuka: `item.end > start and item.start < end`.
- Item yang melewati batas dipotong ke batas klip.
- Input tidak pernah dimutasi.
- Reject NaN, infinity, timestamp negatif, `end <= start`, durasi negatif, dan teks kosong.
- Sort stabil berdasarkan `(start, end)`.
- `require_words=True` menolak hasil tanpa word timestamp.

- [ ] **Step 1: Tambah failing tests untuk validasi dan slicing**

```python
def test_slice_timed_transcript_rebases_and_clamps_without_mutation():
    source = {
        "duration": 20.0,
        "words": [
            {"word": "awal", "start": 4.8, "end": 5.2},
            {"word": "tengah", "start": 6.0, "end": 6.5},
            {"word": "akhir", "start": 8.8, "end": 9.2},
        ],
        "segments": [{"text": "awal tengah akhir", "start": 4.8, "end": 9.2}],
    }
    original = json.loads(json.dumps(source))
    sliced = slice_timed_transcript(source, 5.0, 9.0)
    assert sliced == {
        "duration": 4.0,
        "words": [
            {"word": "awal", "start": 0.0, "end": 0.2},
            {"word": "tengah", "start": 1.0, "end": 1.5},
            {"word": "akhir", "start": 3.8, "end": 4.0},
        ],
        "segments": [{"text": "awal tengah akhir", "start": 0.0, "end": 4.0}],
    }
    assert source == original


def test_slice_timed_transcript_uses_half_open_boundaries():
    source = {
        "duration": 10.0,
        "words": [
            {"word": "before", "start": 4.0, "end": 5.0},
            {"word": "inside", "start": 5.0, "end": 6.0},
            {"word": "after", "start": 7.0, "end": 8.0},
        ],
        "segments": [{"text": "inside", "start": 5.0, "end": 6.0}],
    }
    assert [item["word"] for item in slice_timed_transcript(source, 5.0, 7.0)["words"]] == ["inside"]
```

- [ ] **Step 2: Jalankan tests dan pastikan gagal karena interface belum ada**

Run: `pytest tests/test_job_manager.py -q`

Expected: FAIL pada import/function transcript baru.

- [ ] **Step 3: Implementasikan tipe dan pure functions di `clipper_shared.py`**

Gunakan `math.isfinite`, dictionary baru, `round(value, 3)` hanya pada hasil slice, serta formatter timestamp `HH:MM:SS,mmm`. `timed_segments_to_prompt` harus menghasilkan format yang sudah dipahami Gemini:

```text
[00:01:10,200 - 00:01:14,800] isi ucapan
```

- [ ] **Step 4: Tambah invalid-input tests**

Kasus wajib: NaN, infinity, negatif, range terbalik, `require_words=True` dengan `words=[]`, item boundary, overlap dua klip, dan input tidak termutasi.

- [ ] **Step 5: Jalankan contract tests**

Run: `pytest tests/test_job_manager.py -q`

Expected: seluruh timed-transcript tests PASS.

---

### Task 2: Groq Word + Segment Transcription

**Files:**
- Modify: `clipper_ai.py:612-1050`
- Test: `tests/test_job_manager.py`

**Interfaces:**

```python
MAX_GROQ_UPLOAD_BYTES = 20 * 1024 * 1024


def _transcribe_groq_chunk(self, audio_path: str, time_offset: float = 0.0) -> TimedTranscript: ...
def transcribe_audio_with_timestamps(self, audio_path: str, require_words: bool = False) -> TimedTranscript: ...
```

**Request contract:**

```python
form_data = [
    ("model", self.whisper_model),
    ("response_format", "verbose_json"),
    ("timestamp_granularities[]", "word"),
    ("timestamp_granularities[]", "segment"),
]
```

Tambahkan `language=self.subtitle_language` kecuali nilainya kosong, `none`, atau `auto`.

**Failure contract:**

- Retry maksimal tiga attempt hanya untuk timeout, HTTP 429, dan HTTP 5xx.
- Gunakan `Retry-After` bila valid; batasi sleep maksimum 30 detik.
- HTTP 400/401/403 gagal langsung dengan status, provider base URL, dan model; jangan sertakan key.
- Respons tanpa segment gagal selalu.
- Respons tanpa words gagal ketika `require_words=True`.
- Semua temp chunk dihapus lewat satu `finally` pada success, failure, dan cancellation.

- [ ] **Step 1: Tambah failing test request/response Groq**

Mock `requests.post`; assert endpoint berakhir `/audio/transcriptions`, model `whisper-large-v3-turbo`, `verbose_json`, kedua granularitas, dan language `id`. Respons fixture:

```python
{
    "duration": 2.0,
    "text": "halo dunia",
    "words": [
        {"word": "halo", "start": 0.0, "end": 0.8},
        {"word": "dunia", "start": 0.9, "end": 1.8},
    ],
    "segments": [{"text": "halo dunia", "start": 0.0, "end": 1.8}],
}
```

Expected normalized result: plain dictionaries; tidak ada `SimpleNamespace`.

- [ ] **Step 2: Jalankan failing Groq tests**

Run: `pytest tests/test_job_manager.py -q`

Expected: FAIL karena helper baru belum tersedia.

- [ ] **Step 3: Ganti implementasi API Whisper yang duplikatif**

- Jadikan `transcribe_audio_with_timestamps` satu entry point untuk full audio dan audio klip.
- Gunakan `self.caption_client.base_url`, `self.caption_client.api_key`, dan `self.whisper_model` yang sudah dibangun di `clipper_core.py:81-87`.
- Pertahankan progress heartbeat, cancellation check, dan `report_tokens(0, 0, duration, 0)`.
- Jangan retry tanpa timestamp granularities; downgrade tersebut menghilangkan word timing dan merusak caption karaoke.
- Pertahankan `_whisper_transcribe_words` hanya sebagai compatibility wrapper API untuk legacy caller yang masih aktif; wrapper tidak boleh punya cabang lokal.

- [ ] **Step 4: Implementasikan chunking file besar**

- Probe durasi audio sekali.
- Jika ukuran `<= MAX_GROQ_UPLOAD_BYTES`, upload langsung.
- Jika lebih besar, hitung jumlah chunk dari rasio ukuran, encode setiap chunk menjadi MP3 16 kHz mono 32 kbps, lalu tambahkan `time_offset` absolut.
- Gabungkan words/segments, sort, validasi, dan set `duration` dari media probe; bukan dari kata terakhir.
- Satu file besar boleh menghasilkan beberapa request, tetapi hanya satu pemanggilan `transcribe_audio_with_timestamps` dari pipeline.

- [ ] **Step 5: Tambah retry/chunk/cleanup tests**

Kasus wajib:

- chunk kedua mendapat offset absolut;
- HTTP 401 tidak di-retry;
- HTTP 429 lalu 200 menghasilkan dua attempts;
- HTTP 500 berhenti setelah tiga attempts;
- words kosong ditolak saat `require_words=True`;
- temp chunk hilang setelah success dan exception;
- language `auto` tidak dikirim.

- [ ] **Step 6: Jalankan Groq unit tests**

Run: `pytest tests/test_job_manager.py -q`

Expected: request, normalization, retry, chunk merge, dan cleanup tests PASS.

---

### Task 3: Hybrid Orchestration and Caption Reuse

**Files:**
- Modify: `clipper_core.py:207-367`
- Modify: `clipper_export.py:144-166,236-339,753-920`
- Test: `tests/test_job_manager.py:382-417,486-506,549-599`

**Interfaces:**

```python
def _process_clips_with_sections(
    self,
    url,
    highlights,
    total_clips,
    add_captions,
    add_hook,
    full_transcript: TimedTranscript | None = None,
): ...


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
): ...


def _create_caption_ass(
    self,
    input_path: str,
    clip_dir: Path,
    transcript: TimedTranscript | None = None,
) -> Path | None: ...
```

**Flow A — SRT tersedia:**

1. Parse SRT seperti sekarang.
2. Kirim transcript SRT ke Gemini.
3. Download section terpilih.
4. Jika caption aktif, extract MP3 16 kHz mono langsung dari section lalu panggil Groq.
5. Buat ASS dari word timing Groq.
6. Jika caption mati, jangan extract audio dan jangan panggil Groq.

**Flow B — SRT tidak tersedia:**

1. `download_audio_only(url)`.
2. `transcribe_audio_with_timestamps(audio_path, require_words=add_captions)`.
3. `timed_segments_to_prompt(full_transcript)` dikirim ke Gemini.
4. Setelah highlight dinormalisasi Gemini, slice transcript memakai start/end final.
5. Pass slice melalui `caption_transcript` ke worker.
6. `_create_caption_ass` memakai supplied transcript; tidak extract audio dan tidak memanggil Groq lagi.

- [ ] **Step 1: Ganti regression test no-SRT menjadi Groq-once test**

Perbarui `NoSubtitleCore` agar mencatat `transcribe_audio_with_timestamps`, transcript yang diterima Gemini, dan transcript slice yang diterima `process_clip`.

```python
def test_missing_srt_transcribes_once_and_reuses_words_for_caption(tmp_path):
    core = NoSubtitleCore()
    core.process("https://www.youtube.com/watch?v=abc", num_clips=2, add_captions=True)
    assert core.groq_calls == 1
    assert core.downloaded_audio == 1
    assert len(core.caption_transcripts) == 2
    assert core.caption_transcripts[0]["words"][0]["start"] >= 0
```

Tambahkan test `add_captions=False`: Groq tetap satu kali untuk Gemini, tetapi `caption_transcript` tidak diberikan ke export.

- [ ] **Step 2: Tambah SRT flow tests**

Kasus wajib:

- SRT + captions aktif: Gemini menerima SRT, full audio tidak diunduh, selected clip transcription dipanggil sekali per clip.
- SRT + captions mati: nol panggilan Groq.
- Parallel no-SRT dengan beberapa highlights: full Groq tetap satu kali dan setiap worker mendapat slice berbeda.

- [ ] **Step 3: Implementasikan branch orchestration di `clipper_core.py`**

Gunakan variabel lokal `full_transcript = None`. Jangan simpan transcript klip dalam mutable `self.current_transcript`. Buat slice baru sebelum `executor.submit`. Pass transcript sebagai argumen eksplisit agar worker aman.

- [ ] **Step 4: Pindahkan caption preparation ke awal export**

Di `process_clip`, panggil `_create_caption_ass` sesaat setelah `source_file` tersedia, sebelum `convert_to_portrait_with_progress`. Dampak:

- SRT flow mulai upload Groq segera setelah section selesai diunduh.
- No-SRT flow langsung membuat ASS dari memory.
- Portrait render tidak lagi mendahului STT.

- [ ] **Step 5: Ubah `_create_caption_ass`**

- `transcript is None`: extract `caption_audio.mp3`, panggil `transcribe_audio_with_timestamps(..., require_words=True)`.
- `transcript is not None`: validasi `require_words=True`, jangan extract audio, jangan transcribe.
- Supplied transcript kosong harus gagal jelas; jangan dianggap izin retranskripsi.
- Audio extraction failure saat caption diminta harus gagal, bukan menghasilkan video tanpa caption.

- [ ] **Step 6: Ubah ASS generator ke dictionary contract**

Ganti akses `.words`, `.word`, `.start`, `.end` menjadi dictionary JSON-safe. Escape `\`, `{`, `}`, dan newline dari teks sebelum menulis ASS agar transcript tidak menjadi override tag.

- [ ] **Step 7: Tambah no-retranscription dan ordering tests**

- supplied transcript membuat stub transcription yang melempar tetap tidak pernah dipanggil;
- event log menunjukkan caption preparation terjadi sebelum portrait conversion;
- rebased transcript dari sumber satu jam menghasilkan ASS mulai sekitar `0:00`, bukan `1:00:00`;
- literal `{teks}` dan backslash aman di ASS;
- zero-word supplied transcript gagal.

- [ ] **Step 8: Jalankan pipeline tests**

Run: `pytest tests/test_job_manager.py -q`

Expected: flow SRT/no-SRT, parallel reuse, ASS, dan render command regression tests PASS.

---

### Task 4: Provider Configuration and Remove Local Whisper

**Files:**
- Modify: `job_manager.py:21-22,183-276,339-382,515-559`
- Modify: `config/config_manager.py:18-95,98-170,172-201`
- Modify: `clipper_core.py:43-131`
- Modify: `clipper_base.py:25-67`
- Modify: `clipper_ai.py:1003-1049`
- Modify: `requirements.txt:1-17`
- Modify: `PRODUCT.md:15-27`
- Modify: `README.md:14-24`
- Test: `tests/test_job_manager.py:45-110,158-164`

**Backend settings contract:**

```json
{
  "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
  "api_key": "",
  "api_key_saved": true,
  "model": "gemini-2.5-flash",
  "caption_base_url": "https://api.groq.com/openai/v1",
  "caption_api_key": "",
  "caption_key_saved": true,
  "caption_model": "whisper-large-v3-turbo"
}
```

Secret field selalu dikembalikan sebagai string kosong. Flag saved hanya boolean.

- [ ] **Step 1: Tambah failing config/key lifecycle tests**

Kasus wajib:

- fresh config memakai default Gemini dan Groq yang tepat;
- save menyimpan dua key di provider masing-masing;
- blank key mempertahankan key tersimpan;
- `clear_highlight_api_key` tidak menghapus Groq;
- `clear_caption_api_key` tidak menghapus Gemini;
- legacy `clear_api_key` tetap menghapus keduanya;
- response tidak mengandung secret;
- partial `ai_providers` mendapat provider yang hilang;
- custom caption URL/model/key tidak ditimpa migration;
- old empty `https://api.openai.com/v1` + `whisper-1` dimigrasikan ke default Groq.

- [ ] **Step 2: Implementasikan constants/default/migration Groq**

Tambahkan constants backend:

```python
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "whisper-large-v3-turbo"
```

Migration rules:

- gunakan `setdefault` untuk field provider yang hilang;
- preserve seluruh nonempty key;
- preserve custom URL/model;
- migrate old OpenAI defaults hanya bila caption key kosong dan URL/model tepat sama dengan default lama;
- legacy single-provider migration tidak boleh menyalin Gemini key menjadi Groq key;
- hapus `subtitle_engine` dan `local_whisper` dari config yang dimuat.

- [ ] **Step 3: Perbaiki provider check**

Request menerima `provider_name` bernilai `highlight_finder` atau `caption_maker`.

- Highlight Finder: gunakan chat completion `Reply OK only.` seperti sekarang.
- Caption Maker: gunakan Models API untuk memastikan model tersedia; jangan mengirim dummy audio berbayar.
- Blank request key memakai saved key provider terkait.
- Nonblank request key menguji candidate key tanpa menyimpannya.
- Error dan success response tidak pernah memuat key.

- [ ] **Step 4: Hapus local Whisper production code**

- Hapus `subtitle_engine`, `local_whisper`, `_local_whisper_model` dari constructor dan base declarations.
- Hapus `_get_local_whisper_model`, `_whisper_transcribe_segments_local`, `_whisper_transcribe_words_local`, `transcribe_audio_local`, dan `transcribe_full_video_local`.
- Hapus hardcode local di `job_manager.py:268` dan `job_manager.py:554`.
- Semua caption/STT route memakai Caption Maker API.
- Hapus `faster-whisper>=1.1.0` dari `requirements.txt`.

- [ ] **Step 5: Update product documentation**

`PRODUCT.md` defaults menjadi:

```text
- Highlight finder: Gemini API.
- Subtitle engine: Groq Whisper API.
- Speech-to-text model: whisper-large-v3-turbo.
```

`README.md` menjelaskan Gemini key dan Groq key terpisah, local plaintext storage, serta kebutuhan network.

- [ ] **Step 6: Jalankan backend/config tests**

Run: `pytest tests/test_job_manager.py -q`

Expected: seluruh settings, migration, engine routing, dan pipeline tests PASS.

- [ ] **Step 7: Pastikan tidak ada production reference local Whisper**

Run:

```powershell
rg "faster_whisper|faster-whisper|local_whisper|_local_whisper_model|subtitle_engine" -g "*.py" -g "requirements.txt" -g "PRODUCT.md" -g "README.md" -g "*.tsx"
```

Expected: tidak ada output dari kode produksi atau dokumentasi aktif.

---

### Task 5: Gemini and Groq Settings UI

**Files:**
- Modify: `frontend/src/components/layout/DashboardLayout.tsx:15-26,40-53`
- Modify: `frontend/src/pages/Settings.tsx:5-84,94-151,226-250`

**State additions:**

```ts
caption_base_url: 'https://api.groq.com/openai/v1',
caption_api_key: '',
caption_model: 'whisper-large-v3-turbo',
api_key_saved: false,
caption_key_saved: false,
```

- [ ] **Step 1: Tambah state default kedua provider**

Pertahankan key inputs kosong setelah reload. Merge respons settings tanpa menyalin secret ke browser.

- [ ] **Step 2: Pisahkan UI menjadi dua card**

Card 1:

```text
Highlight Finder — Gemini
Base URL
Gemini API Key
Model
Check Gemini
Hapus Gemini API Key
```

Card 2:

```text
Caption Maker — Groq
Base URL
Groq API Key
Transcription Model
Check Groq
Hapus Groq API Key
```

Tampilkan `API key tersimpan` berdasarkan flag masing-masing. Hapus placeholder ambigu `Gemini/Groq API key`.

- [ ] **Step 3: Implementasikan independent provider checks**

Payload Gemini:

```json
{
  "provider_name": "highlight_finder",
  "base_url": "...",
  "api_key": "...",
  "model": "..."
}
```

Payload Groq:

```json
{
  "provider_name": "caption_maker",
  "base_url": "...",
  "api_key": "...",
  "model": "..."
}
```

Gunakan state loading/success/error terpisah agar hasil satu provider tidak menimpa provider lain.

- [ ] **Step 4: Implementasikan save dan clear yang aman**

- Save memakai response `res.settings` untuk refresh saved flags.
- Empty untouched input mempertahankan key backend.
- Hapus Gemini mengirim `clear_highlight_api_key=true`.
- Hapus Groq mengirim `clear_caption_api_key=true`.
- Setelah save/clear, reset `api_key` dan `caption_api_key` menjadi kosong.
- Hilangkan tombol footer `Hapus API Key` yang ambigu.

- [ ] **Step 5: Jalankan frontend lint**

Run: `npm run lint`

Workdir: `frontend`

Expected: exit code 0.

- [ ] **Step 6: Jalankan frontend build/typecheck**

Run: `npm run build`

Workdir: `frontend`

Expected: `tsc -b` dan Vite build exit code 0.

---

### Task 6: VPS Cleanup and Dead Code Removal

**Files:**
- Modify: `requirements.txt`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: production/test files identified by audit
- Delete: unused files/folders identified by audit
- Test: `tests/test_job_manager.py`

**Cleanup policy:**

- Hapus hanya setelah minimal dua bukti: static search/import graph + successful tests/build setelah removal.
- Jangan hapus runtime artifact yang sengaja local-only: `config.json`, `cookie.txt`, `cookies.txt`, `output/`, `_temp/`, `cache/`; pastikan tetap ignored dan tidak masuk deployment artifact.
- Jangan hapus dependency yang hanya dipakai oleh import dinamis, CLI runtime, generated frontend, OAuth, atau optional platform path sebelum ada test/smoke yang menutupinya.
- Dokumentasikan setiap penghapusan dengan alasan singkat di final implementation summary, bukan dalam komentar kode.

- [ ] **Step 1: Buat inventory file/folder root**

Run:

```powershell
Get-ChildItem -LiteralPath . -Force | Sort-Object Name | ForEach-Object { $_.Name }
```

Expected: daftar root terbaca; tandai kandidat seperti plan lama, mockup lama, cache, output, build artifact, dan file temporary. Jangan hapus apa pun di step ini.

- [ ] **Step 2: Audit Python imports dan dependency runtime**

Run:

```powershell
@'
import ast, pathlib
for path in pathlib.Path('.').glob('**/*.py'):
    if any(part in {'.venv','venv','__pycache__'} for part in path.parts):
        continue
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'))
    except Exception as exc:
        print(f'PARSE_FAIL {path}: {exc}')
        continue
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split('.')[0])
    print(f'{path}: {", ".join(sorted(set(imports)))}')
'@ | python -
```

Expected: import list lengkap. Cocokkan dengan `requirements.txt`. Kandidat awal setelah Groq migration: `faster-whisper` harus hilang; package lain hanya boleh dihapus jika tidak ada import dan bukan optional runtime.

- [ ] **Step 3: Audit frontend dependencies**

Run:

```powershell
node -e "const fs=require('fs'); const p=require('./frontend/package.json'); console.log(Object.keys({...p.dependencies,...p.devDependencies}).sort().join('\n'))"
rg "from ['\"]([^'\"]+)['\"]|import\(['\"]([^'\"]+)['\"]\)" frontend/src frontend/*.config.* frontend/*.ts frontend/*.tsx
```

Expected: dependency list dan imports terbaca. Hapus dependency UI/library hanya jika tidak muncul di source/config dan build tetap lolos.

- [ ] **Step 4: Audit symbol/function dead code Python**

Run:

```powershell
rg "def |class " -g "*.py"
```

Untuk setiap kandidat function/class:

```powershell
rg "candidate_name" -g "*.py" -g "*.md" -g "*.tsx" -g "*.ts"
```

Expected: hanya hapus jika referensi tinggal definisi/test lama dan tidak dipanggil via dynamic name. Kandidat dari perubahan Groq: legacy `_process_clip_legacy`, `add_captions_api`, `add_captions_api_with_progress`, `find_highlights_with_transcription`, `find_highlights_only`, `process_selected_highlights`, dan old Whisper wrappers; hapus hanya setelah referensi nol.

- [ ] **Step 5: Audit folders/files non-runtime**

Run:

```powershell
rg "reference-ui|optimize.md|ttsplan.md|plan/|__pycache__|dist|build|node_modules" -g "*"
```

Expected: identifikasi folder/file yang tidak dibutuhkan VPS runtime. Kandidat aman setelah verifikasi:

- `__pycache__/`, `.pytest_cache/`, frontend `dist/` hasil lokal sebelum build fresh;
- dokumentasi plan lama yang tidak dipakai runtime;
- `reference-ui/` jika tidak direferensikan runtime;
- `optimize.md`, `ttsplan.md`, `plan/` jika hanya catatan lama.

Jangan hapus `docs/superpowers/plans/2026-07-10-groq-gemini-transcription-pipeline.md` selama implementasi masih berjalan.

- [ ] **Step 6: Hapus kandidat satu kategori per commit-sized batch**

Urutan batch:

1. Local/cache/build artifacts.
2. Unused docs/mockups/plans lama.
3. Dead Python functions/classes.
4. Unused Python packages.
5. Unused frontend packages.

Setelah setiap batch jalankan checks minimal:

```powershell
pytest tests/test_job_manager.py -q
python -m compileall .
```

Untuk frontend package/file batch:

```powershell
npm run lint
npm run build
```

Workdir frontend untuk dua command npm.

- [ ] **Step 7: Tambah regression tests untuk function yang dipertahankan karena terlihat unused**

Jika audit menemukan function yang tampak unused tetapi wajib runtime dynamic/route/CLI, tambah test kecil atau catatan README deployment. Contoh: route method di `server.py`, OAuth helper, upload helper, path resolver.

- [ ] **Step 8: Buat deployment manifest bersih**

Tambahkan section README `VPS deploy checklist` berisi:

```text
Include:
- Python source files
- frontend source or built assets sesuai strategi deploy
- requirements.txt
- package.json/package-lock.json jika build di VPS
- README.md / PRODUCT.md

Exclude:
- config.json
- cookie.txt / cookies.txt
- output/
- cache/
- _temp/
- __pycache__/
- .pytest_cache/
- node_modules/
- frontend/dist/ kecuali deploy memakai prebuilt static assets
```

- [ ] **Step 9: Verifikasi tidak ada secret atau artifact besar masuk git/deploy**

Run:

```powershell
git status --short
rg "AIza|sk-|gsk_|Bearer |api_key\":\s*\"[^\"]+" -g "*" --glob "!config.json" --glob "!cookie.txt" --glob "!cookies.txt" --glob "!node_modules/**" --glob "!frontend/package-lock.json"
```

Expected: tidak ada secret di tracked/planned files. Jika ada, hapus atau ganti placeholder sebelum lanjut.

---

### Task 7: Full Verification and Smoke Tests

**Files:**
- Verify only; perbaikan tetap dilakukan pada file pemilik bug.

- [x] **Step 1: Jalankan backend suite penuh**

Run: `pytest`

Expected: exit code 0.

- [x] **Step 2: Jalankan Python compile check**

Run: `python -m compileall .`

Expected: exit code 0.

- [x] **Step 3: Jalankan frontend checks ulang**

Run: `npm run lint`

Workdir: `frontend`

Expected: exit code 0.

Run: `npm run build`

Workdir: `frontend`

Expected: exit code 0.

- [x] **Step 4: Smoke test video dengan SRT**

Acceptance:

- log menunjukkan SRT dipakai untuk Gemini;
- full audio fallback tidak diunduh;
- captions aktif menghasilkan satu Groq transcription per selected clip;
- Groq mulai setelah section download dan sebelum portrait render;
- caption sinkron dari awal klip;
- captions mati menghasilkan nol Groq call.

- [x] **Step 5: Smoke test video tanpa SRT Indonesia**

Acceptance:

- audio-only diunduh satu kali;
- satu tahap full Groq selesai sebelum Gemini;
- Gemini menerima transcript bertimestamp segment;
- selected clips tidak meng-upload audio lagi ke Groq;
- caption memakai word timing hasil full transcript yang sudah di-rebase;
- parallel workers tidak menambah jumlah full transcription.

- [x] **Step 6: Verifikasi cleanup VPS**

Acceptance:

- `requirements.txt` hanya berisi dependency Python yang dipakai runtime/test.
- `frontend/package.json` hanya berisi dependency yang dipakai source/config/build.
- Tidak ada `faster-whisper`, local Whisper code, dead caption API legacy, cache artifact, build artifact lokal, atau folder mockup lama di deployment set.
- `git status --short` hanya menampilkan file yang memang bagian perubahan.
- README punya checklist include/exclude untuk VPS.

- [x] **Step 7: Security regression check**

Cari nilai API key uji pada response settings, logs, `data.json`, file output, dan deployment manifest. Expected: tidak ditemukan. Pastikan error 401/403 menyebut provider/model tanpa token.

## Deliberate Simplifications

- Tidak ada persistent transcript cache. Tambahkan hanya jika retry lintas restart menjadi kebutuhan nyata.
- Tidak ada Groq SDK. Raw multipart request yang ada sudah memenuhi endpoint.
- Tidak ada semaphore API khusus. Tambahkan hanya jika produksi membuktikan HTTP 429 karena worker paralel pada jalur SRT.
- Tidak ada fallback caption berbasis segment. Word timestamp wajib saat caption aktif agar efek karaoke tetap akurat.
- Tidak mengubah prefilter Gemini 35.000 karakter. Evaluasi recall highlight secara terpisah bila video panjang terbukti kehilangan momen penting.
- Tidak membuat bundler/deploy script baru. Cleanup cukup memastikan source dan manifest deploy bersih; automation deploy bisa ditambah setelah VPS target pasti.

## Done Criteria

- Semua automated checks exit code 0.
- Tidak ada import/dependency/config local `faster-whisper` aktif.
- SRT path dan no-SRT path memenuhi call-count contract.
- No-SRT captions menggunakan timestamp full Groq tanpa STT ulang.
- SRT captions memakai Groq hanya untuk klip terpilih.
- Gemini dan Groq keys dikelola independen serta tidak bocor.
- Caption mulai pada timeline klip, bukan timeline video sumber.
- Project siap VPS: dependency, file, folder, function, dan kode mati yang terbukti unused sudah dihapus; README deployment include/exclude jelas.
