# KlipKlop V3

Pipeline klip YouTube otomatis: tiga mode layout tetap, hook + subtitle Indonesia, render final otomatis, dashboard proses persisten, dan workflow dua panel **Set Waktu** / **Hasil**.

## Produk

- Output final mengikuti kualitas tanpa upscale paksa: `480 → 540x960`, `720 → 720x1280`, `1080 → 1080x1920`.
- Mode per URL: `vertical_full`, `gaming`, `split_middle`.
- Vertical Full: landscape + portrait; active-speaker crop menahan subjek terakhir saat deteksi ambigu.
- Gaming / Split Middle: landscape only (portrait diblok sebelum generate). Split Middle memakai ROI orang, bukan belah frame buta.
- Form generate: URL, mode, jumlah klip `1/3/5`, kualitas `480p/720p/1080p`, arahan AI opsional.
- Target klip 50–70 detik (min 40). Pemilihan AI memprioritaskan momen lucu, lalu fallback viral/konflik/insight.
- Hook menampilkan semua teks TTS, maksimal 3 baris dengan wrap + shrink.
- Subtitle Poppins 700 uppercase 3–4 kata, ~75 px pada 1080, putih + kata aktif `#FFFF00`, outline hitam. Vertical Full di `y=0.78`; Split Middle di `y=0.5`.
- Credit `sc: @channel` Poppins 700, ~34 px pada 1080, opacity 60%, kanan atas. Blur/editor style/watermark dihapus.
- Upload hanya via jadwal WIB, minimal 10 menit dari sekarang. Upload langsung ditolak.
- Satu klip gagal tidak menghentikan sibling. Tidak ada retry otomatis.
- Status/riwayat disimpan sampai dihapus manual.

### State

`queued → analyzing → downloading → detecting_layout → rendering → ready_to_schedule → scheduled → uploading → uploaded`

Cabang: `needs_facecam`, `render_error`, `upload_error`, `cancelled`.

## Stack

- Backend: Python 3.11 stdlib `ThreadingHTTPServer` (`server.py`), job worker (`job_manager.py`), FFmpeg/OpenCV/Pillow.
- Frontend: React 19 + Vite + Tailwind (`frontend/`).
- Proxy deploy: Caddy (`deploy/Caddyfile`) → API `:8765`, SPA `frontend/dist`.

## Setup lokal

### Backend

```bash
cd /path/to/klipklop
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# butuh ffmpeg di PATH
python server.py
```

Default bind: `127.0.0.1:8765`.

### Frontend

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173, proxy /api → :8765
npm run build    # dist/ untuk Caddy
```

### Environment

| Var | Default | Fungsi |
|---|---|---|
| `KLIPKLOP_HOST` | `127.0.0.1` | Bind host |
| `KLIPKLOP_PORT` | `8765` | Bind port |
| `SECURITY_MODE` | `local` | Set `public` untuk bind non-localhost |
| `KLIPKLOP_SECRET` | — | Wajib ≥32 byte jika `SECURITY_MODE=public` |
| `KLIPKLOP_LOCAL_PASSWORD` | local default | Password login mode local; ganti di production |

Jangan commit `config.json`, cookie, token OAuth, vault key, media output, atau `.venv/`.

## Workflow UI

1. **Dashboard** — generate + ProcessBoard (status aktif, facecam, retry, cancel, hapus).
2. **Preview (Set Waktu & Hasil)** — jadwal WIB, edit hook → rerender, download final, hasil sukses/gagal.
3. **Settings** — provider AI/TTS, cookie YouTube, OAuth channel (kunci disimpan server-side; response tidak mengembalikan secret).
4. **Console** — log job.

## Verifikasi rilis

```bash
# backend
source .venv/bin/activate
python -m compileall -q .
python -m pytest -q

# frontend
cd frontend
npm test
npm run lint
npm run build
```

Milestone plan: `klipklopv3/plan.md` (M1–M6; **M6 validasi rilis = terakhir**).

### Smoke layout (dev)

Fixture referensi visual: `contoh_video.mp4` (portrait podcast). Smoke mode 1080×1920 + audio + benchmark RTF dijalankan di `/tmp` saat validasi M6; output smoke **tidak** di-commit.

### Catatan rilis M6

- Full pytest + FE build/lint/test harus hijau.
- Media/API hanya via `clip_id` + artifact; raw `path=` ditolak.
- Cancel render set event + hapus temp `master.*.tmp.mp4`.
- Upload YouTube publik butuh OAuth channel terhubung; uji otomatis memakai mock upload (tidak publish ke akun nyata).
