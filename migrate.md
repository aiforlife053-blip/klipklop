# Rencana Integrasi Frontend & Backend (KlipKlop Web)

Dokumen ini berisi panduan dan rencana komprehensif untuk menyambungkan antarmuka Frontend (React/Vite) dengan Backend (Python `server.py` & `job_manager.py`), dengan syarat utama: **UI Frontend yang sudah ada tidak boleh berubah (harus dipertahankan 100%)**.

## 1. Arsitektur & Pola Integrasi
Saat ini Frontend sudah memiliki utilitas `api.ts` yang berfungsi untuk melakukan *fetch* data ke Backend. Semua pemanggilan akan memanfaatkan fungsi `api(path, options)` yang sudah menangani token/session (berdasarkan cookie yang diset oleh `/api/login`).

Backend berjalan di `http://127.0.0.1:8765`, dan Frontend dikonfigurasi melalui proxy di Vite (`vite.config.ts`) agar request `/api` diteruskan ke Backend.

## 2. Pemetaan Endpoint (Endpoint Mapping)

### A. Dashboard (Beranda)
**Fitur:** Mengirim URL untuk diproses, melihat status/log proses, dan melihat hasil sementara.
- **Start Job:** 
  - **FE Action:** Klik tombol "Proses Klip"
  - **BE Endpoint:** `POST /api/start`
  - **Payload:** `{ url, instruction, landscape_blur, source_credit }` (sesuai JSON Payload Modal)
- **Polling Status & Logs:**
  - **FE Action:** *Interval polling* setiap 1-2 detik saat proses berjalan.
  - **BE Endpoint:** `GET /api/status`
  - **Response:** `{ status, message, progress, error, logs }`
  - *Tugas:* Mengganti state `dummyLogs` dengan `logs` dari BE, dan menganimasikan *progress bar* berdasarkan nilai `progress`.
- **Hasil Generate (Staged Outputs):**
  - **FE Action:** Setelah status "complete", *fetch* hasil terbaru.
  - **BE Endpoint:** `GET /api/outputs`
  - *Tugas:* Mengganti state `dummyClips` dengan data dari BE. (Lihat bagian **Catatan Data Kosong/Missing**).
- **Simpan ke Gallery:**
  - **FE Action:** Klik tombol "Simpan ke Gallery"
  - **BE Endpoint:** `POST /api/save`
  - **Payload:** `{ path: "...", clips: ["..."] }`
- **Hapus / Batal:**
  - **FE Action:** Klik tombol "Hapus"
  - **BE Endpoint:** `POST /api/delete`

### B. Gallery (Galeri)
**Fitur:** Menampilkan klip-klip yang sudah di-save sebelumnya, menghapus, atau mengunggahnya.
- **Daftar Klip Tersimpan:**
  - **FE Action:** *Mounting* halaman Gallery
  - **BE Endpoint:** `GET /api/outputs`
  - *Tugas:* Melakukan filter pada `groups` yang memiliki `status == "saved"`, kemudian merendernya di *grid* gallery.
- **Upload ke YouTube:**
  - **FE Action:** Klik "Upload" pada modal Detail
  - **BE Endpoint:** `POST /api/social/youtube/upload`
  - **Payload:** `{ path, title, description, privacy }`

### C. Settings (Pengaturan)
**Fitur:** Konfigurasi engine AI, kualitas video, subtitle, dll.
- **Ambil Pengaturan:**
  - **FE Action:** *Mounting* halaman Settings
  - **BE Endpoint:** `GET /api/settings`
- **Simpan Pengaturan:**
  - **FE Action:** Klik tombol Simpan
  - **BE Endpoint:** `POST /api/settings`

### D. Console
**Fitur:** Menampilkan log real-time dari sistem.
- **Ambil Log:**
  - **BE Endpoint:** `GET /api/status` (mengambil array `logs`).

---

## 3. Catatan Data Kosong (Missing Data) & Perbedaan Skema
Dalam proses penyatuan ini, saya menemukan beberapa perbedaan skema data (data yang dibutuhkan oleh *UI Frontend* tetapi **belum/tidak** disediakan oleh *Backend*, atau sebaliknya). Data ini harus dimodifikasi/dijembatani agar UI tidak rusak.

### 1. Viral Score (`score`) di Kartu Video
- **Di UI Frontend:** Kartu video memiliki lencana skor viral (misal: 🔥 99%).
- **Di Backend:** Saat ini belum ada skor viral di `data.json`.
- **Solusi/Plan Terpilih:** Merombak sedikit alur AI di Backend (`clipper_core.py` atau sejenisnya) agar LLM/AI mengevaluasi dan mereturn nilai skor kepotensian viral (0-100) saat memilih momen. Skor ini kemudian disimpan ke `data.json` agar bisa dibaca oleh Frontend.

### 2. URL Gambar Thumbnail (`img`) per Klip
- **Di UI Frontend:** Setiap kartu membutuhkan URL gambar (`<img src={clip.img} />`).
- **Di Backend:** API hanya mengembalikan path `.mp4`.
- **Solusi/Plan Terpilih:** Memodifikasi Backend agar, setelah klip dibuat, AI/sistem akan mengambil cuplikan (screenshot/thumbnail) khusus dari **momen terbaik/paling menarik** di dalam klip tersebut dan menyimpannya sebagai file gambar statis (misal `.jpg`). Path gambar ini akan dikembalikan oleh endpoint `/api/outputs` sehingga Frontend bisa merendernya dengan mudah menggunakan tag `<img>`.

### 3. Format Durasi Video (`duration`)
- **Di UI Frontend:** Ditulis dalam format string simpel seperti `"45s"` atau `"60s"`.
- **Di Backend:** Mereturn float `duration_seconds` (contoh: `45.123`).
- **Solusi/Plan Terpilih:** Frontend akan ditugaskan memparsing nilai float ini menjadi integer dengan melakukan pembulatan (`Math.round()`), lalu menambah akhiran huruf `"s"` saat proses pe-render-an UI (Contoh: `Math.round(45.123) + "s"`).

### 4. Optimasi Format, Ukuran Storage & Kecepatan Proses
- **Masalah:** Menyimpan video sering memakan *storage* yang besar dan proses pemotongan (FFmpeg) bisa memakan waktu jika tidak dioptimalkan.
- **Solusi/Plan Terpilih:**
  1. **Mengurangi Ukuran File (CRF):** Solusi terbaiknya, kita akan menyetel parameter `CRF` (Constant Rate Factor) FFmpeg di angka `28` hingga `30`. Ini akan mengurangi ukuran file MP4 secara drastis (hingga 40-50%) dengan kualitas visual yang nyaris tidak terlihat penurunannya di layar HP.
  2. **Mempercepat Proses (Preset):** Backend akan di-set untuk menggunakan *preset* kompresi FFmpeg `-preset veryfast`, yang akan sangat mempercepat waktu tunggu pembuatan klip (menghindari antrean lama).

---

## 4. Langkah Pengerjaan Selanjutnya (Execution Plan)

1. **Modifikasi Backend (AI Score & Thumbnail)**:
   - Memperbarui prompt/logika di `clipper_core.py` (dan file terkait) agar AI menilai potensi viral klip dan menaruh skornya di output JSON.
   - Menambahkan proses ekstrak *frame* gambar (menggunakan ffmpeg) di Backend untuk momen terbaik, lalu mendaftarkannya pada API response.
2. **Integrasi Dashboard**:
   - Mengubah fungsi tombol "Proses Klip" untuk mengirim `POST /api/start`.
   - Mengaktifkan interval *polling* ke `GET /api/status` untuk menggerakkan progress bar & log (menggantikan timeout palsu).
   - Mengambil hasil klip dari `GET /api/outputs` dan mengubah formatnya agar sesuai dengan UI kartu, termasuk parsing durasi float ke detik (`s`).
3. **Integrasi Gallery**:
   - Menghubungkan fungsi *fetch* untuk me-render klip-klip yang sudah tersimpan (`saved`).
   - Menghubungkan fungsi Upload YouTube.
4. **Integrasi Settings & Console**:
   - Memastikan form pengaturan tersinkronisasi dua arah dengan `GET /api/settings` dan `POST /api/settings`.
