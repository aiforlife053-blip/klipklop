# Milestone 5 — Cleanup dan Hardening

## Tujuan

Menghapus jalur lama setelah V3 stabil, mengurangi bottleneck, membersihkan dependency/dead code, dan menguatkan security boundary.

## Dependensi

- Milestone 1–4 lulus test.
- Replacement V3 sudah menutup semua fungsi editor, preview, render, dan workflow lama.

## Task

1. Hapus Clip Editor, Live Preview editor, accurate-preview endpoint, default style saving, dan edit-again lama setelah caller nol.
2. Hapus renderer blur/black-contain lama bila tidak dipakai mode V3.
3. Sembunyikan UI watermark; pertahankan kompatibilitas data minimal bila masih diperlukan.
4. Audit import, route, type, CSS, function, test fixture, file, dan package yang tidak terpakai.
5. Hapus dependency hanya setelah build/test penuh tetap lulus.
6. Cache metadata probe, transcript, TTS, face detection, speaker crop, dan asset overlay berdasarkan identity/version.
7. Hindari download, decode, dan re-encode berulang.
8. Gunakan satu final FFmpeg pass bila stabil dan tulis output secara atomik.
9. Batasi concurrency FFmpeg dan pastikan cancel membersihkan child process/temp file.
10. Validasi ownership clip, ROI, seek time, hook, metadata upload, jadwal, dan media path di backend.
11. Cegah path traversal, cross-user access, secret leak, serta shell/filter injection.

## File Utama

- Komponen `frontend/src/components/clip-editor/*` untuk dihapus
- `frontend/src/lib/clip-settings.ts`
- `clipper_portrait.py`
- `clipper_export.py`
- `clipper_download.py`
- `clipper_core.py`
- `render_scheduler.py`
- `job_manager.py`
- `server.py`
- `requirements.txt`
- `frontend/package.json` dan lockfile
- `tests/test_backend_security.py`

## Testing Checklist

- [ ] Pencarian caller editor/blur/preview lama menghasilkan nol referensi runtime.
- [ ] Frontend build tidak memiliki unresolved import.
- [ ] Python compile/import smoke lulus.
- [ ] `pip check` lulus.
- [ ] Retry memakai cache valid dan lebih cepat dari proses awal.
- [ ] Satu clip tidak dapat membaca/mengubah clip user lain.
- [ ] ROI non-finite/out-of-frame/rasio salah ditolak.
- [ ] Hook dan metadata tidak dapat menyisipkan command/filter.
- [ ] Media endpoint menolak path traversal.
- [ ] Cancel tidak meninggalkan FFmpeg/yt-dlp/temp besar.
- [ ] Render concurrency tidak membuat worker berlebihan.
- [ ] Dependency yang tersisa semuanya punya caller/tooling nyata.

## Acceptance Criteria

- Jalur V3 menjadi satu-satunya runtime flow.
- Tidak ada dead code/package besar yang terbukti tidak terpakai.
- Performa retry dan render membaik tanpa mengurangi kualitas.
- Semua trust boundary memiliki validasi dan test security.
