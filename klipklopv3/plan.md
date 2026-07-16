# KlipKlop V3 Plan

## Tujuan

Merombak KlipKlop menjadi pipeline video otomatis dengan tiga mode layout tetap, hook dan subtitle baku, fallback facecam manual, render final otomatis, dashboard proses persisten, serta workflow dua panel: Set Waktu dan Hasil.

## Aturan Produk

- Output final selalu `1080x1920`.
- Mode dipilih manual sekali per URL: `vertical_full`, `gaming`, atau `split_middle`.
- Vertical Full menerima landscape dan portrait.
- Gaming dan Split Middle hanya menerima landscape; source portrait diblok sebelum generate.
- Form generate berisi URL, mode, jumlah klip `1/3/5`, kualitas `480p–2160p`, dan arahan AI opsional.
- AI menargetkan klip 50–70 detik; konteks diperpanjang bila perlu; minimum 40 detik.
- Hook dan subtitle selalu Bahasa Indonesia.
- Hook maksimal 8 kata dan 2 baris.
- Subtitle uppercase, 3–5 kata, putih, kata aktif kuning, outline hitam tipis, tanpa shadow, posisi tengah.
- Source credit `sc: @channel` di kanan atas.
- Blur dan editor style dihapus. Watermark tidak dipakai; menu disembunyikan.
- Render final otomatis setelah analisis.
- Semua upload wajib dijadwalkan dalam WIB, minimal 10 menit dari sekarang.
- Kegagalan satu klip tidak menghentikan klip lain.
- Tidak ada retry otomatis; retry dilakukan user.
- Status dan riwayat disimpan sampai dihapus manual.

## Milestone

1. [Fondasi dan Kontrak Layout](milestone-1-fondasi-layout.md)
2. [Mesin Reframing Cerdas](milestone-2-reframing.md)
3. [Visual dan Pipeline Otomatis](milestone-3-pipeline-visual.md)
4. [Pengalaman Web V3](milestone-4-web-v3.md)
5. [Cleanup dan Hardening](milestone-5-hardening.md)
6. [Validasi Rilis](milestone-6-validasi-rilis.md)

## State Utama

`queued -> analyzing -> downloading -> detecting_layout -> rendering -> ready_to_schedule -> scheduled -> uploading -> uploaded`

Cabang khusus:

- `detecting_layout -> needs_facecam -> rendering`
- `rendering -> render_error -> rendering`
- `uploading -> upload_error -> scheduled`
- Proses aktif dapat menjadi `cancelled`.

## Urutan Kerja

Milestone wajib dikerjakan berurutan. Milestone berikutnya dimulai setelah acceptance criteria milestone sebelumnya lulus. Cleanup kode lama baru dilakukan setelah replacement V3 pada Milestone 1–4 stabil.

## Batas Implementasi

- Pertahankan React/Vite, Python server, OpenCV, Pillow, dan FFmpeg yang sudah dipakai.
- Jangan menambah dependency crop UI; gunakan video, canvas, dan pointer events native.
- Lindungi perubahan lokal yang sudah ada; jangan reset atau overwrite pekerjaan lain.
- Jangan menghapus dependency/file sebelum audit caller dan full test.
- Jangan commit kecuali diminta pengguna.
