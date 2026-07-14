# Fast, Accurate Clip Editor Preview Design

**Date:** 2026-07-14

## Goal

Make hook, subtitle, watermark, credit, and blur changes visible immediately while editing, then provide a fast rendered verification whose composition matches the final render.

## Confirmed Problems

1. The editor video displays `draft.mp4`; control changes only update React state and cannot alter that encoded file (`frontend/src/pages/Preview.tsx:101-124`, `frontend/src/components/clip-editor/ClipEditorModal.tsx:100`).
2. Preview forces 480p while final uses the draft quality, so font metrics, wrapping, outlines, blur radius, and positions can differ after integer rounding (`job_manager.py:1074-1075`).
3. Portrait preview performs a complete reframe encode, writes a temporary MP4, then performs another complete composite encode (`clipper_export.py:452-487`).
4. Preview is one blocking HTTP request with no progress, cancellation UI, or frontend timeout (`server.py:193-195`, `frontend/src/pages/Preview.tsx:112-124`).
5. Blur only executes for landscape input; the current editor gives no explanation when the source is portrait (`clipper_portrait.py:170-186`).
6. Word highlighting only exists when `transcript.words` is present. Segment-only transcripts produce static subtitle text, so no active word can turn blue (`clipper_export.py:573-625`).
7. If generation started with captions disabled, metadata stores an empty `transcript_path`; enabling subtitle later fails even though `transcript.json` exists (`clipper_export.py:333-360`, `clipper_export.py:442-468`).
8. Editor/default retrieval performs unrelated remote Vault checks, and media Range requests repeat full settings retrieval (`job_manager.py:310-348`, `server.py:590-602`).
9. Frontend, backend, and migration defaults disagree, causing inconsistent initial/reset values (`frontend/src/components/layout/DashboardLayout.tsx:35-50`, `config/config_manager.py:127-142`, `job_manager.py:337-341`).

## Selected Approach

Use two complementary preview layers:

1. **Live editor preview:** browser composition updates immediately without encoding. It uses the source clip, normalized settings, local renderer fonts, synchronized foreground/background video, and timed subtitle data.
2. **Accurate render verification:** an asynchronous FFmpeg preview uses the same scene builder and target-resolution layout as final rendering. It performs one video encode, exposes progress/cancel state, and caches by all render inputs.

The live layer prioritizes interaction speed. The rendered verification is the accuracy authority. The UI must clearly label whether the user is viewing “Live” or “Rendered verification” and mark rendered output stale after any setting changes.

## Architecture

### 1. Canonical editor contract

Backend owns normalization. `GET /api/clip` returns:

- account defaults without Vault/network checks;
- draft and committed settings;
- source/draft/final URLs;
- source geometry (`width`, `height`, sample/display aspect ratio, rotation, and `is_landscape`);
- normalized subtitle cues produced by the backend cue builder;
- subtitle capability: `word_highlight`, `static_segments`, or `unavailable`;
- scoped `watermark_url` plus an opaque watermark revision when an asset exists.

Source geometry is persisted when `source.mp4` is created. Legacy clips receive one cached probe whose result is written to `data.json` atomically; editor loads never repeatedly probe media.

Both preview and final POST requests run through the same `_render_settings()` normalization. Rendering, cache hashing, and browser scene data consume the normalized contract rather than separate defaults. Subtitle cues contain cue start/end, complete transformed chunk text, per-word start/end/text, and active-word indexes. ASS generation and live preview consume this shared cue output; the frontend does not duplicate backend chunking rules.

`source.mp4` becomes a read-only `source` clip artifact. The browser never receives `watermark.image_path`; an authenticated watermark artifact endpoint serves only files inside the current user's watermark root. Media authorization remains scoped to the current user's output root.

### 2. Live browser composition

Create a focused `LiveClipPreview` component. For 9:16 landscape sources with `blur_background.enabled=true`, it renders a duplicated blurred/darkened background plus a synchronized centered foreground at the configured scale. With blur disabled, it contain-fits the foreground over a black canvas, matching the final center path. Hook, subtitle, watermark, and credit layers follow renderer order.

For portrait sources, blur controls are disabled because the current final renderer never applies blur to non-landscape input; explain that non-9:16 portrait input may still be letterboxed. For 16:9 output, use one source video without the portrait background stack.

The component uses bundled `PlusJakartaSans.ttf`, `Poppins-Regular.ttf`, and `Poppins-Bold.ttf` through local `@font-face` declarations. Position values remain normalized ratios. Font, watermark, outline, opacity, transform, and visibility calculations mirror renderer formulas at a canonical 340px preview width. Live watermark rendering uses only the scoped `watermark_url`.

Subtitle playback uses the current video time and backend-produced cues. Word cues highlight exactly one active word. Segment-only cues display static timed text and show that active-word highlighting is unavailable. Missing cues disable subtitle activation with a precise message instead of failing late during render.

### 3. Shared FFmpeg scene builder

Refactor portrait/background generation into reusable filter-graph builders. `render_existing_clip()` reads `source.mp4` once and builds one graph containing:

1. portrait background/foreground composition;
2. hook overlay;
3. ASS subtitle;
4. watermark;
5. credit;
6. final format/optional preview downscale.

No intermediate portrait MP4 is written. Audio maps from the same source input.

Accurate preview computes overlay assets and ASS at the final target resolution, then downscales the fully composed frame to 480p within the same graph before encoding. This preserves final wrapping, placement, and outline decisions while reducing output encode cost. Final render omits the last downscale.

Preview uses a dedicated fast encoder profile. Final keeps existing quality behavior. Both paths use identical normalized settings, target dimensions, font files, subtitle timeline, and layer order.

### 4. Asynchronous preview lifecycle

`POST /api/clip/preview` starts or reuses a preview job and returns immediately with `preview_id`. Add scoped status and cancel endpoints:

- `GET /api/clip/preview/status?clip_id=...&preview_id=...`
- `POST /api/clip/preview/cancel`

Status includes `state`, `stage`, `progress`, `elapsed_seconds`, `stream_url`, and sanitized `error`. Preview state is keyed by user + clip + preview ID, not process-global display variables.

At job creation, persist an immutable snapshot containing normalized settings, normalized hook text, source/transcript/watermark identities, target dimensions, subtitle cues, renderer versions, and cache digest. Workers render only this snapshot, never mutable clip metadata.

The frontend polls while active, shows progress and elapsed time, permits cancellation, and continues allowing modal close. Starting a newer preview supersedes the older preview for that clip. A process-wide bounded render scheduler caps concurrent FFmpeg processes, prioritizes final renders, and cancels superseded queued/running previews while retaining per-user ownership checks.

The cache digest includes normalized settings, hook text, render revision, source/transcript/watermark fingerprints, target/output dimensions, scene-builder version, cue-builder version, selected font hashes, preview encoder profile, and FFmpeg compatibility key. Keep only the newest bounded set of preview artifacts per clip.

### 5. Settings consistency

Move editor defaults to one canonical backend constant/schema. Frontend does not invent style defaults before settings load; it shows loading state or uses the canonical response. Migrations only add missing fields and never overwrite explicit user choices.

Dashboard blur controls write one canonical nested `blur_background.enabled` value. `landscape_blur` remains a derived compatibility field until old metadata is migrated.

### 6. UX states

- Every valid control change updates live composition immediately.
- Any change after rendered verification marks it stale.
- “Render Preview Akurat” starts async verification.
- Progress shows stage, percentage, elapsed time, and cancel action.
- Successful verification switches the video source to the rendered artifact and labels it “Akurat”.
- Editing again switches back to “Live” and marks verification stale.
- Final render uses the current normalized state even if the user skips verification.
- Subtitle cannot be enabled without usable timed content; reason appears beside the toggle.
- Active-word color control is disabled for segment-only transcripts with explanatory text.
- Blur control is disabled for portrait source with explanatory text.
- Missing watermark image is an actionable validation error; renderer does not silently create a `LOGO` placeholder.
- Watermark upload decodes and verifies the image, enforces permitted decoded formats and pixel limits, rejects animated/malformed files, strips metadata, and re-encodes to a canonical server-generated filename.
- Enabled credit with missing channel falls back to literal template text after removing unresolved `{channel}`, or is blocked if the resulting text is empty.

## Error Handling

- Invalid settings return field-level errors before job creation.
- Preview cancellation is a normal `cancelled` state, not a generic render failure.
- Stale job completions cannot replace a newer preview URL.
- Source/transcript/watermark changes invalidate cache entries.
- FFmpeg errors remain detailed in server logs; API returns safe stage-specific messages.
- Failed verification leaves live editing usable.
- Failed final render preserves the existing `master.mp4` behavior.

## Testing

### Backend

- normalization parity for preview/final;
- transcript capability and captions-off recovery;
- active-word ASS color/timing;
- one-pass graph: one source, one video encoder, no portrait temporary file;
- final-resolution overlay followed by preview downscale;
- async status, cancellation, stale-attempt protection, and cache fingerprints;
- bounded artifact cleanup;
- source artifact authorization;
- editor defaults and media serving perform no Vault calls;
- portrait blur and missing watermark validation.

### Frontend

Add Vitest + React Testing Library because no frontend test runner exists. Cover:

- controls update live layers without API calls;
- source/background videos remain synchronized;
- hook visibility/duration/style;
- subtitle chunking and active-word color at mocked times;
- segment-only/missing transcript states;
- watermark/credit/blur geometry;
- stale rendered-preview state;
- async progress, cancellation, and out-of-order responses.

### Visual acceptance

Use deterministic fixture clips and capture frames from live preview, accurate preview, and final at selected timestamps. Compare normalized bounding boxes, active subtitle word/color, blur state, and layer visibility. Decoded accurate-preview and final frames use declared perceptual thresholds after common scaling; geometry, cue state, and layer visibility must match exactly. Exact pixel equality, when needed for scene-builder tests, compares lossless pre-encode frames from the shared graph. Live preview uses geometry/color tolerances because browser and Pillow/libass rasterization differ.

## Performance Acceptance

Benchmark the same uncached 60-second 1080p landscape fixture on documented deployment hardware. Record fixture checksum, settings, FFmpeg build, encoder, browser, refresh rate, and idle machine load. Run one warm-up plus at least five uncached old/new trials:

- live state reaches the first painted frame within 50ms at p95, measured with `requestAnimationFrame`;
- preview POST acknowledges within 500ms excluding network latency;
- accurate preview performs one video encode, never two;
- median new accurate-preview wall time is at most 60% of the median current baseline;
- cached preview resolves without FFmpeg execution;
- cancel request stops FFmpeg and reaches `cancelled` within 3 seconds;
- no repeated Vault RPC occurs during editor load or clip media Range requests.

## Out of Scope

- frame-by-frame browser parity with Pillow/libass;
- changing final video quality or aspect ratio inside the editor;
- generating new word timestamps during editing;
- adding GPU encoding before deployment hardware capability is measured;
- broad replacement of filesystem clip storage.
