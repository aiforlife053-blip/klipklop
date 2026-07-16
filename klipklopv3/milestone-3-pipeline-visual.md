# Milestone 3 — Visual dan Pipeline Otomatis

## Tujuan

Mengunci style video, menghasilkan hook/subtitle sesuai referensi, memilih highlight 40–70 detik, dan langsung merender final tanpa editor style.

## Dependensi

- Milestone 1–2 selesai.
- Layout final dan metadata tracking/ROI tersedia.
- Provider AI, TTS, transcript, Pillow, font lokal, dan FFmpeg berfungsi.

## Task

1. Buat preset visual server-side tetap untuk output 1080x1920.
2. Gunakan font lokal paling dekat dengan contoh, mulai dari `Poppins-Bold.ttf`.
3. Buat hook Indonesia maksimal 8 kata dan 2 baris; ringkas ulang lalu fallback potong kata utuh.
4. Pertahankan voice TTS saat ini.
5. Saat intro: bekukan frame dan audio asli, putar TTS, jeda 300 ms, geser hook ke kiri 300 ms, lalu mulai video/audio asli.
6. Buat subtitle Indonesia uppercase, kelompok 3–5 kata, putih, active yellow, outline hitam tipis, tanpa shadow, posisi tengah.
7. Pertahankan hanya tanda baca `?`, `!`, dan koma.
8. Tampilkan `sc: @channel` kecil di kanan atas.
9. Nonaktifkan blur dan watermark dari renderer.
10. Ubah AI highlight: target 50–70 detik; perluas konteks; izinkan minimum 40 detik.
11. Hapus tahap `needs_edit`; render final otomatis dan atomik.
12. Pisahkan error per klip agar satu kegagalan tidak menghentikan batch.
13. Retry manual memakai cache source/transcript/tracking/TTS yang masih valid.

## File Utama

- `config/editor_defaults.py`
- `config/config_manager.py`
- `clipper_ai.py`
- `subtitle_cues.py`
- `clipper_export.py`
- `clipper_core.py`
- `job_manager.py`
- `render_scheduler.py`
- `tests/test_job_manager.py`

## Testing Checklist

- [ ] Hook selalu Indonesia, maksimal 8 kata/2 baris.
- [ ] Audio asli tidak berjalan saat TTS.
- [ ] Pause dan slide masing-masing 300 ms.
- [ ] Video, audio, subtitle, dan credit tetap sinkron setelah intro.
- [ ] Subtitle 3–5 kata, uppercase, warna/outline/posisi benar.
- [ ] Watermark dan blur tidak muncul.
- [ ] Credit tepat `sc: @channel` di kanan atas.
- [ ] Durasi target 50–70 detik; hasil tidak di bawah 40 detik.
- [ ] Batch tetap melanjutkan klip lain saat satu render gagal.
- [ ] Render sukses menghasilkan `master.mp4` dan status `ready_to_schedule`.
- [ ] Render gagal menghasilkan `render_error` tanpa retry otomatis.

## Acceptance Criteria

- Output visual konsisten dan tidak dapat diubah lewat payload client.
- Hook/subtitle mendekati `contoh_video.mp4` pada aspek yang disepakati.
- Pipeline selesai otomatis dari analisis sampai final.
- Retry tidak mengulang pekerjaan mahal bila cache masih valid.
