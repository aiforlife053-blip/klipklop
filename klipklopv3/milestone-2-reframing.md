# Milestone 2 — Mesin Reframing Cerdas

## Tujuan

Membuat Vertical Full mengikuti pembicara aktif dan Game Mode memiliki deteksi facecam otomatis dengan pemilihan manual sebagai fallback.

## Dependensi

- Milestone 1 selesai.
- Geometry layout dan status `detecting_layout`/`needs_facecam` sudah tersedia.
- OpenCV, NumPy, FFmpeg, source clip, dan metadata durasi tersedia.

## Task

1. Buat modul active-speaker tracking untuk Vertical Full.
2. Gabungkan deteksi wajah, gerak mulut, dan energi audio untuk memilih pembicara.
3. Gunakan kebijakan konservatif: pindah hanya saat confidence cukup.
4. Tahan pembicara minimum 1,5 detik; bila ambigu tahan posisi terakhir.
5. Haluskan perpindahan crop sekitar 300 ms.
6. Jika tracking hilang, tahan crop terakhir; jika belum ada wajah, gunakan crop tengah.
7. Pertahankan detector facecam Gaming dan simpan confidence/ROI.
8. Jika confidence rendah, ubah status menjadi `needs_facecam` dan simpan setelah restart.
9. Buat modal fallback berisi video/frame source asli, timeline, crop box drag/resize dengan rasio terkunci, serta preview 1:3 + 2:3.
10. Validasi ROI dan overlap gameplay di backend sebelum melanjutkan render.

## File Utama

- `speaker_tracking.py` baru
- `clipper_portrait.py`
- `gaming_layout.py`
- `job_manager.py`
- `server.py`
- `frontend/src/components/facecam/FacecamPickerModal.tsx` baru
- `frontend/src/pages/Dashboard.tsx`
- Test backend/frontend terkait tracking dan ROI

## Testing Checklist

- [ ] Speaker dominan dipilih berdasarkan audio dan gerak mulut.
- [ ] Pergantian tidak lebih cepat dari hold 1,5 detik.
- [ ] Perpindahan crop halus sekitar 300 ms.
- [ ] Dua speaker ambigu mempertahankan speaker sebelumnya.
- [ ] Tracking hilang memakai posisi terakhir/crop tengah.
- [ ] Facecam confidence rendah menghasilkan `needs_facecam`.
- [ ] Job `needs_facecam` tetap ada setelah server restart.
- [ ] Timeline menampilkan frame source asli.
- [ ] ROI dapat digeser/resize, tetap dalam frame, dan rasio terkunci.
- [ ] ROI overlap gameplay tidak bisa disimpan.
- [ ] User lain tidak dapat membuka frame atau mengubah ROI clip.

## Acceptance Criteria

- Vertical Full mengikuti orang yang berbicara tanpa gerakan crop liar.
- Game Mode otomatis berjalan bila confidence cukup.
- Fallback manual dapat diselesaikan dari Dashboard dan dilanjutkan setelah browser/server dibuka ulang.
- Tidak ada path filesystem yang diterima dari client.
