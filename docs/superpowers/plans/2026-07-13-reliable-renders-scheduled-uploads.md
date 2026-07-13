# Reliable Renders and Scheduled YouTube Uploads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix broken download streaming, speed up 1440p/2160p rendering, and schedule direct-public YouTube uploads using WIB.

**Architecture:** Persist each clip's YouTube state in its adjacent `data.json`. A process-local scheduler scans user output folders every minute; due uploads are submitted with `privacyStatus: public`. Schedule timestamps are parsed as `Asia/Jakarta` then stored as UTC ISO timestamps.

**Tech Stack:** Python 3.11 stdlib `zoneinfo`, YouTube Data API, React, TypeScript.

## Global Constraints

- No new dependency.
- Schedule is exact WIB input, stored UTC.
- Scheduled videos upload as `public` only at due time.
- One upload worker per process prevents duplicate submission.

---

### Task 1: Backend scheduling persistence

**Files:** `job_manager.py`, `server.py`, `tests/test_job_manager.py`

- [ ] Add validated schedule/cancel methods with output containment checks.
- [ ] Persist `youtube_upload` object in `data.json`: `status`, `scheduled_at`, `title`, `description`, `privacy`, `video_id`, `url`, `error`.
- [ ] Start a one-minute scheduler and atomically mark due clips `uploading`; upload public video; persist `uploaded` or `error`.
- [ ] Test WIB conversion, invalid/past timestamps, cancel, output listing, success/failure persistence.

### Task 2: Render and download reliability

**Files:** `server.py`, `clipper_ffmpeg.py`, `tests/test_job_manager.py`

- [ ] Stream downloads in 64 KiB writes, handling disconnected clients.
- [ ] Use `libx264 -preset ultrafast -crf 28` only for CPU 1440p/2160p; preserve all existing lower-resolution behavior.
- [ ] Log selected high-resolution worker cap and encoder.
- [ ] Test the encoder selection for 720p and 1440p.

### Task 3: Detail-card scheduling controls

**Files:** `frontend/src/pages/Gallery.tsx`, `frontend/src/pages/Dashboard.tsx`

- [ ] Add `datetime-local` control labeled WIB plus schedule/cancel actions.
- [ ] Refresh output state after scheduling; show scheduled, uploading, uploaded, error states.
- [ ] Keep immediate upload behavior unchanged.
- [ ] Run `npm run lint`, `npm run build`, `pytest tests/test_job_manager.py -q`, and `python -m compileall .`.
