# Plan Sosmed Auto Upload

## Tujuan

Menambahkan sistem upload otomatis untuk klip yang sudah selesai dibuat, dimulai dari YouTube lalu TikTok.

## Scope Awal

- Platform awal: YouTube.
- Platform berikutnya: TikTok.
- Upload berjalan dari queue lokal.
- Cron/worker memproses queue secara berkala.
- Token OAuth disimpan lokal, tidak hardcode.

## Arsitektur

```text
Clip selesai dibuat
  -> masuk upload_queue
  -> user pilih platform + metadata + jadwal
  -> worker/cron cek queue
  -> upload ke platform
  -> update status
```

## Data Queue

Gunakan file lokal dulu: `upload_queue.json`.

Contoh item:

```json
{
  "id": "20260707-clip-001-youtube",
  "platform": "youtube",
  "file_path": "output/.../master.mp4",
  "title": "Judul clip",
  "description": "Deskripsi clip",
  "privacy": "private",
  "schedule_at": "2026-07-07T20:00:00+07:00",
  "status": "pending",
  "attempts": 0,
  "last_error": "",
  "remote_id": ""
}
```

Status:

- `pending`
- `uploading`
- `uploaded`
- `failed`
- `cancelled`

## YouTube Upload

### OAuth

1. Buat Google Cloud project.
2. Enable YouTube Data API v3.
3. Buat OAuth Client type Desktop App.
4. Download `client_secret.json`.
5. App buka browser login Google sekali.
6. Simpan refresh token lokal.

Scope minimal:

```text
https://www.googleapis.com/auth/youtube.upload
```

### Upload API

Pakai `google-api-python-client`:

- `youtube.videos().insert(...)`
- `MediaFileUpload(file_path, resumable=True)`

Metadata:

- `snippet.title`
- `snippet.description`
- `snippet.categoryId` default `22`
- `status.privacyStatus`: `private`, `unlisted`, `public`

## TikTok Upload

TikTok butuh:

1. TikTok Developer app.
2. OAuth login.
3. Content Posting API.
4. App review / approval untuk production.

Scope kemungkinan:

- video upload/posting permission dari TikTok Developer.

TikTok dibuat setelah YouTube stabil karena approval lebih ribet.

## UI Plan

### Page Sosmed

- Card YouTube
  - Connect YouTube
  - Status connected / not connected
  - Channel name
  - Disconnect

- Card TikTok
  - Connect TikTok
  - Status connected / not connected
  - Username
  - Disconnect

### Card Clip

Tambah menu/tombol:

- `Upload`
- `Jadwalkan`

Modal upload:

- Platform: YouTube / TikTok
- Title
- Description
- Privacy
- Schedule time
- Submit to queue

### Page Queue

Tabel/list:

- Clip
- Platform
- Schedule
- Status
- Attempts
- Actions: retry / cancel / open uploaded link

## Worker / Cron

File: `upload_worker.py`

Flow:

```text
load queue
filter pending where schedule_at <= now
mark uploading
upload
if success -> uploaded + remote_id
if fail -> failed + last_error + attempts++
save queue
```

Run manual:

```powershell
python upload_worker.py
```

Windows Task Scheduler:

- Trigger: every 5 minutes
- Action: `python D:\Vibe Code\web-klip\upload_worker.py`
- Start in: `D:\Vibe Code\web-klip`

## Backend API Plan

Endpoints:

```text
GET  /api/social/status
POST /api/social/youtube/connect
POST /api/social/youtube/disconnect
GET  /api/upload-queue
POST /api/upload-queue/add
POST /api/upload-queue/retry
POST /api/upload-queue/cancel
```

## File Plan

New files:

- `social_auth.py`
- `youtube_uploader.py`
- `upload_queue.py`
- `upload_worker.py`

Existing files:

- `server.py` add API routes
- `job_manager.py` expose queue/social helpers
- `static/app.js` add Sosmed UI actions
- `index.html` add upload queue UI
- `.gitignore` ignore token files

Ignore:

```text
client_secret*.json
token*.json
upload_queue.json
```

## Security Notes

- Jangan commit `client_secret.json`.
- Jangan log access token / refresh token.
- Token local-only.
- Default privacy upload: `private`.
- Retry pakai backoff, jangan spam API.

## Milestone

### M1 — YouTube Auth

- Add OAuth flow.
- Save token lokal.
- Show connected channel in Sosmed page.

### M2 — Manual YouTube Upload

- Upload one selected clip manually.
- Metadata editable.
- Default privacy private.

### M3 — Queue + Worker

- Add queue file.
- Add worker.
- Add retry/cancel.

### M4 — Cron Setup

- Add docs / helper command for Windows Task Scheduler.
- Test scheduled upload.

### M5 — TikTok

- Add OAuth.
- Add upload endpoint.
- Add TikTok queue support.

## Recommended First Build

Build M1 + M2 first:

1. YouTube OAuth connect.
2. Manual upload one clip.
3. Verify upload reaches YouTube as private.

Cron comes after upload is proven stable.
