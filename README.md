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

## VPS Deploy

Buat artifact dari root repository dengan PowerShell 5.1+:

```powershell
.\deploy\package.ps1 -OutputPath "$env:TEMP\klipklop-deploy.zip"
```

Script menjalankan `npm ci` dan `npm run build`, lalu membuat ZIP dengan timestamp entry tetap dan `DEPLOY-MANIFEST.txt` berisi SHA-256 setiap file. Gunakan `-SkipBuild` hanya jika `frontend/dist/index.html` sudah dibangun dari source saat ini. Audit isi tanpa membuat ZIP:

```powershell
.\deploy\package.ps1 -SkipBuild -ListOnly
```

Artifact menyertakan source aplikasi, `frontend/dist`, dependencies manifests, fonts, migration, serta konfigurasi deployment. Artifact mengecualikan `.git`, `.venv`, `venv`, `node_modules`, `data`, output video, cache, temporary files, build outputs non-deploy, logs, database lokal, archive, environment files, credentials, cookies, token, dan private key. `deploy/klipklop.env.example` tetap disertakan karena hanya template.

Jangan ekstrak ZIP langsung ke `/opt/klipklop` dan jangan jalankan sinkronisasi `--delete` tanpa protected filters. Prosedur staging, validasi manifest, selective copy, preservation `/opt/klipklop/data` dan `/opt/klipklop/.venv`, ownership, restart, rollback, log, API, serta SPA checks ada di `vps_manual.md`.
