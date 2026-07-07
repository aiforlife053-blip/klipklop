# Security Plan

## Status awal

Aplikasi ini saat ini **local-first**, belum aman untuk public hosting. `PRODUCT_SPEC.md` juga sudah menyatakan public hosting out of scope sampai auth, secret vault, storage, worker isolation, queueing, rate limit siap.

Temuan cepat:
- `server.py` bind ke `127.0.0.1`, bagus untuk lokal, tetapi tidak cukup jika di-host publik.
- Tidak ada authentication/authorization di endpoint `/api/*`.
- Endpoint berbahaya jika publik: `/api/settings`, `/api/cookies`, `/api/start`, `/api/delete`, `/api/save`, `/api/download`, `/api/outputs`, `/api/status`.
- `config.json`, `cookie.txt`, `cookies.txt`, `output/` sudah masuk `.gitignore`.
- `config.json` lokal berisi API key nyata. Walau tidak tracked git, key harus dianggap bocor jika pernah dishare/backup/screenshot/log. Rotasi key.
- API menerima URL user lalu `yt-dlp`/FFmpeg memprosesnya: ini SSRF/resource-exhaustion risk bila publik.
- File download/delete memakai path dari client. Ada validasi output root, tetapi masih perlu hardened untuk symlink, path equality, dan metadata leak.
- Logs/status bisa membocorkan URL, path lokal, error provider, judul video, output folder.
- Cookie YouTube disimpan plaintext.

## Keputusan keamanan utama

Jangan host app ini langsung seperti sekarang.

Target aman minimum:
1. Tetap private via VPN/Tailscale, atau
2. Jika public internet wajib: tambah auth kuat, CSRF, rate limit, secret vault, job isolation, storage boundary, reverse proxy, monitoring.

## Threat model

### Aset dilindungi
- API keys AI provider.
- YouTube cookies/session.
- Video output dan metadata.
- Local filesystem/server host.
- Job queue/CPU/GPU/disk quota.
- Browser session user.

### Penyerang
- Internet random scanner.
- Bot DoS resource-heavy jobs.
- CSRF attacker dari website lain.
- User tidak sah yang menebak URL public.
- Input malicious lewat YouTube URL/title/subtitle/metadata.
- Dependency/supply-chain compromise (`yt-dlp`, FFmpeg, Python deps, browser assets).

## Attack surface

### HTTP API
- No auth: semua endpoint bisa dipakai siapa pun jika publik.
- No CSRF: browser user bisa dipaksa POST dari situs lain jika app publik pakai cookie auth nanti.
- No rate limit: `/api/start` bisa spam job berat.
- No body size limit: `/api/cookies` atau `/api/settings` bisa kirim payload besar.
- No CORS/CSP/security headers.
- No request timeout.

### File system
- Download/delete/save menerima path absolut dari client.
- Output allowlist masih memasukkan `.txt`, `.json`, `.vtt`; metadata bisa sensitif.
- `output_dir` bisa diubah dari UI ke lokasi sensitif.
- Symlink inside output bisa jadi escape jika tidak dicek `is_relative_to` + symlink policy.

### Secrets
- `config.json` plaintext.
- `cookie.txt`/`cookies.txt` plaintext.
- API key lama ada di file lokal; rotasi.
- Settings API sudah write-only untuk key, bagus, tapi file tetap raw.

### Processing
- URL validation hanya `http/https` + netloc; belum restrict domain YouTube.
- SSRF risk jika publik dan downloader bisa fetch URL arbitrary.
- FFmpeg/yt-dlp memproses media untrusted.
- Job thread daemon tanpa per-job process sandbox.
- No disk/time/CPU quota.

### Frontend
- Banyak UI update pakai `textContent`, bagus.
- Ada `innerHTML` untuk template SVG + escaped message; tetap wajib audit semua dynamic HTML.
- No CSP, no frame-ancestors, no nosniff.

## Plan prioritas

### P0 - Sebelum hosting apa pun

1. Rotate semua API key yang pernah tersimpan di `config.json`.
2. Jangan expose port app langsung ke internet.
3. Jalankan hanya di `127.0.0.1` atau di private network.
4. Backup `config.json`, `cookie.txt`, `cookies.txt` terenkripsi saja.
5. Tambah preflight startup check: jika host bukan `127.0.0.1` dan auth belum aktif, server harus refuse start.
6. Tambah `SECURITY_MODE=local|private|public`; default `local`.

### P1 - Auth & session

1. Tambah login wajib untuk semua `/api/*` dan static dashboard jika public/private remote.
2. Gunakan session cookie:
   - `HttpOnly`
   - `Secure`
   - `SameSite=Lax` atau `Strict`
   - short idle timeout
3. Password hash pakai stdlib tidak cukup; gunakan Argon2/bcrypt jika dependency sudah ada, kalau belum pakai external auth/reverse proxy lebih sederhana.
4. Untuk paling cepat dan aman: pakai Tailscale atau Supabase Auth internal.
5. Jika auth internal dibuat: tambah logout, session rotation, brute-force lockout.

### P2 - CSRF & headers

1. Tambah CSRF token untuk semua POST jika cookie auth dipakai.
2. Tambah headers:
   - `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`
   - `X-Content-Type-Options: nosniff`
   - `Referrer-Policy: no-referrer`
   - `Permissions-Policy: camera=(), microphone=(), geolocation=()`
   - `Cache-Control: no-store` untuk `/api/settings`, `/api/status`, secret-sensitive responses.
3. Disable directory/content sniffing behavior.

### P3 - API hardening

1. Body size limit:
   - settings: max 64 KB
   - cookies: max 512 KB
   - start/delete/save: max 16 KB
2. Method allowlist; reject unknown methods.
3. Per-IP/per-session rate limit:
   - `/api/start`: 1 active + cooldown
   - `/api/settings`: low frequency
   - `/api/cookies`: very low frequency
4. Return generic errors ke client; detail hanya local log yang sudah redacted.
5. Redact patterns:
   - API keys
   - cookies
   - Authorization headers
   - local paths
   - signed URLs/tokens
6. Add audit log tanpa secret.

### P4 - URL/download safety

1. Restrict input URL ke YouTube domains only:
   - `youtube.com`
   - `www.youtube.com`
   - `m.youtube.com`
   - `youtu.be`
2. Reject private/local IP redirects jika downloader mendukung hook; minimal reject non-YouTube URL sebelum processing.
3. Limit video duration/file size where possible via `yt-dlp` options.
4. Disable playlist by default.
5. Use fixed output root not arbitrary UI path in public mode.
6. Normalize file checks with resolved path:
   - target must be inside output root
   - reject symlink files/dirs unless explicitly allowed
   - reject target equal output root for delete
7. Remove public download of `.txt`/`.json` unless needed; if needed, only generated safe metadata, never raw logs/config/cookies.
8. Use server-generated file IDs instead of accepting raw absolute paths from client.

### P5 - Job isolation & DoS control

1. Run each processing job in separate process, not app thread.
2. Enforce timeout per job.
3. Enforce disk quota per run and global output retention.
4. Enforce max concurrent jobs = 1 for personal use.
5. Add queue length limit = 1 or small fixed number.
6. Kill child process tree on timeout/cancel.
7. Store temp files under one controlled temp dir and clean on startup.
8. Use lower OS privileges for worker account.
9. If Linux hosting: systemd sandbox/Docker with read-only app dir, writable only output/temp/config.

### P6 - Secret storage

1. Do not store secrets in repo or image.
2. In public/private hosted mode, move keys/cookies to environment variables or encrypted secret store.
3. If file storage remains:
   - `0600` permissions on Linux
   - Windows ACL restrict current user only
   - never serve app root static files except explicit allowlist
4. Split config:
   - non-secret config JSON
   - secret file/env separate
5. Add secret scanner check before commit.

### P7 - Static serving

1. Replace current generic static serving from project root with allowlist:
   - `/` -> `index.html`
   - `/static/app.js`
   - `/static/*.css` if exists
   - required assets only
2. Never serve `.py`, `.json`, `.md`, `.txt`, logs, config, cookies.
3. Add cache rules: no-store for dashboard if sensitive; immutable only for hashed assets.

### P8 - Dependency/supply-chain

1. Pin Python dependencies in lock/requirements.
2. Keep `yt-dlp` and FFmpeg updated from trusted source.
3. Run dependency audit regularly.
4. Verify downloaded binaries path and permissions.
5. Do not auto-download executable binaries at runtime in public mode.

### P9 - Monitoring & recovery

1. Health endpoint that exposes no secrets.
2. Alert on repeated failed login, rate limit hits, job failures, disk usage.
3. Daily encrypted backup of config minus transient output unless needed.
4. Restore drill: verify backup can restore keys/settings.
5. Incident runbook:
   - stop server
   - revoke API keys
   - revoke YouTube cookies/session
   - preserve logs
   - rotate host credentials
   - redeploy clean

## Minimal implementation order

1. Rotate current keys.
2. Add startup guard: no public bind without `SECURITY_MODE=public` and auth configured.
3. Static allowlist; stop serving project root.
4. Add auth via reverse proxy first, not custom code.
5. Add request body limits + rate limit.
6. Restrict URL to YouTube domains.
7. Replace raw paths in API with generated file IDs.
8. Add security headers + CSRF if cookie auth.
9. Move secrets out of `config.json`.
10. Worker process isolation + timeout/quota.

## Acceptance criteria before public hosting

- Unauthenticated user cannot access dashboard or any `/api/*`.
- CSRF attempt from external origin cannot trigger `/api/start`, `/api/settings`, `/api/cookies`, `/api/delete`.
- `/api/download` cannot read files outside output, including symlink escape.
- `/api/delete` cannot delete outside output or output root itself.
- App refuses startup on `0.0.0.0` without explicit public security config.
- Secrets never appear in API responses, logs, browser storage, source map, screenshots, or git.
- 100 repeated `/api/start` requests do not create more than allowed jobs.
- Huge request body is rejected early.
- Non-YouTube URL is rejected.
- Disk full/FFmpeg hang does not bring down web server.
- Restore process documented and tested.

## Hosting recommendation

Best personal setup:

1. Keep app bound to `127.0.0.1`.
2. Access remotely using Tailscale/ZeroTier/WireGuard.
3. If browser access via domain needed, require Supabase Auth and still bind app privately when possible.
4. Do not public-port-forward this app.

## Files to audit next

- `server.py`
- `job_manager.py`
- `config/config_manager.py`
- `clipper_download.py`
- `clipper_core.py`
- `utils/helpers.py`
- static dashboard files
- deployment/start scripts
