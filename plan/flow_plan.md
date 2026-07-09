# Flow Plan: Fast Clip Generation + Good Subtitles

## Goal

Generate clips faster without downloading full video, while keeping final subtitles accurate and matching Preview Editor settings.

## Core Rules

- Never download full video.
- Download full audio only when YouTube subtitle is unavailable.
- Download video only by selected timestamp sections.
- If section download fails, show error. No full-video fallback.
- Preview Editor settings are the render contract.

## Best Flow

### 1. Get metadata + subtitle

Input: YouTube URL.

Steps:
- Fetch video metadata.
- Try downloading YouTube subtitle/transcript.

Result:
- If subtitle exists, use it for AI highlight selection.
- If subtitle does not exist, continue to audio-only transcription.

### 2. Audio-only fallback when no subtitle

Steps:
- Download audio-only full video.
- Run local faster-whisper in fast mode.
- Produce segment-level transcript with timestamps.
- Delete temporary audio after transcript is ready.

Purpose:
- Only to let AI know where good moments are.
- Not used as final subtitle quality source.

Recommended mode:
- model: `small`
- device: `cpu`
- compute_type: `int8`
- word timestamps: off for this stage

Recommended audio format:
- Use MP3 mono 16kHz at 32kbps for the audio-only fallback.
- This is small, simple, and compatible with faster-whisper.
- Approx size: 60 minutes ≈ 14 MB, 120 minutes ≈ 28 MB.
- Avoid Opus unless needed; it is smaller but may require extra conversion before Whisper.

Target FFmpeg profile:
```bash
ffmpeg -i input -vn -ac 1 -ar 16000 -b:a 32k audio.mp3
```

### 3. AI highlight selection

Input:
- metadata
- subtitle transcript or audio transcript
- requested clip count: `1`, `3`, or `5`

Output per clip:
- `start_time`
- `end_time`
- `title`
- `description`
- `virality_score`

Rules:
- Return exactly requested clip count when possible.
- Reject clips too short.
- If AI returns too few usable clips, show clear error or fill from transcript only if acceptable later.

### 4. Download video sections only

For each AI timestamp:
- Download only that video section.
- Do not download full video.

Example:
```text
clip 1: download 00:12:30 - 00:13:10
clip 2: download 00:24:05 - 00:24:52
clip 3: download 00:41:20 - 00:42:01
```

Failure behavior:
- If a section fails, stop job and show error.
- No fallback to full video.

### 5. Final subtitle per clip

For each downloaded video section:
- Extract audio from that section.
- Run local faster-whisper with word-level timestamps.
- Burn subtitle from section transcript.

Purpose:
- Final subtitles are accurate for each clip.
- Avoid using rough full-audio transcript for final subtitle rendering.

Recommended mode:
- same model/device/compute_type
- word timestamps: on

### 6. Render according to Preview Editor

Render must use saved settings from `frontend/src/pages/Preview.tsx`:

- background blur enabled
- background zoom
- foreground video scale
- blur strength
- credit text enabled/text/color/size/opacity/position
- watermark enabled/image/scale/opacity/position
- hook enabled/text color/background/size/radius/shape/position/font
- subtitle enabled/color/background/opacity/size/weight/position/transform/font

Preview Editor is the visual contract. Generated output should match it as closely as possible.

## Final Pipeline

```text
YouTube URL
→ metadata
→ try subtitle
→ if subtitle exists: use subtitle transcript
→ if subtitle missing: download audio-only full + fast Whisper segment transcript
→ AI selects timestamps
→ download video sections only
→ for each section: Whisper word-level subtitle
→ render overlays/subtitles from Preview settings
→ output master.mp4 per clip
```

## Stop Behavior

Stop must cancel:
- audio-only download
- YouTube subtitle download
- video section download
- Whisper transcription when possible
- FFmpeg render

UI should immediately leave processing state after stop request.

## Expected Benefits

- Faster than full video download.
- Lower bandwidth.
- Better stop responsiveness.
- Better final subtitle accuracy.
- Output matches Preview Editor settings.
