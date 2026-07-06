# KlipKlop Feature Plan

## 1. Delete Confirmation Modal

Problem: Hapus langsung tanpa warning, data hilang permanen.

Fix:
- Buat modal konfirmasi reusable di HTML
- Setiap aksi hapus (clip di Home, session di Riwayat) wajib buka modal dulu
- Modal isi: pesan warning + tombol Batal + tombol Ya, Hapus
- Setelah confirm baru call /api/delete

Files: index.html, static/app.js

Status: pending

---

## 2. Blur Background Toggle

Behavior:
- Source landscape + Blur ON:
  - layer background = video sama, diperbesar, di-crop 9:16, blur
  - layer foreground = video landscape asli, fit width, center
  - output = portrait 9:16, blur bergerak mengikuti video
- Source landscape + Blur OFF:
  - crop tengah biasa
- Source portrait:
  - abaikan toggle, render normal

UI di main form:
```
Background Landscape
Toggle: [OFF | Blur Bergerak]
Deskripsi: Isi area kosong dengan blur dari video yang sama
```

Default: OFF

Config:
```json
"landscape_blur": false
```

FFmpeg command blur mode:
```
ffmpeg -i input.mp4
  -filter_complex
    "[0:v]scale=W:H,crop=w:h:x:y,boxblur=30:3[bg];
     [0:v]scale=width:-2[fg];
     [bg][fg]overlay=(W-w)/2:(H-h)/2"
  -c:v libx264 -preset veryfast -crf 23
  output.mp4
```

Resolusi ikut video_quality:
- 480p  → W=540  H=960
- 720p  → W=720  H=1280
- 1080p → W=1080 H=1920

Deteksi landscape:
```python
landscape = orig_w > orig_h
```

Files: clipper_portrait.py, clipper_core.py, job_manager.py, config/config_manager.py, index.html, static/app.js

Status: pending

---

## 3. Remove Bottom Stepper

Problem: Bagian Paste Link → AI Bekerja → Download makan ruang, tidak fungsional.

Fix: Hapus section itu dari HTML. Ganti dengan info compact di bawah progress bar:
```
Status: Downloading source video
Clip: 1 dari 3 | Quality: 720p | Mode: Blur
```

Files: index.html, static/app.js

Status: pending

---

## 4. UI Revamp - Home (Beranda)

Panel kiri - form input:
- Link YouTube
- Jumlah Klip: 1 / 3 / 5 (selector tombol)
- Kualitas Video: 480p / 720p / 1080p
- Background Landscape: toggle blur
- Bahasa Subtitle: dropdown
- Tombol Proses Klip
- Progress bar + status text + Log button

Panel kanan - hasil:
- Belum ada hasil: placeholder informatif
  ```
  Belum ada hasil klip.
  Paste link YouTube di sebelah kiri dan mulai proses.

  Tips:
  - Video 5-60 menit paling optimal
  - Subtitle harus tersedia (Indonesia atau Inggris)
  - Gunakan Blur untuk video landscape
  ```
- Ada hasil: grid clip cards

Files: index.html, static/app.js

Status: pending

---

## 5. UI Revamp - Hasil Klip per Session

Per clip card:
```
[ video preview playable ]
[ checkbox ] Pilih klip 1
Judul klip (dari AI)
Deskripsi singkat
Durasi: 62s

[ Download ]  [ Simpan ]  [ Hapus ]
```

Per session header:
```
Judul video YouTube
3 klip tersedia | 720p | Blur Background | 6 Jul 2026 14:32
[ Simpan yang dipilih ]  [ Hapus Session ]
```

Files: static/app.js

Status: pending

---

## 6. UI Revamp - Riwayat

Per session card:
```
Judul video YouTube
2 klip tersimpan | 720p | 6 Jul 2026
[ Hapus Session ] → dengan warning modal
```

Expand session: tampil clip-clip tersimpan
Per clip:
- video preview playable
- judul klip
- durasi
- [ Download ]

Files: static/app.js

Status: pending

---

## 7. Clip Duration ~60s

Target: 60s, valid 45–75s
Already implemented in clipper_ai.py.

Status: done

---

## 8. Save Selected

Already implemented:
- Simpan yang dipilih (renamed)
- save kirim checked clips
- 0 checked → error
- saved clips hilang dari Home
- save union tidak overwrite

Status: done

---

## 9. Download Source Once

Already implemented:
- download_video_only() method
- local FFmpeg cuts per clip

Status: done

---

## 10. Quality Setting

Already implemented:
- 480 / 720 / 1080
- output resolution tied to quality
- config saved

Status: done

---

## File Change Summary

| File | Changes |
|---|---|
| index.html | Remove stepper, add blur toggle, add confirm modal, UI cleanup |
| static/app.js | Delete confirmation, blur toggle save, UI renders improved |
| clipper_portrait.py | Add convert_to_portrait_blur_with_progress() method |
| clipper_core.py | Pass landscape_blur setting, detect landscape |
| job_manager.py | Read/save landscape_blur config, pass to core |
| config/config_manager.py | Add "landscape_blur": false default |

---

## Test Checklist

1. Generate 1 clip, 720p, blur ON, source landscape → output portrait blur background bergerak
2. Generate 1 clip, 720p, blur OFF → output portrait crop tengah
3. Delete clip di Home → modal muncul → confirm → clip hilang
4. Delete session di Riwayat → modal muncul → confirm → session hilang
5. Checklist 2 clip → Simpan yang dipilih → 2 clip masuk Riwayat
6. Preview playable di Home dan Riwayat
7. Quality 480 → output 540x960, quality 1080 → 1080x1920
8. Checks: py_compile, node --check, 23 test funcs pass
