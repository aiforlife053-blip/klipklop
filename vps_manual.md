Checklist Setup VPS - Urutan Lengkap
Saya petakan semua yang perlu disiapkan sebelum upload. Konfirmasi dulu mana yang sudah/belum punya:
A. Persiapan Lokal (sebelum VPS)
1. Supabase Project Baru
- Buat project baru di https://supabase.com/dashboard
- Catat Project Reference (dari URL project)
- Catat Project API URL dari Settings → API
- Catat anon public key
- Catat service_role key (secret, jangan share)
- Disable public signup: Authentication → Providers → Email → "Enable email signup" OFF
- Buat 5 user manual via Authentication → Users → "Add user" (pakai email/password)
2. Google OAuth Credentials
- Buka https://console.cloud.google.com
- Buat/pilih project
- Enable YouTube Data API v3
- Buat OAuth 2.0 credentials (Application type: Web application)
- Authorized redirect URIs: tambahkan https://DOMAIN_ANDA/api/youtube/callback
- Catat Client ID dan Client Secret
3. Generate Encryption Keys
# KLIPKLOP_SECRET (minimal 32 bytes random)
python -c "import secrets; print(secrets.token_urlsafe(32))"

# TOKEN_ENCRYPTION_KEY (Fernet key)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
4. Rotasi Kredensial Lama
- Gemini API: generate key baru di https://aistudio.google.com/apikey
- Groq API: generate key baru di https://console.groq.com/keys
- Revoke semua key lama yang ter-commit
5. Build Frontend
cd frontend
npm run build
# Hasil ada di frontend/dist/
B. Setup VPS
6. VPS Requirements
- OS: Ubuntu 22.04+ / Debian 12+
- Python 3.11+
- Domain sudah pointing ke IP VPS (A record)
- Port 80, 443, 22 terbuka
7. Install Dependencies
# Update system
sudo apt update && sudo apt upgrade -y

# Install essentials
sudo apt install -y python3.12 python3.12-venv python3-pip git curl

# Install Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy

# Install FFmpeg
sudo apt install -y ffmpeg
8. Upload & Setup Application
# Buat user khusus
sudo useradd -m -s /bin/bash klipklop

# Upload codebase (dari lokal)
rsync -avz --exclude='node_modules' --exclude='output' --exclude='__pycache__' \
  /path/to/web-klip/ user@VPS_IP:/tmp/klipklop-upload

# Di VPS, pindah ke direktori final
sudo mv /tmp/klipklop-upload /opt/klipklop
sudo chown -R klipklop:klipklop /opt/klipklop

# Setup Python venv
sudo -u klipklop python3.12 -m venv /opt/klipklop/venv
sudo -u klipklop /opt/klipklop/venv/bin/pip install -r /opt/klipklop/requirements.txt
9. Setup Environment
# Buat file env (edit dengan nilai real)
sudo nano /opt/klipklop/.env

# Isi dengan nilai dari langkah 1-3:
APP_DOMAIN=domain.anda.com
KLIPKLOP_HOST=127.0.0.1
KLIPKLOP_PORT=8765
SECURITY_MODE=public
ALLOWED_ORIGINS=https://domain.anda.com
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
KLIPKLOP_SECRET=hasil_generate_step3
TOKEN_ENCRYPTION_KEY=hasil_generate_step3
YOUTUBE_CLIENT_ID=xxx.apps.googleusercontent.com
YOUTUBE_CLIENT_SECRET=GOCSPX-xxx
YOUTUBE_REDIRECT_URI=https://domain.anda.com/api/youtube/callback

# Protect file
sudo chmod 600 /opt/klipklop/.env
sudo chown klipklop:klipklop /opt/klipklop/.env
10. Apply Supabase Migration
# Install Supabase CLI
curl -sL https://github.com/supabase/cli/releases/latest/download/supabase_linux_amd64.tar.gz | tar xz
sudo mv supabase /usr/local/bin/

# Link project
cd /opt/klipklop
supabase login
supabase link --project-ref PROJECT_REF

# Apply migration
supabase db push
11. Setup Systemd Service
# Copy service file
sudo cp /opt/klipklop/deploy/klipklop.service /etc/systemd/system/

# Edit jika perlu (path venv, user, dll)
sudo nano /etc/systemd/system/klipklop.service

# Enable & start
sudo systemctl daemon-reload
sudo systemctl enable klipklop
sudo systemctl start klipklop
sudo systemctl status klipklop
12. Setup Caddy
# Copy Caddyfile
sudo cp /opt/klipklop/deploy/Caddyfile /etc/caddy/Caddyfile

# Ganti {$APP_DOMAIN} dengan domain real atau edit:
sudo nano /etc/caddy/Caddyfile
# Ubah baris 1: {$APP_DOMAIN} → domain.anda.com

# Reload Caddy
sudo systemctl reload caddy
C. Verifikasi
13. Health Checks
# Check app logs
sudo journalctl -u klipklop -f

# Check Caddy
sudo systemctl status caddy

# Test HTTPS
curl https://domain.anda.com/api/status
14. Functional Tests (via browser)
- Login dengan salah satu dari 5 user
- Upload cookie YouTube
- Connect YouTube OAuth (callback harus sukses)
- Start job → cek queue position
- Save output → cek isolation (user lain tidak bisa akses)
- Settings → save provider key → cek Vault (tidak muncul di response)
- Logout → login user berbeda → pastikan file/job terpisah
