# Milestone 1 — Fondasi dan Kontrak Layout

## Tujuan

Mengunci kontrak V3, state machine, tiga mode layout, geometry output, dan validasi orientasi sebelum mengubah pipeline utama.

## Dependensi

- Tidak bergantung milestone lain.
- Memakai FFmpeg/ffprobe dan test backend/frontend yang sudah ada.
- Perubahan gaming lokal yang belum committed harus dipertahankan.

## Task

1. Catat baseline test dan working tree sebelum perubahan.
2. Tetapkan mode canonical: `vertical_full`, `gaming`, `split_middle`.
3. Tetapkan payload generate minimal: URL, mode, jumlah, kualitas, arahan opsional.
4. Tambahkan state machine persisten sesuai `plan.md` dan validasi transisi legal.
5. Buat router layout terpusat untuk memilih filtergraph berdasarkan mode.
6. Implementasikan geometry Split Middle: source kiri menjadi panel atas, source kanan menjadi panel bawah.
7. Tetapkan Game Mode: facecam 1/3 atas dan gameplay crop tengah 2/3 bawah.
8. Validasi orientasi: Gaming/Split menolak portrait; Vertical Full menerima landscape/portrait.
9. Bila facecam Game Mode masuk area gameplay tengah, tolak mode agar wajah tidak tampil ganda.

## File Utama

- `layout_modes.py` baru
- `gaming_layout.py`
- `job_manager.py`
- `server.py`
- `tests/test_layout_modes.py` baru
- `tests/test_gaming_layout.py`
- `tests/test_job_manager.py`

## Testing Checklist

- [ ] Ketiga nama mode diterima; nilai lain ditolak.
- [ ] Output geometry selalu 1080x1920.
- [ ] Split Middle menghasilkan kiri di atas dan kanan di bawah.
- [ ] Game Mode menghasilkan tinggi 640/1280.
- [ ] Portrait ditolak untuk Gaming/Split dengan pesan yang menyarankan Vertical Full.
- [ ] Facecam yang overlap gameplay tengah menghasilkan error jelas.
- [ ] Transisi state ilegal ditolak.
- [ ] Baseline regression dicatat.

## Acceptance Criteria

- Kontrak mode, payload, status, dan geometry tunggal dipakai backend dan frontend.
- Tidak ada blur pada mode mana pun.
- Test layout dan state machine lulus.
- Belum ada penghapusan jalur lama yang masih dipakai.
