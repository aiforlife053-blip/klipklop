# Plan: Strategi Cookies & Anti-Bot untuk yt-dlp di VPS (Clipper Web)

Konteks: aplikasi clipper web jalan di VPS, yt-dlp sering kena error
`Sign in to confirm you're not a bot` karena IP datacenter + cookies statis
yang cepat basi.

---

## 1. Tujuan

- Minimalkan frekuensi block/bot-check dari YouTube.
- Bikin proses refresh cookies gak manual tiap hari.
- Punya fallback kalau cookies tetap invalid (PO Token).

---

## 2. Strategi Cookies

### 2.1 Akun khusus scraping
- [ ] Buat akun Google terpisah, khusus dipakai yt-dlp (jangan akun pribadi utama).
- [ ] Login akun ini di 1 browser saja (jangan multi-device) supaya sesi gak sering di-invalidate Google.
- [ ] Jangan logout/clear cookies browser tsb.

### 2.2 Export & sinkronisasi cookies ke VPS
- [ ] Install extension "Get cookies.txt LOCALLY" di browser akun scraping.
- [ ] Export `cookies.txt` dari browser (di laptop/PC, bukan di VPS — VPS gak ada GUI browser).
- [ ] Upload ke VPS ke path tetap, misal: `/opt/clipper/cookies.txt`
- [ ] Command yt-dlp pakai:
  ```bash
  yt-dlp --cookies /opt/clipper/cookies.txt <url>
  ```

### 2.3 Jadwal refresh manual (sementara)
- [ ] Re-export cookies tiap **3–7 hari** (sebelum kadaluarsa duluan).
- [ ] Cara upload cepat ke VPS:
  ```bash
  scp cookies.txt user@vps-ip:/opt/clipper/cookies.txt
  ```
- [ ] (Opsional) bikin reminder kalender biar gak lupa.

### 2.4 Auto-refresh cookies (opsi lanjutan)
- [ ] Riset pakai `--cookies-from-browser` di headless browser terjadwal (mis. Playwright login script) yang re-export cookies.txt otomatis tiap N jam, lalu push ke VPS.
- [ ] Alternatif: cron job di VPS yang re-login pakai Playwright/Puppeteer headless (butuh handle captcha risk — evaluasi dulu sebelum implementasi).

---

## 3. Strategi PO Token (Proof-of-Origin Token)

### 3.1 Setup provider (bgutil-ytdlp-pot-provider)
- [ ] Jalankan HTTP server via Docker di VPS:
  ```bash
  docker run --name bgutil-provider -d --init -p 4416:4416 brainicism/bgutil-ytdlp-pot-provider
  ```
- [ ] Install plugin Python:
  ```bash
  pip install -U bgutil-ytdlp-pot-provider
  ```
- [ ] Verifikasi plugin aktif:
  ```bash
  yt-dlp -v <url> 2>&1 | grep "PO Token"
  ```
  Harus muncul: `bgutil:http-x.x.x (external)`

### 3.2 Maintenance
- [ ] Pastikan container `bgutil-provider` auto-restart kalau VPS reboot:
  ```bash
  docker update --restart unless-stopped bgutil-provider
  ```
- [ ] Cek log container secara berkala kalau token generation mulai gagal:
  ```bash
  docker logs bgutil-provider --tail 50
  ```

---

## 4. Kombinasi Cookies + PO Token

Jalankan bareng untuk hasil paling stabil:
```bash
yt-dlp --cookies /opt/clipper/cookies.txt <url>
```
(PO Token otomatis aktif di background selama plugin & container jalan — gak perlu flag tambahan kalau pakai port default 4416)

---

## 5. Kalau Masih Sering Kena Block

- [ ] Cek apakah IP VPS udah flagged permanen → test dari IP lain (VPS baru / IP berbeda).
- [ ] Pertimbangkan proxy residential khusus untuk request ke YouTube.
- [ ] Batasi rate request (jangan spam banyak clip dalam waktu singkat dari IP yang sama).
- [ ] Update yt-dlp rutin (`pip install -U yt-dlp`) — YouTube sering ubah mekanisme deteksi.

---

## 6. Monitoring & Alerting (opsional, untuk clipper production)

- [ ] Tambah error handling di backend: kalau yt-dlp gagal karena bot-check, kirim notifikasi (Telegram/Discord webhook) biar tahu cookies perlu di-refresh.
- [ ] Log setiap error yt-dlp dengan timestamp buat lihat pola (misal ternyata basi tiap X hari — bisa dipakai buat set jadwal refresh yang lebih akurat).

---

## Referensi
- https://github.com/yt-dlp/yt-dlp/wiki/FAQ
- https://github.com/Brainicism/bgutil-ytdlp-pot-provider
