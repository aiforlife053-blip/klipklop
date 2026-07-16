# Milestone 4 — Pengalaman Web V3

## Tujuan

Mengganti UI lama dengan form generate V3, dashboard semua proses aktif, fallback facecam, serta workflow dua panel Set Waktu dan Hasil.

## Dependensi

- Milestone 1–3 selesai.
- API status persisten, auto-render, final media, edit hook, dan scheduler tersedia.

## Task

1. Ubah form Home menjadi URL, mode, jumlah 1/3/5, kualitas 480p–2160p, dan arahan opsional.
2. Hapus toggle blur dan pengiriman style settings.
3. Preflight orientasi setelah metadata video tersedia; backend tetap memvalidasi ulang.
4. Tampilkan semua proses aktif, bukan hanya job terbaru.
5. Tampilkan progress, tahap, elapsed time, error, cancel, delete, retry, dan aksi `Pilih Facecam` sesuai status.
6. Ubah halaman Preview menjadi dua panel: Set Waktu dan Hasil.
7. Set Waktu memuat `ready_to_schedule`, `scheduled`, dan `uploading` serta preview final portrait.
8. Sediakan judul, deskripsi, hook text, dan waktu WIB.
9. Edit hook hanya teks; perubahan memicu render ulang dan kembali ke Dashboard selama proses.
10. Hapus upload langsung; jadwal wajib minimal 10 menit dari sekarang.
11. Hasil memuat sukses, render/upload gagal, dan dibatalkan sampai dihapus manual.
12. Card sukses ber-border hijau, gagal merah, batal abu-abu.
13. Aksi sukses: Buka YouTube, Download final, Hapus. Aksi gagal: Retry, Hapus.

## File Utama

- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/components/dashboard/ProcessBoard.tsx` baru
- `frontend/src/pages/Preview.tsx`
- `frontend/src/components/clip-workflow/WorkflowPanel.tsx`
- `frontend/src/components/layout/DashboardLayout.tsx`
- `job_manager.py`
- `server.py`
- Test frontend/backend workflow

## Testing Checklist

- [ ] Form hanya mengirim field V3 yang diizinkan.
- [ ] Portrait diblok untuk Gaming/Split.
- [ ] Semua proses aktif tampil dan polling berhenti/melambat saat idle.
- [ ] `needs_facecam` membuka modal fallback.
- [ ] Preview hanya memiliki Set Waktu dan Hasil.
- [ ] Final video dapat diputar dari card Set Waktu.
- [ ] Hook lebih dari 8 kata ditolak.
- [ ] Edit hook memicu render ulang.
- [ ] Upload langsung tidak tersedia.
- [ ] Jadwal kurang dari 10 menit ditolak client dan server.
- [ ] Waktu selalu ditampilkan dalam `Asia/Jakarta`.
- [ ] Warna border dan tombol card sesuai status.
- [ ] UI keyboard/focus/aria tetap dapat digunakan.

## Acceptance Criteria

- User dapat menjalankan seluruh alur tanpa editor style.
- Dashboard menjadi pusat seluruh proses aktif dan fallback.
- Workflow hanya dua panel dan semua upload melalui jadwal WIB.
- State UI tetap benar setelah refresh atau server restart.
