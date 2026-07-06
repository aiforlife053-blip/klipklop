# KlipKlop Web — Product Specification

## 1. Product Overview

KlipKlop Web is a local-only web application that converts long-form YouTube videos into short-form viral clips for TikTok, Instagram Reels, and YouTube Shorts. The product runs on a user's machine through a Python HTTP server and a browser-based dashboard. It downloads a YouTube video, obtains subtitles, asks an AI model to identify high-potential viral segments, cuts those segments with FFmpeg, optionally adds captions/hooks, and exposes generated files for local download.

The current product is intentionally local-first. Public hosting is out of scope until authentication, queueing, worker isolation, storage, secret management, and rate limiting are designed.

## 2. Product Goals

### Primary Goals

- Turn a YouTube URL into multiple ready-to-post short-form video clips.
- Make clipping usable by non-technical Indonesian creators through a simple dashboard.
- Prioritize viral potential: conflict, emotion, punchlines, strong opinions, quotable hooks, relatable moments.
- Keep all sensitive credentials local: API keys, YouTube cookies, generated files.
- Minimize setup: install Python dependencies, run `python server.py`, open local browser.

### Secondary Goals

- Support configurable AI providers through OpenAI-compatible APIs.
- Support Indonesian-first subtitle and prompt behavior.
- Allow users to customize clip-selection direction with freeform instructions.
- Preserve generated clip history by scanning local output folders.
- Remain self-contained so the folder can become a standalone repository.

## 3. Target Users

### Primary User

Indonesian content creators, editors, podcast teams, and social media operators who want to repurpose long YouTube videos into short viral clips without manually scrubbing timelines.

### Secondary Users

- Solo creators editing podcasts/interviews.
- Agencies managing multiple social channels.
- Technical users who want a local AI-assisted clipping pipeline.
- Internal operators preparing content batches before manual publishing.

## 4. User Problems

- Finding the best viral moments in long videos is slow.
- Manual clipping requires timeline editing skill.
- Repurposing podcast/interview content needs narrative judgment, not just random cuts.
- YouTube download access often requires valid cookies.
- Users want local control over API keys, cookies, and output files.

## 5. Value Proposition

KlipKlop Web turns long YouTube content into short, platform-ready clips by combining transcript analysis, AI highlight selection, FFmpeg video processing, and a simple local dashboard. It focuses on Indonesian viral content patterns and keeps the user's data on their own machine.

## 6. Current Scope

### In Scope

- Local web dashboard.
- YouTube URL input.
- Local Python HTTP server.
- Settings modal for AI provider, API key, model, subtitle language, output directory.
- Cookie upload/storage via `cookie.txt` and synced `cookies.txt`.
- Processing status and progress bar.
- Background single-job processing.
- Generated output listing/history.
- Download endpoint for generated files.
- AI highlight selection using OpenAI-compatible provider config.
- Subtitle-based highlight detection.
- 9:16 output support.
- Optional captions if Caption Maker/Whisper API key exists.
- Optional hook generation if Hook Maker/TTS key exists, though currently disabled in the UI request payload.
- GPU encoding support in core config, currently not exposed in the UI.

### Out of Scope Now

- Public multi-user hosting.
- User accounts/auth.
- Cloud queue/worker architecture.
- Remote object storage.
- Browser-based editing timeline.
- Manual trim adjustment.
- Direct upload to TikTok/Reels/Shorts.
- Multi-job queue in the local UI.
- 1:1 and 16:9 processing, despite visible UI options.
- Collaborative review.
- Billing/subscriptions.

## 7. Product Principles

- Local-first: secrets and files stay on the user's machine.
- Indonesian-first: default prompt, UI copy, and viral criteria target Indonesian audiences.
- Simple before powerful: one URL, one process button, downloadable outputs.
- No silent secret exposure: API keys are write-only from the UI and never returned by API responses.
- One active processing job at a time.
- Fail with actionable messages when cookies, captions, URLs, or providers are invalid.

## 8. User Journey

### First-Time Setup

1. User installs dependencies with `pip install -r requirements.txt`.
2. User starts the server with `python server.py`.
3. Browser opens `http://127.0.0.1:8765`.
4. User opens settings.
5. User enters AI provider Base URL, API key, model, subtitle language, and output directory.
6. User uploads or creates `cookie.txt` locally.
7. App stores config in `config.json`.

### Clip Creation

1. User pastes a YouTube URL.
2. User chooses screen size; current backend accepts only `9:16`.
3. User toggles captions.
4. User optionally adds clip direction/instructions.
5. User clicks `Proses Klip`.
6. Backend validates URL, job state, screen size, and required keys.
7. Background thread starts.
8. UI polls `/api/status` every 800 ms.
9. Core downloads video/subtitle.
10. Core sends transcript + video context to AI highlight model.
11. Core receives exact clip segment JSON.
12. Core cuts clips and writes outputs.
13. UI shows completion and refreshes result/history panels.
14. User downloads files through `/api/download`.

### Error Journey

- Empty URL -> immediate validation error.
- Unsupported screen size -> immediate error stating only `9:16` is supported.
- Captions enabled without Caption Maker key -> immediate error.
- Hook enabled without Hook Maker key -> immediate error.
- Processing already running -> returns busy state.
- Missing/expired YouTube cookies -> core returns detailed recovery instructions.
- Missing subtitle -> core raises subtitle-not-found behavior.

## 9. Functional Requirements

### 9.1 Dashboard

The dashboard must provide:

- Product header with KlipKlop branding.
- Settings button.
- Local profile indicator.
- Sidebar navigation: Beranda and Riwayat.
- YouTube URL input.
- Screen size selector with `9:16`, `1:1`, `16:9` options.
- Captions toggle.
- Optional instruction modal with max 1000 characters.
- Process button.
- Progress bar.
- Status text.
- Result panel.
- History panel listing generated files.

### 9.2 Settings

Settings must support:

- Base URL / provider.
- API key input.
- Model name.
- Subtitle language selection: `id`, `en`, `ms`, `auto`.
- Output directory.
- Save settings.
- Clear API key.
- API key masking: API key must not be returned to frontend after save.
- Indication that API key is saved through `api_key_saved` boolean.

### 9.3 Cookie Handling

The system must:

- Accept cookie content through API.
- Write cookie content to local `cookie.txt`.
- Sync `cookie.txt` to `cookies.txt` for the clipping core.
- Report cookie existence/path to UI.
- Never expose cookie content via API.
- Use cookies for YouTube access when required.

### 9.4 Processing Job

The job manager must:

- Reject invalid URLs.
- Reject a new job while another job thread is alive.
- Reject unsupported screen sizes.
- Validate caption/hook key requirements.
- Run processing in a daemon thread.
- Track status, message, progress, and error.
- Reset active thread after completion/error.
- Return consistent status JSON.

### 9.5 AI Highlight Selection

The core must:

- Use an OpenAI-compatible client/provider config.
- Send transcript and video context to the configured highlight model.
- Use Indonesian viral prompt criteria by default.
- Respect desired clip count.
- Require 60–120 second segments where possible.
- Internally scan multiple candidates, rank by viral potential, then select the strongest clips.
- Prefer segments with conflict, emotion, confession, strong opinion, punchline, or mini-story structure.
- Avoid filler, generic advice, long technical explanations without emotion, and transitions without payoff.
- Require strict JSON output with five fields:
  - `start_time`
  - `end_time`
  - `title`
  - `description`
  - `virality_score`

### 9.6 Video Download

The core must:

- Download YouTube metadata.
- Download source video.
- Request subtitles for configured language unless transcription mode is used.
- Use `yt-dlp` module when available, otherwise subprocess fallback.
- Prefer 720p+ formats when available.
- Merge output to MP4 through FFmpeg.
- Use Deno JS runtime if bundled/available for YouTube extraction.
- Provide clear error messages for 403, bot checks, empty downloads, missing cookies, and missing subtitles.

### 9.7 Video Output

The system must:

- Produce clip files in the configured output directory.
- Support generated companion files such as `.json`, `.srt`, `.ass`, `.txt`.
- List only allowed output file types.
- Limit history response to the newest 50 files.
- Allow download only from inside configured output directory.
- Allow download only for approved extensions: `.mp4`, `.json`, `.srt`, `.ass`, `.txt`.

## 10. API Specification

### `GET /api/status`

Returns current processing state.

Response:

```json
{
  "status": "idle|running|complete|error",
  "message": "string",
  "progress": 0.0,
  "error": "string"
}
```

### `GET /api/settings`

Returns safe settings.

Response fields:

- `base_url`
- `api_key` always empty string
- `api_key_saved`
- `caption_key_saved`
- `hook_key_saved`
- `model`
- `subtitle_language`
- `output_dir`
- `cookies`

### `POST /api/settings`

Saves provider/model/output settings.

Request fields:

- `base_url`
- `api_key`
- `model`
- `subtitle_language`
- `output_dir`
- `clear_api_key`

Response:

```json
{
  "status": "saved",
  "settings": {}
}
```

### `POST /api/cookies`

Saves cookie content.

Request:

```json
{
  "content": "Netscape cookie text"
}
```

Response:

```json
{
  "status": "saved",
  "cookies": {
    "exists": true,
    "path": ".../cookie.txt"
  }
}
```

### `POST /api/start`

Starts clipping process.

Request fields:

- `url`
- `num_clips`
- `add_captions`
- `add_hook`
- `screen_size`
- `subtitle_language`
- `instruction`

Response success:

```json
{
  "status": "started"
}
```

Response busy:

```json
{
  "status": "busy",
  "message": "Processing is already running"
}
```

Response error:

```json
{
  "status": "error",
  "message": "..."
}
```

### `GET /api/outputs`

Lists generated output files.

Response:

```json
{
  "files": [
    {
      "name": "clip.mp4",
      "path": "absolute local path",
      "size": 123
    }
  ]
}
```

### `GET /api/download?path=...`

Downloads approved output file from configured output directory.

Rules:

- File must exist.
- File must be inside output directory.
- Extension must be allowlisted.

## 11. Data & Configuration

### Local Config File

`config.json` stores:

- Legacy `api_key`, `base_url`, `model`.
- `tts_model`.
- `temperature`.
- `output_dir`.
- `system_prompt`.
- `installation_id`.
- `ai_providers`:
  - `highlight_finder`
  - `caption_maker`
  - `hook_maker`
  - `youtube_title_maker`
- `watermark`.
- `face_tracking_mode`.
- `mediapipe_settings`.
- `repliz`.
- `gpu_acceleration`.

### Local Files

- `cookie.txt`: user-facing cookie file.
- `cookies.txt`: synced cookie file consumed by core.
- `output/`: generated clips.
- `output/_temp/`: temporary downloaded media/subtitles.
- `ffmpeg/`: bundled FFmpeg/FFprobe binaries.
- `bin/deno.exe`: bundled Deno runtime.

## 12. Security Requirements

- Server binds to `127.0.0.1` only.
- API keys must never be returned from settings APIs.
- Cookie contents must never be returned from APIs.
- Static file serving must block path traversal.
- Download endpoint must restrict files to output directory and allowlisted extensions.
- Public hosting must not happen without auth, secret vault, storage, worker isolation, queueing, and rate limiting.
- Generated output paths are local filesystem paths and should not be exposed beyond local trusted use.

## 13. Non-Functional Requirements

### Performance

- UI status polling interval: 800 ms.
- Processing should happen in background thread so UI server remains responsive.
- FFmpeg should use CPU by default.
- GPU acceleration may be enabled by config and must fall back to CPU if hardware encoder fails.
- Future performance improvements should prioritize frame sampling, static center crop, analysis downscaling, and worker queueing.

### Reliability

- Single active job prevents concurrent file/temp conflicts.
- Job manager must clear thread state in `finally`.
- Failed processing must preserve error message for UI.
- Missing cookies/subtitles/provider keys should produce actionable errors.

### Compatibility

- Windows is a first-class environment.
- FFmpeg, FFprobe, and Deno can be bundled locally.
- Python dependencies are listed in `requirements.txt`.
- Browser UI uses plain HTML/CSS/JS with Tailwind CDN.

### Maintainability

- Keep app self-contained.
- Avoid adding frontend build tooling unless needed.
- Prefer stdlib HTTP server for local-only mode.
- Keep tests runnable with `python tests/test_job_manager.py`.

## 14. UX Requirements

### Language

- UI copy should primarily use Bahasa Indonesia.
- AI prompt should target Indonesian viral content.
- Error messages may use Indonesian explanations for user recovery.

### Interaction Rules

- `Proses Klip` disables during active processing.
- Progress bar reflects backend progress.
- History refreshes after completion.
- Settings save shows status text.
- API key field clears after save and uses placeholder to indicate saved key.
- Instruction modal enforces 1000 character max and shows live count.

### Current UX Gaps

- Cookie upload UI endpoint exists but no visible cookie upload input in current dashboard.
- `1:1` and `16:9` options are visible but backend rejects them.
- Step copy says AI selects 5 clips while request defaults to 3 clips.
- Caption toggle requires a Caption Maker key, but settings modal does not expose Caption Maker key separately.
- Hook generation exists in backend/core but UI sends `add_hook: false`.

## 15. Acceptance Criteria

### Basic Run

- Given dependencies are installed, when user runs `python server.py`, then browser opens local dashboard at `127.0.0.1:8765`.

### Settings Save

- Given user saves API key, when frontend reloads settings, then `api_key` is empty and `api_key_saved` is true.

### Invalid URL

- Given empty URL, when user starts processing, then backend returns error and no thread starts.

### Busy State

- Given a job is running, when user starts another job, then backend returns `busy`.

### Unsupported Size

- Given screen size `1:1` or `16:9`, when user starts processing, then backend returns error: only `9:16` is currently supported.

### Cookie Save

- Given valid cookie text, when user saves cookies, then `cookie.txt` and `cookies.txt` are written locally.

### Output Listing

- Given output folder contains `clip.mp4` and `secret.key`, when `/api/outputs` is called, then only `clip.mp4` is returned.

### Download Safety

- Given a path outside output dir, when `/api/download` is called, then server returns 404.

## 16. Known Constraints

- Local-only architecture.
- One processing job at a time.
- 9:16 output only.
- AI output quality depends on transcript quality and model behavior.
- YouTube download reliability depends on `yt-dlp`, cookies, and YouTube anti-bot behavior.
- Captions require separate Caption Maker/Whisper API key in config.
- Large videos may take significant time and disk space.

## 17. Roadmap

### Near-Term

- Add visible cookie upload/paste UI or auto-cookie refresh button.
- Align UI clip count copy with actual default.
- Hide or disable unsupported `1:1` and `16:9` options until implemented.
- Expose Caption Maker and Hook Maker provider keys in settings.
- Add GPU toggle and frame-skip setting in UI.
- Add clearer subtitle/transcription fallback behavior.

### Mid-Term

- Implement 1:1 output.
- Implement 16:9 output.
- Add static center-crop mode for faster processing.
- Add analysis downscaling.
- Add frame sampling controls.
- Add manual clip review/edit before rendering.
- Add cancellable running jobs.

### Future Hosted Version

Required before public deployment:

- Authentication.
- Per-user projects/files.
- Queue system.
- Isolated FFmpeg workers.
- Durable storage.
- Secret vault.
- Rate limiting.
- Abuse prevention.
- Usage/billing model.
- Observability/log retention.

## 18. Success Metrics

### Local Product Metrics

- Time from app start to first processing attempt.
- Successful clip generation rate.
- Average processing time per source minute.
- Frequency of cookie-related failures.
- Frequency of subtitle-related failures.
- Number of downloaded/generated clips per session.

### Quality Metrics

- User-rated virality/usefulness of selected clips.
- Percentage of AI-selected clips accepted without manual adjustment.
- Caption readability.
- Hook/title usefulness.
- Output video compatibility with target platforms.

## 19. Backend Implementation Notes

### Core Server

- Keep the backend local-only and bound to `127.0.0.1`.
- Use stdlib HTTP server unless local-only constraints no longer hold.
- Keep API responses JSON-only for `/api/*` endpoints.
- Keep static file serving separate from API routing.
- There is no `/settings` page route; settings are exposed through `GET /api/settings` and `POST /api/settings` only.
- Reject unsupported methods with clear HTTP status codes.

### Request Validation

- Validate JSON body size before parsing large requests.
- Validate YouTube URL before starting any background work.
- Validate `screen_size` against supported values before calling the core processor.
- Clamp `num_clips` to a safe local range.
- Trim `instruction` and enforce the 1000 character limit server-side.
- Treat all paths from requests as untrusted.

### Job Lifecycle

- Allow exactly one active job thread.
- Store job state in one shared status object.
- Update status messages at each major processing phase.
- Clear active thread state in `finally` after success or failure.
- Preserve the last error until the next run starts.
- Do not kill in-flight FFmpeg/yt-dlp processes unless cancellable jobs are explicitly implemented.

### File Safety

- Resolve output paths before listing or downloading files.
- Only expose files inside configured output directory.
- Keep extension allowlist for downloads and history listing.
- Never return `cookie.txt`, `cookies.txt`, config files, logs, or API keys through download endpoints.
- Prefer generated filenames that avoid user-controlled raw title text where possible.

### Config & Secrets

- Keep API keys write-only from frontend APIs.
- Return only boolean saved flags for configured keys.
- Report cookie existence/path through `GET /api/settings` and `POST /api/cookies`; the current UI may omit visible cookie status because users can manage cookie files manually.
- Sync `cookie.txt` to `cookies.txt` after cookie save.
- Avoid logging API keys, cookies, request bodies, or full provider headers.
- Keep config backward compatible with existing `config.json` fields.

### Processing Integration

- Backend should call one orchestration function for clipping work.
- Core processor should own video download, subtitle retrieval, AI highlight selection, FFmpeg rendering, and optional captions/hooks.
- Backend should translate predictable exceptions into actionable UI messages.
- Unexpected exceptions should be returned as safe error text and logged locally only.

### Backend Acceptance Criteria

- Empty URL returns error and does not start a thread.
- Invalid JSON returns HTTP 400.
- Active job returns `busy` and keeps current job running.
- Unsupported screen size returns error before core processing.
- Saved settings never return API key values.
- Saved cookies create both `cookie.txt` and `cookies.txt`.
- Output listing excludes disallowed extensions.
- Download rejects paths outside output directory.
- Download rejects non-allowlisted extensions.
- Job state returns to `idle`, `complete`, or `error` after every run.

## 20. Open Questions

- Should the product support transcription fallback when YouTube subtitles are unavailable?
- Should `num_clips` be user-configurable in the UI?
- Should captions default off until Caption Maker key is configured?
- Should unsupported screen sizes be hidden rather than selectable?
- Should cookies be pasted, uploaded, auto-refreshed from browser, or all three?
- Should output deletion/cleanup be available from the UI?
- Should processing logs be visible in the dashboard?
- Should AI provider settings be split by feature instead of one shared Base URL/model field?
