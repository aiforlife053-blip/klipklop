# KlipKlop Fix Plan 2

## 1. Preview Skip Buttons

Problem: Preview video native controls tidak menyediakan tombol skip cepat seperti YouTube.

Fix:
- Tambah tombol `-10s` dan `+10s` di setiap preview video.
- Berlaku untuk Home dan Riwayat.
- JS helper:
  - cari `<video>` terdekat dari tombol
  - update `currentTime`
  - clamp ke `0..duration`

Files:
- `static/app.js`

Status: pending

---

## 2. Durasi Clip Fleksibel

Problem: Sistem terlalu terpaku 60 detik / range 45–75s, padahal clip harus mengikuti konteks.

Behavior baru:
- AI pilih segment berdasarkan konteks cerita.
- Tidak wajib 60 detik.
- Maksimum durasi: 120 detik.
- Minimum safety: 10 detik.
- Segment >120s dipangkas ke `start + 120s` jika masih masuk akal.
- Segment <10s ditolak.

Files:
- `clipper_ai.py`

Status: pending

---

## 3. Fix AI 0 Valid Clips

Problem: AI sudah menemukan momen bagus, tapi semua dibuang karena filter `45 <= duration <= 75`.

Fix:
- Hapus strict filter 45–75s.
- Ganti validasi:
  - `<10s` → reject
  - `10–120s` → accept
  - `>120s` → trim ke 120s lalu accept
- Log baru:
  - `accepted`
  - `trimmed to 120s`
  - `too short, skipped`

Files:
- `clipper_ai.py`

Status: pending

---

## 4. Subtitle ON/OFF Clarity

Problem: Toggle subtitle terlihat aktif, tapi user tidak tahu apakah benar-benar dipakai saat render.

Fix:
- Pastikan toggle mengirim `add_captions` ke backend.
- Log jelas:
  - `Subtitles: ON/OFF`
  - `Whisper OK`
  - `ASS events: N`
  - `Subtitle burn OK`
- Kalau subtitle OFF, log `Skipped captions (disabled)`.

Files:
- `static/app.js`
- `job_manager.py`
- `clipper_export.py`

Status: pending

---

## 5. Subtitle Style Settings

Problem: Font dan posisi subtitle hardcoded, tidak bisa diatur dari UI.

Default sekarang:
- Font: `Arial Black`
- Size: `65`
- Position: bottom margin `400`
- Alignment: `2` (bottom center)

Fix:
- Tambah setting subtitle style:
  - Font
  - Size
  - Vertical position / bottom margin
- Simpan ke config.
- Pakai setting di ASS style.

Files:
- `index.html`
- `static/app.js`
- `job_manager.py`
- `config/config_manager.py`
- `clipper_core.py`
- `clipper_export.py`

Status: pending

---

## 6. Fix Subtitle Tidak Muncul

Problem: Log subtitle bisa sukses, tapi hasil video tidak menampilkan subtitle.

Kemungkinan penyebab:
- ASS event kosong.
- Path ASS Windows salah escape.
- FFmpeg subtitle burn gagal lalu fallback copy tanpa subtitle.

Fix:
- Setelah create ASS, hitung jumlah events.
- Jika `events == 0` → error jelas, jangan lanjut silent.
- Perbaiki path ASS Windows.
- Kalau burn gagal → tampil error, jangan copy diam-diam.
- Log output:
  - `ASS events: N`
  - `Subtitle burn OK`

Files:
- `clipper_export.py`

Status: pending

---

## 7. Progress Download Ngulang

Problem: Log download terlihat 100% lalu mulai 0% lagi.

Penyebab:
- yt-dlp download stream video dan audio terpisah.
- Progress hook reset per stream, terlihat seperti download ulang.

Fix:
- Ubah label jadi phase-aware: `Downloading video/audio...`.
- Dedupe log progress agar tidak spam.
- Tetap satu source download; bukan bug download dua kali.

Files:
- `clipper_download.py`
- `job_manager.py`

Status: pending

---

## Verification Checklist

1. Preview Home: tombol `-10s` dan `+10s` bekerja.
2. Preview Riwayat: tombol `-10s` dan `+10s` bekerja.
3. AI menerima clip 10–120s.
4. AI trim clip >120s ke 120s.
5. Subtitle ON → Whisper OK, ASS events >0, subtitle terlihat di video.
6. Subtitle OFF → caption step dilewati.
7. Subtitle style setting mengubah font/size/posisi.
8. Download progress tidak terlihat ngulang membingungkan.
9. Checks:
   - `py -3.12 -m py_compile clipper_ai.py clipper_export.py clipper_download.py job_manager.py config\config_manager.py`
   - `node --check static\app.js`
   - `py -3.12 tests\test_job_manager.py`
