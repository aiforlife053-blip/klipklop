# KlipKlop Web Lokal

Web lokal untuk KlipKlop. Folder ini dibuat self-contained agar nanti bisa dipindah menjadi repo sendiri.

## Run

```powershell
pip install -r requirements.txt
py -3.12 server.py
```

Buka `http://127.0.0.1:8765` jika browser tidak terbuka otomatis.

## Settings

- Default Base URL Gemini-compatible: `https://generativelanguage.googleapis.com/v1beta/openai`
- Default model: `gemini-2.5-flash`
- API key disimpan di `config.json` lokal.
- Buat/isi `cookie.txt` di folder ini, atau paste lewat modal Pengaturan.
- Output mengikuti folder output di konfigurasi.

## Catatan

Ini local-only. Hosting publik butuh desain terpisah untuk auth, queue, worker FFmpeg, storage, rate limit, dan secret vault.
