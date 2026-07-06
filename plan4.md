# KlipKlop Plan 4

## 1. Clean JSON Preview for Local Subtitle Engine

Problem:
- JSON masih menampilkan `caption_base_url`, `caption_model`, `caption_api_key` walaupun `subtitle_engine = "local"`.
- Local faster-whisper tidak pakai API URL/key, jadi membingungkan.

Fix:
- Buat JSON preview conditional.
- Kalau `subtitle_engine: "local"`:
```json
{
  "subtitle_engine": "local",
  "local_whisper": {
    "enabled": true,
    "model": "small",
    "device": "cpu",
    "compute_type": "int8"
  }
}
```
- Jangan tampilkan:
  - `caption_base_url`
  - `caption_model`
  - `caption_api_key`

Files:
- `static/app.js`

Status: pending

---

## 2. API Fields Only for API Whisper

Behavior:
- Engine `Local faster-whisper`:
  - UI sembunyikan API Whisper URL/model/key.
  - JSON sembunyikan API fields.
- Engine `API Whisper`:
  - UI tampilkan API Whisper URL/model/key.
  - JSON tampilkan API fields.
- Engine `Auto`:
  - UI boleh tampilkan API fields sebagai optional.
  - JSON tampilkan API fields hanya kalau user isi key / field non-default.

Files:
- `index.html`
- `static/app.js`

Status: pending

---

## 3. Settings Payload Cleanup

Problem:
- Satu payload dipakai untuk save backend dan JSON preview, sehingga JSON preview terlalu teknis.

Fix:
- Split:
  - `settingsPayload()` = payload lengkap untuk save backend.
  - `previewPayload()` = payload bersih untuk JSON preview.
- `showPayloadJson()` pakai `previewPayload()`, bukan raw `settingsPayload()`.

Files:
- `static/app.js`

Status: pending

---

## 4. Console Task Header Plain Text

Problem:
- Header task di Konsol sekarang pakai kotak ungu.
- User ingin tampilan console biasa, tanpa warna khusus.

Fix:
- Hapus style khusus `[Task]`.
- Render sebagai plain monospaced text.
- Format:
```text
============================================================
TASK 06 Jul 2026 22:36:49
URL: https://www.youtube.com/watch?v=AH--25o6LsA
============================================================
```

Implementation:
- Backend boleh tetap `_add_log(..., "Task")`.
- Frontend `renderLogLine()`:
  - jangan render div ungu untuk `[Task]`
  - parse line task → render separator plain text
  - error tetap merah, done tetap hijau minimal

Files:
- `static/app.js`
- optional `job_manager.py`

Status: pending

---

## 5. Hide Raw FFmpeg Command from Home Status

Problem:
- Home status menampilkan command FFmpeg panjang.
- UI jadi berantakan.

Fix:
- Home status hanya human-readable:
  - `Memotong video...`
  - `Membuat portrait...`
  - `Menambahkan subtitle...`
  - `Finalizing...`
- Raw FFmpeg command tetap masuk Konsol/log detail.
- Sanitasi `status-text`:
  - kalau message mengandung `ffmpeg.exe`
  - atau `-progress pipe`
  - atau mulai dengan path quoted
  - tampilkan label pendek.

Files:
- `job_manager.py`
- `static/app.js`
- optional `clipper_ffmpeg.py`

Status: pending

---

## 6. Smooth Loading Progress

Problem:
- Progress terasa patah/kurang smooth.
- Kadang loncat karena FFmpeg progress parsing belum granular.

Fix:
- CSS transition progress bar:
```css
transition: width 300ms ease;
```
- Frontend smoothing:
  - backend kirim target progress
  - UI animate current progress menuju target
- Backend stage messages:
  - Download
  - Cut
  - Portrait
  - Subtitle
  - Finalize
- Jangan spam UI dengan command mentah.

Files:
- `index.html`
- `static/app.js`
- optional `clipper_ffmpeg.py`

Status: pending

---

## 7. Console Scroll Fix

Problem:
- Console panel tidak bisa scroll sampai atas.
- Kemungkinan nested height/overflow issue.

Fix:
- Page Konsol:
  - `h-[calc(100vh-180px)]`
  - `overflow-y-auto`
  - internal log panel scroll sendiri
- Auto-scroll hanya kalau user sedang dekat bottom.
- Kalau user scroll ke atas, jangan dipaksa turun.
- Tambah tombol optional:
  - `Bottom`
  - `Top`

Files:
- `index.html`
- `static/app.js`

Status: pending

---

## 8. Dynamic Subtitle Placement

Goal:
- Posisi subtitle otomatis, tidak statis.
- Tidak pakai AI dulu; pakai video analysis lokal.

Approach v1:
- Sample beberapa frame dari clip final/portrait.
- Analisis 3 zona:
  - top
  - middle-lower
  - bottom
- Skor tiap zona:
  - brightness terlalu terang/gelap
  - edge/detail terlalu ramai
  - area foreground utama
  - blur landscape area
- Pilih zona dengan skor terbaik.
- Generate ASS per clip:
  - `Alignment`
  - `MarginV`
  - background box tetap ON.

Rules:
- Blur landscape → prioritaskan area blur bawah.
- Portrait/crop → bottom safe area default.
- Kalau bawah ramai → pindah middle/top.

Config:
```json
"subtitle_position": "auto"
```

Options:
- `auto`
- `top`
- `middle`
- `bottom`

UI:
- Subtitle Position dropdown.
- Default: `Auto`.

Files:
- `index.html`
- `static/app.js`
- `config/config_manager.py`
- `job_manager.py`
- `clipper_core.py`
- `clipper_export.py`

Status: pending

---

## 9. Floating JSON Preview

Problem:
- JSON preview inline di Beranda makan ruang.
- User ingin JSON muncul floating saat tombol JSON diklik.

Fix:
- Hapus inline `<pre id="payload-json">` dari form flow.
- Buat floating panel/modal:
  - title: `Payload JSON`
  - close button
  - copy button optional
- Klik tombol `JSON`:
  - buka floating panel
  - isi JSON live update.
- Saat panel terbuka, perubahan form tetap update JSON.
- Saat panel tertutup, layout Beranda tetap rapi.

Files:
- `index.html`
- `static/app.js`

Status: pending

---

## Verification Checklist

1. Local subtitle engine selected → JSON tidak menampilkan API fields.
2. API Whisper selected → JSON menampilkan API fields.
3. JSON preview floating, bukan inline.
4. JSON live update saat form berubah.
5. Console task header plain text dengan separator `====`.
6. Home status tidak menampilkan raw FFmpeg command.
7. Progress bar smooth.
8. Console bisa scroll ke atas dan bawah.
9. Auto-scroll tidak mengganggu saat user scroll manual.
10. Subtitle position `auto` memilih area readable.
11. Blur landscape → subtitle di area blur bawah kalau aman.
12. Checks:
    - `py -3.12 -m py_compile ...`
    - `node --check static\app.js`
    - `py -3.12 tests\test_job_manager.py`
