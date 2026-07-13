# KlipKlop V2 Plan

## 1. Tujuan

Ubah KlipKlop dari proses sekali jalan menjadi workflow dua tahap:

1. Sistem mencari highlight, mengunduh potongan, lalu melakukan reframe 9:16 saja.
2. Pengguna mengedit hook, subtitle, watermark, dan credit per klip di halaman Preview.
3. Preview dibuat oleh renderer FFmpeg yang sama dengan final render agar posisi, font, ukuran, wrapping, dan overlay akurat.
4. Setelah final render selesai, pengguna dapat upload sekarang atau menjadwalkan upload public berdasarkan WIB.

## 2. Keputusan Produk

- Reframe selalu 9:16 dengan ukuran/layout tetap.
- Kontrol `Video Scale` dihapus dari editor.
- Pilihan latar blur dipindahkan ke Dashboard sebagai toggle sebelum generate.
- Dashboard tidak menampilkan kartu/video hasil generate.
- Dashboard menampilkan pesan bahwa klip siap diedit dan tombol `Buka Preview`.
- Tombol tersebut mengarahkan pengguna ke halaman Preview.
- Halaman Gallery, route Gallery, dan navigasi Gallery dihapus.
- Semua queue, editing, rendering, scheduling, dan hasil upload dikelola dari Preview.
- Default editor disimpan per akun.
- `Simpan sebagai default` bersifat opsional.
- Tanpa menyimpan sebagai default, perubahan hanya berlaku pada klip aktif.

## 3. Workflow Preview Empat Panel

### Panel 1 — Queue

Menampilkan klip hasil generate yang sudah dipotong dan direframe, tetapi belum memiliki final hook, subtitle, watermark, atau credit.

Setiap item menampilkan:

- Judul klip.
- Durasi.
- Virality score.
- Status `Perlu diedit`.
- Tombol `Edit`.
- Tombol hapus dengan konfirmasi.

Klik `Edit` membuka editor klip pada halaman yang sama.

Jika Queue kosong, tampilkan pesan bahwa belum ada klip yang perlu diedit dan tombol kembali ke Dashboard.

### Editor Klip

Editor menggunakan pengaturan yang saat ini tersedia di Preview, kecuali `Video Scale`:

- Hook aktif/nonaktif.
- Teks hook.
- Font hook.
- Ketebalan font.
- Ukuran hook.
- Warna teks dan outline.
- Ketebalan outline.
- Posisi hook.
- Subtitle aktif/nonaktif.
- Font subtitle.
- Ketebalan font.
- Ukuran subtitle.
- Warna teks, highlight, dan outline.
- Ketebalan outline.
- Posisi subtitle.
- Watermark aktif/nonaktif.
- Gambar watermark.
- Ukuran, opacity, dan posisi watermark.
- Source credit aktif/nonaktif.
- Teks, ukuran, opacity, warna, dan posisi credit.
- Background zoom dan blur strength hanya tersedia bila blur diaktifkan dari Dashboard.

Editor memuat video nyata dari klip aktif, bukan placeholder.

Aksi editor:

- `Render Preview`: membuat preview pendek/rendah resolusi menggunakan pipeline FFmpeg final.
- `Simpan sebagai default`: opsional; menyimpan setting editor per akun ke JSON/config pengguna.
- `Lanjut ke tahap berikutnya`: menyimpan setting khusus klip lalu memasukkan klip ke antrean final render.
- `Batal`: kembali ke Queue tanpa mengubah default akun.

Default akun otomatis menjadi nilai awal untuk klip berikutnya. Pengguna tetap dapat mengubahnya per klip.

### Panel 2 — Proses

Menampilkan antrean final render:

- `Menunggu`.
- `Rendering` dengan progress.
- `Gagal` dengan pesan yang aman dan tombol `Coba Lagi`.

Final render wajib menggunakan setting tersimpan milik klip, bukan setting global yang mungkin berubah setelah antrean dibuat.

Render menggunakan file sementara. `master.mp4` hanya diganti secara atomik setelah output baru lolos validasi. Render gagal tidak boleh merusak hasil valid sebelumnya.

Setelah sukses, klip otomatis pindah ke Panel 3.

### Panel 3 — Set Waktu

Hanya menerima klip final yang render-nya sukses.

Setiap item menyediakan:

- Preview final.
- Judul dan deskripsi YouTube.
- `Upload sekarang`.
- Input tanggal/jam WIB.
- `Jadwalkan upload`.
- `Edit ulang`.
- `Hapus`.

Perilaku jadwal:

- Sistem menyimpan waktu dalam UTC, tetapi seluruh UI membaca dan menulis WIB (`Asia/Jakarta`).
- Scheduler baru mengupload file final saat waktu WIB tiba.
- Upload langsung menggunakan privacy `public`.
- Jika klip diedit ulang sebelum jadwal tiba, jadwal dipertahankan dan akan memakai revisi final terbaru yang sudah selesai.
- Edit ditolak saat upload sedang berjalan.
- Klip yang sudah berhasil diupload tidak ditimpa; edit ulang menghasilkan status siap upload baru.

### Panel 4 — Hasil

Menampilkan riwayat hasil:

- `Berhasil` beserta URL/video ID YouTube dan waktu upload.
- `Gagal` beserta pesan dan tombol `Coba Lagi` atau `Kembali ke Set Waktu`.
- Status file lokal.
- Tombol download final.
- Tombol hapus lokal dengan konfirmasi.

Panel ini menggantikan kebutuhan Gallery.

## 4. Perubahan Dashboard

Dashboard tetap menangani:

- URL YouTube.
- Jumlah klip.
- Resolusi output.
- Arahan AI.
- Toggle blur background.

Dashboard tidak lagi melakukan render hook, subtitle, watermark, dan credit saat tahap generate.

Setelah highlight selesai:

- Area `Hasil Generasi Klip` tidak menampilkan video atau card.
- Tampilkan teks seperti `3 klip siap diedit`.
- Tampilkan tombol utama `Buka Preview`.
- Tombol membuka Preview dan fokus ke Queue terkait generation terakhir.

Generate baru hanya diblokir bila batas antrean/penyimpanan tercapai, bukan karena klip belum disimpan ke Gallery.

## 5. Pipeline Backend Baru

### Tahap A — Generate Draft

1. Validasi URL.
2. Download subtitle YouTube.
3. Jika subtitle tidak tersedia, download audio dan transkrip menggunakan Groq.
4. Gemini memilih highlight.
5. yt-dlp mengunduh source section tiap highlight.
6. Sistem melakukan reframe 9:16 dengan layout tetap dan blur sesuai toggle Dashboard.
7. Simpan source bersih dan transcript bertimestamp untuk rerender.
8. Simpan draft clip dengan status `needs_edit`.
9. Jangan membakar hook, subtitle, watermark, atau credit pada tahap ini.

File minimum per klip:

- `source.mp4`: potongan bersih untuk rerender.
- `draft.mp4`: hasil reframe awal untuk editor.
- `transcript.json`: word/segment timestamp.
- `data.json`: metadata dan state machine.
- `thumbnail.jpg`.

### Tahap B — Preview Render

- Backend menerima clip ID/path dan draft setting.
- Validasi kepemilikan user dan containment path.
- Generate preview menggunakan fungsi render yang sama dengan final.
- Gunakan resolusi lebih rendah atau rentang pendek agar cepat.
- Jangan mengganti final output.
- Kembalikan revision/cache key agar browser mengambil file baru.

### Tahap C — Final Render

- Snapshot setting klip ketika pengguna menekan `Lanjut ke tahap berikutnya`.
- Masukkan job ke render queue.
- Render dari `source.mp4` dan `transcript.json`.
- Gunakan pipeline hook/subtitle/watermark/credit yang sama dengan preview.
- Tulis ke file temporary.
- Validasi hasil.
- Atomically replace `master.mp4`.
- Increment `render_revision`.
- Pindahkan status menjadi `ready_to_schedule`.

## 6. State Machine Klip

Gunakan state eksplisit dalam `data.json`:

```text
needs_edit
preview_rendering
ready_to_render
render_queued
rendering
render_error
ready_to_schedule
scheduled
uploading
uploaded
upload_error
```

Transisi utama:

```text
needs_edit → preview_rendering → needs_edit
needs_edit → render_queued → rendering → ready_to_schedule
rendering → render_error → render_queued
ready_to_schedule → scheduled → uploading → uploaded
ready_to_schedule → uploading → uploaded
uploading → upload_error → ready_to_schedule
scheduled → needs_edit hanya melalui aksi Edit ulang
```

## 7. Struktur Metadata

Contoh `data.json`:

```json
{
  "clip_id": "uuid",
  "status": "needs_edit",
  "title": "Judul klip",
  "description": "Deskripsi",
  "start_time": "00:01:02,000",
  "end_time": "00:01:32,000",
  "duration_seconds": 30,
  "virality_score": 9,
  "source_path": "source.mp4",
  "draft_path": "draft.mp4",
  "final_path": "master.mp4",
  "transcript_path": "transcript.json",
  "render_settings_version": 1,
  "render_revision": 0,
  "render_settings": {},
  "render_error": "",
  "youtube_upload": null
}
```

Jangan simpan API key, OAuth token, cookie, atau secret lain ke metadata klip.

## 8. Default Setting Per Akun

Default disimpan di config JSON milik user yang sudah terisolasi.

Field yang disimpan:

- Hook style.
- Subtitle style.
- Watermark.
- Credit watermark.
- Blur detail yang boleh diedit.

Aturan:

- Default dibaca saat editor membuka klip yang belum memiliki setting khusus.
- Setting klip yang sudah tersimpan selalu lebih prioritas daripada default akun.
- `Simpan sebagai default` menyimpan setting editor saat ini ke config user.
- Tombol ini tidak wajib ditekan sebelum final render.
- `Lanjut ke tahap berikutnya` hanya menyimpan snapshot ke klip aktif.
- Mengubah default tidak mengubah klip lama atau job yang sudah antre.

## 9. Akurasi Preview

Preview DOM/CSS saat ini tidak boleh menjadi acuan final karena berbeda dari Pillow, ASS, dan FFmpeg.

Solusi:

- UI editor boleh menampilkan posisi kasar saat drag.
- Setelah perubahan, pengguna menekan `Render Preview`.
- Backend menghasilkan preview menggunakan renderer final yang sama.
- Preview dan final berbagi fungsi pembentuk filter graph, font resolution, text wrapping, position math, dan overlay generation.
- Tidak ada implementasi styling kedua yang mencoba meniru hasil final secara independen.

Target: hasil preview render dan final render sama secara visual pada resolusi/aspect ratio yang sama.

## 10. Penghapusan Gallery

Hapus:

- Route `/gallery`.
- Lazy import Gallery.
- Navigasi desktop Gallery.
- Navigasi mobile Gallery.
- CTA `Simpan ke Gallery`.
- Komponen/page Gallery setelah tidak ada referensi.

Pertahankan fungsi backend yang masih dibutuhkan Preview atau migrasikan namanya secara bertahap. Jangan langsung menghapus storage/output API bila masih dipakai queue baru.

Akses lama `/gallery` diarahkan ke `/preview` agar bookmark lama tidak menjadi halaman kosong.

## 11. Endpoint Minimum

```text
GET  /api/clips
GET  /api/clips/{clip_id}
POST /api/clips/{clip_id}/preview
POST /api/clips/{clip_id}/render
POST /api/clips/{clip_id}/retry
POST /api/clips/{clip_id}/schedule
POST /api/clips/{clip_id}/schedule/cancel
POST /api/clips/{clip_id}/upload
DELETE /api/clips/{clip_id}
GET  /api/render-status
```

Jika router backend saat ini tidak mendukung path parameter dengan nyaman, gunakan endpoint tetap dengan `clip_id` di payload/query. Jangan gunakan path filesystem dari browser sebagai identitas jangka panjang.

## 12. Keamanan dan Reliabilitas

- Semua clip ID harus dipetakan ulang ke folder dalam output root user.
- Tolak path milik akun lain.
- Validasi seluruh setting di backend.
- Gunakan atomic JSON write untuk state dan metadata.
- Gunakan satu render worker sesuai batas CPU/resolusi yang sudah ada.
- Jangan hapus klip dengan status `rendering`, `scheduled`, atau `uploading`.
- Retention harus melewati klip `scheduled`, `uploading`, dan semua render aktif.
- Scheduler harus memulihkan state `uploading` yang stale setelah restart.
- Scheduler harus mencegah duplicate upload dengan lease/attempt ID.
- Error publik harus aman; detail teknis tetap masuk server log.

## 13. Tahapan Implementasi

### Fase 1 — Data dan Source Retention

- Tambahkan `clip_id` dan state machine.
- Simpan immutable setting snapshot per run/clip.
- Pertahankan `source.mp4` dan `transcript.json`.
- Pisahkan draft reframe dari final render.
- Tambahkan migrasi/fallback untuk output lama.

### Fase 2 — Render API

- Ekstrak fungsi render reusable dari pipeline saat ini.
- Implement preview render.
- Implement queued final render.
- Implement progress, retry, atomic replace, revision.

### Fase 3 — Preview Workflow

- Ubah Preview menjadi empat panel.
- Implement Queue dan editor per klip.
- Gunakan video aktual.
- Implement `Render Preview`, `Simpan sebagai default`, dan `Lanjut ke tahap berikutnya`.
- Implement polling status Proses.

### Fase 4 — Dashboard dan Gallery Removal

- Ganti hasil card Dashboard dengan teks + tombol `Buka Preview`.
- Pertahankan toggle blur di Dashboard.
- Hapus Gallery route/nav/page.
- Redirect `/gallery` ke `/preview`.

### Fase 5 — Upload Workflow

- Pindahkan upload sekarang dan jadwal WIB ke Panel 3.
- Persist semua upload state.
- Implement Panel 4 untuk success/error.
- Lindungi scheduled/uploading clip dari delete/retention.

### Fase 6 — Validasi Akhir

- Test seluruh state transition.
- Test isolation antar user.
- Test render gagal tidak merusak final lama.
- Bandingkan preview render dan final frame menggunakan screenshot/frame extraction.
- Test restart server saat queued/rendering/scheduled/uploading.
- Run lint, TypeScript build, compileall, dan seluruh pytest.

## 14. Acceptance Criteria

- Generate selesai menghasilkan draft tanpa hook/subtitle/watermark/credit terbakar.
- Dashboard menampilkan jumlah klip siap edit dan tombol menuju Preview.
- Preview menampilkan empat panel sesuai workflow.
- Klik Queue membuka editor per klip.
- Video Scale tidak tersedia; reframe fixed 9:16.
- Blur dipilih dari Dashboard.
- `Simpan sebagai default` opsional dan hanya memengaruhi default akun.
- `Lanjut ke tahap berikutnya` merender dengan snapshot setting klip.
- Preview render dan final memakai renderer yang sama.
- Final gagal tidak merusak output valid sebelumnya.
- Klip final dapat upload sekarang atau dijadwalkan WIB sebagai public.
- Gallery tidak terlihat dan `/gallery` redirect ke Preview.
- State tetap benar setelah refresh dan restart server.
- Tidak ada secret dalam JSON output.
