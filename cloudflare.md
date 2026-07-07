# Cloudflare Tunnel + Access Setup

Dokumen ini menjelaskan cara memproteksi KlipKlop Web agar hanya bisa diakses oleh pemilik akun, menggunakan **Cloudflare Tunnel** (tanpa port publik) dan **Cloudflare Access** (Zero Trust).

## Prasyarat

- Domain yang sudah di Cloudflare (atau subdomain yang di-delegate ke Cloudflare).
- Akun Cloudflare (free plan sudah cukup untuk Access).
- Aplikasi KlipKlop berjalan di mesin lokal (misalnya `127.0.0.1:8765`).

## Langkah 1 — Install cloudflared

Download binary `cloudflared` dari https://github.com/cloudflare/cloudflared/releases atau gunakan package manager:

```powershell
winget install Cloudflare.cloudflared
```

Verifikasi:

```powershell
cloudflared --version
```

## Langkah 2 — Login ke Cloudflare

```powershell
cloudflared tunnel login
```

Browser akan terbuka. Pilih domain yang akan dipakai (misalnya `klipklop.example.com`). File sertifikat akan tersimpan di `~/.cloudflared/cert.pem`.

## Langkah 3 — Buat Tunnel

```powershell
cloudflared tunnel create klipklop
```

Catat **Tunnel ID** yang muncul (contoh: `a1b2c3d4-...`). File credentials akan tersimpan di `~/.cloudflared/<TUNNEL_ID>.json`.

## Langkah 4 — Konfigurasi Tunnel

Buat file `~/.cloudflared/config.yml`:

```yaml
tunnel: <TUNNEL_ID>
credentials-file: C:\Users\<USER>\.cloudflared\<TUNNEL_ID>.json

ingress:
  - hostname: klipklop.example.com
    service: http://127.0.0.1:8765
    originRequest:
      noTLSVerify: true
  - service: http_status:404
```

Ganti `<TUNNEL_ID>` dan `<USER>` sesuai sistem.

## Langkah 5 — DNS Route

```powershell
cloudflared tunnel route dns klipklop klipklop.example.com
```

Ini membuat record CNAME `klipklop.example.com` yang mengarah ke tunnel.

## Langkah 6 — Jalankan Tunnel

```powershell
cloudflared tunnel run klipklop
```

Untuk menjalankan sebagai service Windows:

```powershell
cloudflared service install
net start cloudflared
```

## Langkah 7 — Proteksi dengan Cloudflare Access

1. Buka **Cloudflare Zero Trust Dashboard** → https://one.dash.cloudflare.com
2. Masuk ke menu **Access → Applications**.
3. Klik **Add an application** → pilih **Self-hosted**.
4. Isi konfigurasi:
   - **Application name**: `KlipKlop`
   - **Application domain**: `klipklop.example.com`
   - **Session duration**: sesuai kebutuhan (misalnya 24 hours)
5. Pada tab **Policies**, buat policy:
   - **Policy name**: `Owner Only`
   - **Action**: Allow
   - **Include rule**: Emails → masukkan email pribadi (misalnya `kamu@gmail.com`)
6. Simpan.

Sekarang, siapa pun yang mengakses `https://klipklop.example.com` akan diarahkan ke halaman login Cloudflare Access dan hanya email yang terdaftar yang bisa masuk.

## Langkah 8 — Verifikasi

1. Buka browser incognito → `https://klipklop.example.com`
2. Harus muncul halaman login Cloudflare Access.
3. Login dengan email yang didaftarkan → aplikasi terbuka.
4. Coba email lain → ditolak.

## Catatan Keamanan

- Aplikasi tetap bind ke `127.0.0.1` — tidak ada port yang terbuka ke internet.
- Semua traffic dienkripsi lewat Cloudflare Tunnel.
- Access policy berlaku untuk seluruh domain, termasuk semua path `/api/*`.
- Untuk menambah lapisan, aktifkan **WAF** dan **Bot Fight Mode** di dashboard Cloudflare.
- Rotasi API key AI provider secara berkala (lihat `securityplan.md` P0).

## Troubleshooting

- **403 Forbidden setelah login**: pastikan email di Access policy sama persis dengan email yang dipakai login.
- **Tunnel tidak connect**: cek `cloudflared tunnel info klipklop` dan pastikan credentials file ada.
- **DNS belum resolve**: tunggu propagasi atau flush DNS lokal.

## Incident Runbook

Jika terjadi insiden keamanan (misalnya API key bocor, akses tidak sah, atau serangan):

### Langkah 1 — Stop Server
```powershell
# Jika dijalankan manual
Ctrl+C di terminal server

# Jika dijalankan sebagai service
net stop KlipKlop
```

### Langkah 2 — Revoke API Keys
1. Buka provider AI (Gemini, OpenAI, dll)
2. Revoke semua API key yang pernah tersimpan di `config.json`
3. Generate API key baru
4. Update `config.json` dengan key baru

### Langkah 3 — Revoke YouTube Session
```powershell
# Hapus token YouTube
del token_youtube.json

# Revoke di Google Cloud Console
# Buka: https://myaccount.google.com/permissions
# Cari "KlipKlop" atau nama app Anda
# Klik "Remove Access"
```

### Langkah 4 — Preserve Logs
```powershell
# Backup log aktivitas
copy activity.log activity.log.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')

# Backup error log jika ada
copy error.log error.log.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')
```

### Langkah 5 — Rotate Host Credentials
Jika server di-host di mesin remote:
```powershell
# Ganti password user
net user <username> *

# Atau rotate SSH key jika pakai SSH
# Generate key baru dan update authorized_keys
```

### Langkah 6 — Redeploy Clean
```powershell
# Backup config lama
copy config.json config.json.compromised-$(Get-Date -Format 'yyyyMMdd-HHmmss')

# Reset ke config default (opsional)
# Atau edit manual untuk hapus data sensitif

# Restart server
py -3.12 server.py
```

### Langkah 7 — Audit
1. Cek Cloudflare Access logs: siapa yang login, dari mana
2. Cek activity log di aplikasi
3. Identifikasi apakah ada data yang bocor
4. Update security plan jika perlu

## Backup & Restore

### Backup Secrets
```powershell
# Backup encrypted (gunakan password manager atau encryption tool)
# Contoh dengan 7-Zip:
7z a -p<password> secrets-backup-$(Get-Date -Format 'yyyyMMdd').7z config.json cookie.txt cookies.txt token_youtube.json
```

### Restore dari Backup
```powershell
# Extract backup
7z x secrets-backup-YYYYMMDD.7z

# Verify file permissions (Windows)
icacls config.json /grant:r %USERNAME%:F
icacls cookie.txt /grant:r %USERNAME%:F
icacls cookies.txt /grant:r %USERNAME%:F
icacls token_youtube.json /grant:r %USERNAME%:F

# Restart server
py -3.12 server.py
```

### Daily Backup Script (Opsional)
Buat `backup-daily.ps1`:
```powershell
$backupDir = "C:\Backups\KlipKlop"
$date = Get-Date -Format 'yyyyMMdd'
$backupFile = "$backupDir\secrets-$date.7z"

# Create backup directory
New-Item -ItemType Directory -Force -Path $backupDir

# Backup secrets (ganti <password> dengan password Anda)
7z a -p<password> $backupFile config.json cookie.txt cookies.txt token_youtube.json

# Cleanup old backups (keep last 30 days)
Get-ChildItem $backupDir -Filter "secrets-*.7z" | 
    Where-Object { $_.CreationTime -lt (Get-Date).AddDays(-30) } | 
    Remove-Item

Write-Host "Backup completed: $backupFile"
```

Jalankan dengan Task Scheduler setiap hari.

## Referensi

- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- [Cloudflare Access Documentation](https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/)
- [Zero Trust Quickstart](https://developers.cloudflare.com/cloudflare-one/get-started/)
- [Security Plan](./securityplan.md) - Detail threat model dan acceptance criteria
