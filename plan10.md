# Plan 10

## Tujuan
- Hook bisa dibacakan suara otomatis memakai Gemini TTS native.
- Subtitle muncul lagi dengan gaya seperti contoh: beberapa kata per chunk, teks putih, kata aktif/box berwarna `#247BA0`.
- Hook text lebih kecil, warna utama `#247BA0`.
- UI hasil klip dirapikan: JSON tidak sticky, status di kanan, judul/info lebih turun dan rata kiri.

## Perubahan Backend
1. Tambah dependency `google-genai` ke `requirements.txt`.
2. Tambah konfigurasi TTS Gemini:
   - model default: `gemini-3.1-flash-tts-preview`
   - voice default: `Kore`
   - API key reuse dari provider Gemini yang sudah tersimpan.
3. Di `clipper_core.py`, aktifkan `tts_client`/helper Gemini TTS saat API key tersedia.
4. Di `clipper_export.py`, ganti jalur hook voice:
   - generate audio `.wav` dari Gemini TTS.
   - pakai prompt pendek, contoh: `Say energetically in Indonesian: ...`
   - fallback ke silent hook jika TTS gagal, supaya export tetap jalan.
5. Cache audio hook per teks bila perlu untuk mengurangi request berulang.

## Perubahan Hook Visual
1. Kecilkan ukuran font hook.
2. Ubah warna teks hook dari kuning ke `#247BA0`.
3. Pertahankan box putih agar tetap terbaca.
4. Pastikan layout hook tetap aman untuk 9:16 dan 16:9.

## Perubahan Subtitle
1. Fix bug chunk terakhir tidak masuk saat word timestamp tersedia.
2. Ubah ASS subtitle style:
   - teks putih bold.
   - box/background `#247BA0` untuk kata/chunk aktif.
   - tampil beberapa kata per event, bukan satu kalimat panjang.
   - posisi bawah seperti contoh TikTok.
3. Pastikan caption burn tetap jalan untuk API Whisper dan local whisper.
4. Jika ASS event 0, log jelas penyebabnya.

## Perubahan UI
1. JSON tidak fixed/sticky kanan bawah.
2. Taruh tombol JSON di area status kanan bawah panel hasil.
3. Info status tetap di kiri, JSON di kanan dalam satu bar.
4. Saat generating:
   - tombol utama berubah `Generating`.
   - tombol samping menjadi `Stop`.
5. Judul dan info session di bawah kartu:
   - lebih turun.
   - rata kiri.
   - tidak center.
6. Header hasil klip:
   - judul `Hasil Klip`.
   - deskripsi singkat di bawahnya.
   - warning di bawah deskripsi dengan jarak lega.

## File Target
- `requirements.txt`
- `clipper_core.py`
- `clipper_export.py`
- `job_manager.py`
- `static/app.js`
- `static/styles.css`
- `index.html`

## Verifikasi
1. `python -m py_compile clipper_core.py clipper_export.py job_manager.py server.py`
2. `node --check static/app.js`
3. Jalankan generate 1 sesi:
   - hook on.
   - subtitle on.
   - pastikan hook bersuara.
   - pastikan subtitle muncul.
   - pastikan clip selesai muncul incremental.
4. Cek UI:
   - JSON tidak sticky.
   - status kiri, JSON kanan.
   - Stop muncul saat generating.
   - judul/info rata kiri dan lebih turun.

## Risiko
- Gemini TTS preview bisa berubah kuota/format response.
- Voice Indonesia belum selalu natural; prompt perlu diuji.
- Jika TTS gagal, fallback silent tetap dipakai agar export tidak gagal total.
