# KlipKlop Web Lokal

Web lokal untuk KlipKlop. Folder ini dibuat self-contained agar nanti bisa dipindah menjadi repo sendiri.

## Run

```powershell
pip install -r requirements.txt
py -3.12 server.py
```

Buka `http://127.0.0.1:8765` jika browser tidak terbuka otomatis.

## Settings

- Highlight finder: Gemini API (`https://generativelanguage.googleapis.com/v1beta/openai`, `gemini-2.5-flash`).
- Caption maker: Groq Audio Transcriptions API (`https://api.groq.com/openai/v1`, `whisper-large-v3-turbo`).
- Dibutuhkan API key Gemini dan API key Groq (dikelola terpisah).
- Konfigurasi dan kredensial disimpan dalam plaintext di `config.json` lokal. Membutuhkan koneksi internet.
- Buat/isi `cookie.txt` di folder ini, atau paste lewat modal Pengaturan.
- Output mengikuti folder output di konfigurasi.

## Catatan

Ini local-only. Hosting publik butuh desain terpisah untuk auth, queue, worker FFmpeg, storage, rate limit, dan secret vault.

## VPS Deploy Checklist

Deployment minimal harus menyertakan file dan folder source, tetapi harus mengecualikan artifact lokal dan rahasia pengguna.

**Include:**
- Python source files (`*.py`)
- Frontend source (`frontend/`) dan `package.json`/`package-lock.json` (jika build dilakukan di VPS) atau `frontend/dist/` (jika prebuilt static)
- `requirements.txt`
- `README.md` dan `PRODUCT.md`
- Folder `fonts/`

**Exclude:**
- `config.json`
- `cookie.txt` dan `cookies.txt`
- Folder output video: `output/`
- Folder sementara: `_temp/` dan `cache/`
- Folder system dan tool lokal: `bin/`, `ffmpeg/`, `__pycache__/`, `.pytest_cache/`, `node_modules/`
- File logs dan tracker statik runtime: `error.log`, `tickets.json`, `static/watermarks/`
