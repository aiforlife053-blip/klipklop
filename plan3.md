# KlipKlop Plan 3

## 1. Caption UI Rename + Local Default

Problem: `Caption Maker URL/Model/API Key` membingungkan. User ingin subtitle gratis pakai local model dulu.

Fix:
- Ganti label UI menjadi `Subtitle Engine`.
- Default engine: `Local faster-whisper`.
- Default local model: `small`.
- Sembunyikan API Whisper fields kecuali user pilih `API Whisper`.

Behavior:
- `Suntik Subtitel` ON:
  - Engine `Local faster-whisper` → pakai local `faster-whisper` model `small`.
  - Engine `API Whisper` → pakai Caption/API key.
  - Engine `Auto` → pakai API kalau key ada, fallback local kalau tidak ada.

Config:
```json
"subtitle_engine": "local",
"local_whisper": {
  "enabled": true,
  "model": "small",
  "device": "cpu",
  "compute_type": "int8"
}
```

Files:
- `index.html`
- `static/app.js`
- `job_manager.py`
- `config/config_manager.py`
- `clipper_core.py`
- `clipper_ai.py`
- `clipper_export.py`

Status: pending

---

## 2. Add Local faster-whisper Subtitle Path

Goal: subtitle gratis tanpa API key.

Install:
```bash
pip install faster-whisper
```

Implementation:
- Extract audio from clip.
- Load `WhisperModel("small", device="cpu", compute_type="int8")` lazily.
- Transcribe with:
  - `language=subtitle_language`
  - `word_timestamps=True`
- Convert words/segments into existing ASS subtitle path.
- Burn subtitle with FFmpeg.

Logs:
- `Using local faster-whisper: small/cpu/int8`
- `Local Whisper OK`
- `ASS events: N`
- `Subtitle burn OK`

Fallback:
- If local package missing → error jelas:
  - `faster-whisper belum terinstall. Run: pip install faster-whisper`

Status: pending

---

## 3. Remove Save Button, Keep JSON

Problem: tombol `Save` di form membingungkan.

Fix:
- Hapus tombol `Save` di form utama.
- Tombol `JSON` tetap ada.
- JSON harus live update saat user mengubah:
  - jumlah klip
  - kualitas
  - blur
  - subtitle toggle
  - subtitle engine/model
  - URL
  - instruction

Files:
- `index.html`
- `static/app.js`

Status: pending

---

## 4. Subtitle Readability on Blur Mode

Problem: subtitle belum mudah dibaca / belum muncul jelas.

Fix:
- Subtitle wajib punya background box semi-transparent.
- Default style:
  - Font: `Arial Black`
  - Size: adaptive per resolution
  - Alignment: bottom-center
  - Outline: black
  - Shadow: enabled
  - Background box: semi-transparent black
- Kalau `landscape_blur` ON:
  - Posisi subtitle di area blur bawah jika foreground landscape tidak memenuhi portrait.
  - Jangan nutup wajah/foreground utama.
- Kalau crop mode:
  - Posisi subtitle tetap bottom safe area.

Files:
- `clipper_export.py`
- `clipper_core.py`
- `job_manager.py`
- `config/config_manager.py`

Status: pending

---

## 5. Fix Subtitle ON/OFF Reliability

Problem: user sudah ON tapi output bisa `has_captions: false`.

Fix:
- Preserve checkbox state saat `saveSettings()` dipanggil.
- Start payload selalu kirim:
  - `add_captions`
  - `enable_captions`
- Metadata `data.json` harus sesuai pilihan user.
- Jika subtitle ON tapi engine/key/local model gagal → error jelas, jangan render tanpa subtitle diam-diam.

Verification:
- `data.json` output dengan subtitle ON harus punya:
```json
"has_captions": true
```

Status: pending

---

## 6. Console Clear + No Auto Navigation

Problem:
- Clear console bisa menampilkan `[Error] Not found`.
- Generate klip jangan auto pindah ke page Konsol.

Fix:
- Clear endpoint robust:
  - `/api/logs/clear`
  - `/api/clear-logs`
  - `/api/clear_logs`
- UI clear langsung kosongkan console, jangan tampilkan error lama.
- Klik `Proses Klip` tetap di Beranda.
- User buka Konsol manual dari nav kiri.

Files:
- `server.py`
- `job_manager.py`
- `static/app.js`

Status: pending

---

## 7. JSON Preview Live Update

Problem: JSON preview bisa stale setelah user ubah jumlah klip/settings.

Fix:
- JSON preview live update on `input` and `change` events.
- Setelah klik JSON, preview tetap visible dan terus update.
- Isi JSON:
```json
{
  "settings": {},
  "start": {}
}
```

Files:
- `static/app.js`

Status: pending

---

## 8. Project Diagnostics Cleanup

Goal: bersihkan diagnostics editor (`130` error, `23` warning).

Findings awal:
- `py_compile` semua file Python: pass
- `node --check static/app.js`: pass
- `tests/test_job_manager.py`: 23 pass
- Jadi diagnostics kemungkinan dari editor/linter static, bukan runtime syntax.

Plan:
1. Ambil daftar diagnostics dari editor (`Ctrl+Shift+M`) atau copy error list.
2. Kelompokkan:
   - JS browser globals / DOM typing
   - Python unresolved imports
   - unused imports
   - generated/cache/output files ikut ke-diagnose
   - missing workspace config
3. Fix paling kecil:
   - ignore `output/`, `_temp/`, cache
   - minimal JS/Python config kalau diagnostics bogus
   - hapus unused imports yang aman
   - jangan refactor logic
4. Verification:
   - `py -3.12 -m py_compile ...`
   - `node --check static\app.js`
   - `py -3.12 tests\test_job_manager.py`
   - diagnostics count turun / nol

Status: pending

---

## Verification Checklist

1. Subtitle ON + no API key → local faster-whisper `small` jalan.
2. Log menampilkan `Using local faster-whisper: small/cpu/int8`.
3. Subtitle terlihat jelas dengan background box.
4. Blur ON → subtitle berada di area mudah dibaca.
5. Output metadata `has_captions: true` saat subtitle ON.
6. Tombol Save form hilang.
7. JSON preview tetap ada dan live update.
8. Clear console tidak menampilkan `[Error] Not found`.
9. Generate klip tidak auto pindah ke Konsol.
10. Checks pass:
    - `py -3.12 -m py_compile ...`
    - `node --check static\app.js`
    - `py -3.12 tests\test_job_manager.py`
