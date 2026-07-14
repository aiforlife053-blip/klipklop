# Fast, Accurate Clip Editor Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every valid editor change visible immediately, make accurate preview substantially faster, and guarantee that accurate preview and final render share settings, subtitle cues, geometry, fonts, and layer composition.

**Architecture:** Add a canonical backend editor contract and subtitle cue builder, render a synchronized live scene in React, then refactor FFmpeg composition into one source-to-output graph. Accurate previews run as immutable asynchronous jobs through a bounded scheduler; final renders use the same scene builder with a different output profile.

**Tech Stack:** Python 3.11+, Pillow, FFmpeg, existing `ThreadingHTTPServer`, React 19, TypeScript 6, Vite 8, Radix UI, Tailwind CSS, Vitest, React Testing Library.

## Global Constraints

- Preserve existing authenticated per-user filesystem isolation.
- Never expose absolute source, transcript, watermark, or output paths to the browser.
- No AI/API call during editor load, live preview, accurate preview, final composition, or media Range serving.
- Preview and final settings must pass through the same normalization function.
- Accurate preview and final must share target-resolution layout, cue generation, fonts, and layer order.
- Accurate preview may downscale only after complete target-resolution composition.
- Final rendering must retain atomic `master.mp4` replacement and previous-master recovery.
- Maximum FFmpeg concurrency must be bounded and configurable; final jobs have priority over preview jobs.
- Existing user settings must not be overwritten by migrations.
- Do not commit changes unless the user explicitly requests a commit.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `subtitle_cues.py` | Create | Canonical timed cue/chunk construction used by ASS and browser preview |
| `config/editor_defaults.py` | Create | Canonical editor defaults and renderer version constants |
| `render_scheduler.py` | Create | Bounded final/preview queue, immutable attempts, cancellation, status |
| `clipper_export.py` | Modify | Consume canonical cues; build one source-to-output composite |
| `clipper_portrait.py` | Modify | Return reusable portrait filter fragments instead of requiring an intermediate MP4 |
| `clipper_core.py` | Modify | Accept render profile and scheduler cancellation without changing AI pipeline |
| `clipper_shared.py` | Modify | Add typed editor cue structures |
| `config/config_manager.py` | Modify | Use canonical defaults; add-only migration |
| `job_manager.py` | Modify | Editor contract, source metadata, async preview lifecycle, cache, cleanup |
| `server.py` | Modify | Source/watermark artifacts, preview start/status/cancel routes, cache headers |
| `frontend/public/fonts/*` | Create | Browser copies of renderer fonts |
| `frontend/src/index.css` | Modify | Local `@font-face` declarations |
| `frontend/src/lib/clip-settings.ts` | Modify | Strict editor contract/settings/cue types and shared UI calculations |
| `frontend/src/components/clip-editor/LiveClipPreview.tsx` | Create | Immediate synchronized browser composition |
| `frontend/src/components/clip-editor/ClipEditorModal.tsx` | Modify | Live/accurate modes, capability states, progress/cancel UI |
| `frontend/src/pages/Preview.tsx` | Modify | Async preview controller, stale protection, polling |
| `frontend/package.json` | Modify | Vitest/RTL scripts and dependencies |
| `frontend/vite.config.ts` | Modify | Vitest jsdom configuration |
| `frontend/src/test/setup.ts` | Create | DOM test setup |
| `frontend/src/**/*.test.tsx` | Create | Live preview and controller regressions |
| `tests/test_subtitle_cues.py` | Create | Cue-builder unit tests |
| `tests/test_render_scheduler.py` | Create | Priority/cancel/stale-attempt tests |
| `tests/test_job_manager.py` | Modify | Contract, one-pass render, cache, defaults, lifecycle regressions |
| `tests/test_backend_security.py` | Modify | Asset ownership/path/upload validation tests |
| `tests/fixtures/preview/*` | Create | Deterministic media/transcript/settings fixtures |
| `tests/benchmark_preview.py` | Create | Repeatable old/new preview benchmark |

---

### Task 1: Freeze Baseline and Add Canonical Editor Defaults

**Files:**
- Create: `config/editor_defaults.py`
- Modify: `config/config_manager.py:70-95,114-150`
- Modify: `job_manager.py:310-348,409-549,950-989`
- Modify: `frontend/src/components/layout/DashboardLayout.tsx:35-50`
- Test: `tests/test_job_manager.py`

**Interfaces:**
- Produces: `EDITOR_DEFAULTS: dict[str, dict[str, object]]`
- Produces: `SCENE_BUILDER_VERSION`, `CUE_BUILDER_VERSION`, `PREVIEW_PROFILE_VERSION`
- Produces: `WebJobManager._editor_defaults_local() -> dict`
- Preserves: `_render_settings(payload, metadata) -> normalized settings`

- [ ] **Step 1: Write failing default-consistency tests**

Add tests proving local editor defaults do not call Vault and migrations preserve explicit values:

```python
def test_editor_defaults_are_local_and_do_not_query_vault(tmp_path, monkeypatch):
    manager = mod.WebJobManager(app_dir=tmp_path, user_id="user-1")
    monkeypatch.setattr(manager, "_vault_key_exists", lambda *_: pytest.fail("Vault called"))
    defaults = manager._editor_defaults_local()
    assert defaults["subtitle"]["color"] == "#00BFFF"
    assert defaults["blur_background"]["enabled"] is False


def test_style_migration_preserves_explicit_user_values(tmp_path):
    from config.config_manager import ConfigManager

    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "hook_style": {"text_color": "#112233"},
        "subtitle": {"color": "#445566"},
        "_text_style_controls_migrated": False,
    }), encoding="utf-8")
    cfg = ConfigManager(path, tmp_path / "output").config
    assert cfg["hook_style"]["text_color"] == "#112233"
    assert cfg["subtitle"]["color"] == "#445566"
```

- [ ] **Step 2: Run tests and confirm failure**

```powershell
pytest tests/test_job_manager.py -k "editor_defaults_are_local or style_migration_preserves" -v
```

Expected: missing `_editor_defaults_local`, plus migration overwrites explicit colors.

- [ ] **Step 3: Define one canonical default object**

Create `config/editor_defaults.py` with immutable source data and cloning:

```python
from copy import deepcopy

SCENE_BUILDER_VERSION = "scene-v2"
CUE_BUILDER_VERSION = "cue-v1"
PREVIEW_PROFILE_VERSION = "preview-v2"

EDITOR_DEFAULTS = {
    "watermark": {"enabled": False, "image_path": "", "position_x": 0.85, "position_y": 0.05, "opacity": 0.8, "scale": 0.15},
    "credit_watermark": {"enabled": False, "text": "sc : {channel}", "color": "#FFFFFF", "size": 0.032, "opacity": 0.55, "position_x": 0.06, "position_y": 0.23},
    "hook_style": {"enabled": False, "font_size": 0.054, "font_family": "Plus Jakarta Sans", "font_weight": 800, "text_color": "#FFD700", "outline_color": "#000000", "outline_thickness": 1.5, "duration": 5.0, "position_x": 0.5, "position_y": 0.2},
    "subtitle": {"enabled": False, "color": "#00BFFF", "text_color": "#FFFFFF", "size": 0.04, "position_x": 0.5, "position_y": 0.85, "text_transform": "uppercase", "bg_color": "#000000", "bg_opacity": 0.0, "font_family": "Plus Jakarta Sans", "font_weight": 800, "outline_color": "#000000", "outline_thickness": 1.0},
    "blur_background": {"enabled": False, "scale": 1.0, "zoom": 1.08, "strength": 30},
}


def editor_defaults():
    return deepcopy(EDITOR_DEFAULTS)
```

- [ ] **Step 4: Replace divergent fallback/default literals**

Use `editor_defaults()` in `ConfigManager`, `get_settings()`, `_editor_defaults_local()`, and `_render_settings()`. Migration logic must use `setdefault` per nested field, never `.update()` over user values. Remove fabricated style defaults from `DashboardLayout`; settings context starts in a loading state until `/api/settings` resolves.

- [ ] **Step 5: Normalize blur from one source**

Persist `blur_background.enabled` as canonical. Keep `landscape_blur = blur_background.enabled` only when producing compatibility renderer settings. Do not let top-level dashboard values overwrite nested blur after normalization.

- [ ] **Step 6: Verify**

```powershell
pytest tests/test_job_manager.py -k "settings or migration or default or blur" -v
npm run lint --prefix frontend
npm run build --prefix frontend
```

Expected: tests pass; frontend contains no competing hook/subtitle/blur style literals.

---

### Task 2: Build Canonical Subtitle Cues and Recover Existing Transcripts

**Files:**
- Create: `subtitle_cues.py`
- Modify: `clipper_shared.py:7-22`
- Modify: `clipper_export.py:494-632`
- Modify: `clipper_export.py:333-360,442-469`
- Modify: `job_manager.py:851-891,944-989`
- Test: `tests/test_subtitle_cues.py`
- Test: `tests/test_job_manager.py:835-876,1786-1808`

**Interfaces:**
- Produces: `build_subtitle_cues(transcript: TimedTranscript, text_transform: str) -> list[SubtitleCue]`
- `SubtitleCue`: `{start: float, end: float, text: str, words: list[CueWord], active_word_indexes: list[int], capability: Literal["word_highlight", "static_segments"]}`
- `CueWord`: `{text: str, start: float, end: float, active_from: float, active_until: float}`
- Consumed by: ASS generation and `GET /api/clip` editor contract

- [ ] **Step 1: Write failing cue tests**

```python
def test_word_cues_preserve_chunking_and_active_windows():
    cues = build_subtitle_cues({
        "duration": 2.0,
        "words": [
            {"word": "satu", "start": 0.0, "end": 0.3},
            {"word": "dua", "start": 0.35, "end": 0.7},
            {"word": "tiga", "start": 0.75, "end": 1.0},
        ],
        "segments": [],
    }, "uppercase")
    assert cues[0]["text"] == "SATU DUA TIGA"
    assert cues[0]["words"][1]["active_from"] == 0.3
    assert cues[0]["words"][1]["active_until"] == 0.7
    assert cues[0]["capability"] == "word_highlight"


def test_segment_cues_are_static_not_fake_word_highlights():
    cues = build_subtitle_cues({
        "duration": 2.0,
        "words": [],
        "segments": [{"text": "halo dunia", "start": 0.0, "end": 2.0}],
    }, "none")
    assert cues == [{"start": 0.0, "end": 2.0, "text": "halo dunia", "words": [], "capability": "static_segments"}]
```

- [ ] **Step 2: Run and confirm failure**

```powershell
pytest tests/test_subtitle_cues.py -v
```

Expected: import/module failure.

- [ ] **Step 3: Extract current chunking exactly once**

Move the punctuation/gap/3–5 word chunk rules from `clipper_export.py:573-610` into `build_subtitle_cues`. Generate active windows using the existing event timing: first word begins at chunk start, later words begin at previous word end, final active window ends at chunk end.

- [ ] **Step 4: Make ASS consume cues**

Replace duplicate chunk construction in `create_ass_subtitle_capcut()` with cue iteration. For `word_highlight`, emit one event per cue word using `subtitle.color` for the active word and `subtitle.text_color` for all others. For `static_segments`, emit one static event and never claim active-word support.

- [ ] **Step 5: Recover captions-off transcript artifacts**

When `metadata.transcript_path` is empty but `clip_dir/transcript.json` exists, validate it and use it if it contains words or segments. Update draft creation to always store `transcript_path="transcript.json"` when the artifact has usable timed content, independent of the initial overlay toggle. Subtitle enablement remains an output setting, not a transcription-retention switch.

- [ ] **Step 6: Return cues and capability from `GET /api/clip`**

Return only validated normalized cues, never transcript filesystem paths. Enforce at most 3,600 cues and 2 MiB of serialized cue JSON. Never silently truncate: an oversized or malformed legacy transcript returns `capability="unavailable"`, `subtitle_cues=[]`, and a safe `subtitle_reason`; add tests for malformed and oversized files.

- [ ] **Step 7: Verify blue active-word regression**

```powershell
pytest tests/test_subtitle_cues.py tests/test_job_manager.py -k "subtitle or caption or transcript" -v
```

Expected: ASS contains BGR conversion of `#00BFFF`; word cue API reports `word_highlight`; captions-off legacy artifact can be enabled later.

---

### Task 3: Persist Source Geometry and Add Safe Editor Assets

**Files:**
- Modify: `clipper_export.py:326-369`
- Modify: `job_manager.py:851-903,944-952`
- Modify: `server.py:126-130,278-299,578-602`
- Test: `tests/test_job_manager.py`
- Test: `tests/test_backend_security.py`

**Interfaces:**
- Produces clip fields: `source_geometry`, `source_url`, `watermark_url`, `watermark_revision`
- Adds clip artifact: `source` mapped to `source.mp4`
- Adds account route: `GET /api/watermark?revision=<sha256>` with watermark-root ownership validation
- `_render_settings(payload, metadata) -> dict` raises `SettingsValidationError(errors: dict[str, str])`
- Preserves current Range behavior and ownership isolation

- [ ] **Step 1: Write failing contract/security tests**

Test that `GET /api/clip` data contains geometry/opaque URLs and no absolute paths. Test traversal, cross-user watermark access, malformed image bytes, animated images, and oversized decoded dimensions.

```python
def test_clip_view_never_exposes_local_asset_paths(tmp_path):
    manager = mod.WebJobManager(app_dir=tmp_path)
    clip_dir = tmp_path / "output" / "generation-1" / "clip-1"
    clip_dir.mkdir(parents=True)
    (clip_dir / "source.mp4").write_bytes(b"source")
    (clip_dir / "draft.mp4").write_bytes(b"draft")
    (clip_dir / "data.json").write_text(json.dumps({
        "clip_id": "clip-1",
        "status": "needs_edit",
        "source_geometry": {"width": 1920, "height": 1080, "is_landscape": True},
        "render_settings": {"watermark": {"image_path": str(tmp_path / "secret.png")}},
    }), encoding="utf-8")
    view = manager.get_clip("clip-1")["clip"]
    encoded = json.dumps(view)
    assert str(tmp_path) not in encoded
    assert view["source_url"].startswith("/api/clip/media?")
    assert view["source_geometry"]["width"] == 1920
```

- [ ] **Step 2: Persist geometry at draft creation**

Store width, height, sample/display aspect ratio, rotation, and derived orientation in `data.json`. For legacy metadata, probe once under the clip lock, atomically write the result, then reuse it.

- [ ] **Step 3: Add browser-safe source and watermark routes**

Add `source` to `clip_artifact()` as `"source": "source.mp4"`. Add `GET /api/watermark?revision=<sha256>` backed by a current-account watermark-root ownership check. `GET /api/clip` returns `source_url`, `watermark_url`, and `watermark_revision`; it never returns `watermark.image_path`. Add immutable cache headers to revisioned source/preview/final/watermark responses and preserve Range headers.

- [ ] **Step 4: Canonicalize watermark uploads**

Decode with Pillow, call `verify()`, reopen, reject animation, enforce PNG/JPEG/WEBP input and maximum decoded dimensions, apply EXIF transpose, convert to RGBA, strip metadata, and save as server-generated PNG under the current account watermark root. Return only `watermark_url` and revision/hash.

- [ ] **Step 5: Sanitize settings and remove placeholder behavior**

Before returning the editor contract, remove `watermark.image_path` from defaults, draft settings, and render settings. `_render_settings()` ignores/rejects client-supplied `image_path`, resolves the owned account watermark server-side, and raises `SettingsValidationError({"watermark.image_path": "Watermark belum tersedia"})` when enabled without a valid asset. Preview, final, and defaults routes catch this exception and return HTTP 400 with `{status: "error", errors}` before job creation or metadata mutation. Remove `watermark_placeholder` and `LOGO` drawing from `clipper_export.py:240-249`.

- [ ] **Step 6: Resolve credit text in the canonical contract**

Add `resolved_credit_text` to the editor/job snapshot. Replace `{channel}` with the channel name; when absent, remove the token and normalize leftover whitespace/punctuation. If credit is enabled and the result is empty, raise `SettingsValidationError({"credit_watermark.text": "Teks credit kosong"})`. Live preview and Pillow consume `resolved_credit_text` and never perform separate template substitution.

- [ ] **Step 7: Decouple media serving from `get_settings()`**

Use `manager.output_dir.resolve()`/account root already established at manager creation. Do not call `get_settings()` or Vault during `_stream_video()`.

- [ ] **Step 8: Verify**

```powershell
pytest tests/test_backend_security.py tests/test_job_manager.py -k "artifact or watermark or geometry or media" -v
```

Expected: ownership tests pass; no absolute path in API JSON; no Vault mock invocation; valid Range response retains cache headers.

---

### Task 4: Implement Immediate Live Browser Composition

**Files:**
- Create: `frontend/public/fonts/PlusJakartaSans.ttf`
- Create: `frontend/public/fonts/Poppins-Regular.ttf`
- Create: `frontend/public/fonts/Poppins-Bold.ttf`
- Modify: `frontend/src/index.css:1-20`
- Modify: `frontend/src/lib/clip-settings.ts`
- Create: `frontend/src/components/clip-editor/LiveClipPreview.tsx`
- Modify: `frontend/src/components/clip-editor/ClipEditorModal.tsx:16-33,84-123`
- Test: `frontend/src/components/clip-editor/LiveClipPreview.test.tsx`

**Interfaces:**
- `SourceGeometry`: `{width: number; height: number; sample_aspect_ratio: string; display_aspect_ratio: string; rotation: number; is_landscape: boolean}`
- `SubtitleCapability`: `'word_highlight' | 'static_segments' | 'unavailable'`
- `CueWord`: `{text: string; start: number; end: number; active_from: number; active_until: number}`
- `SubtitleCue`: `{start: number; end: number; text: string; words: CueWord[]; active_word_indexes: number[]; capability: Exclude<SubtitleCapability, 'unavailable'>}`
- `ClipEditorContract`: `{source_url: string; source_geometry: SourceGeometry; subtitle_cues: SubtitleCue[]; subtitle_capability: SubtitleCapability; subtitle_reason: string; watermark_url: string; watermark_revision: string; resolved_credit_text: string}`
- Consumes: normalized `ClipEditorContract`, `ClipSettings`, `hookText`
- Produces: `onTimeChange(currentTime: number)` and visible live layers
- Uses: browser-safe `source_url`, `watermark_url`, backend subtitle cues and resolved credit text

- [ ] **Step 1: Install frontend test tooling**

```powershell
npm install --prefix frontend --save-dev vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
```

Add scripts:

```json
"test": "vitest run",
"test:watch": "vitest"
```

Configure `environment: 'jsdom'` and `setupFiles: ['./src/test/setup.ts']` in `frontend/vite.config.ts`.

- [ ] **Step 2: Write failing live-layer tests**

Create a complete `fixture` implementing `ClipEditorContract`, a `settings` object with every section, and `vi.stubGlobal('fetch', vi.fn())`. Add executable tests for toggle immediacy, black background when blur is off, duplicated background when on, exact ratio positions, hook duration, scoped watermark URL, resolved credit text, word cue color, segment-only state, video synchronization after a mocked 100ms drift, and absence of `/api/clip/preview` calls after `userEvent.click`/control changes.

```tsx
it('highlights the active word with subtitle.color', () => {
  render(<LiveClipPreview contract={fixture} settings={settings} hookText="HOOK" currentTime={0.45} onTimeChange={vi.fn()} />);
  expect(screen.getByText('DUA')).toHaveStyle({ color: '#00BFFF' });
  expect(screen.getByText('SATU')).toHaveStyle({ color: '#FFFFFF' });
});

it('does not render an accurate preview on a live control change', async () => {
  const api = vi.mocked(fetch);
  render(<EditorHarness contract={fixture} initialSettings={settings} />);
  await userEvent.click(screen.getByRole('checkbox', { name: 'Tampilkan hook' }));
  expect(screen.queryByTestId('live-hook')).not.toBeInTheDocument();
  expect(api).not.toHaveBeenCalledWith(expect.stringContaining('/api/clip/preview'), expect.anything());
});
```

- [ ] **Step 3: Bundle renderer fonts locally**

Copy the three existing repository font files into `frontend/public/fonts/`. Define matching `@font-face` families and weights; remove dependence on Google-hosted fonts for preview layers.

- [ ] **Step 4: Implement synchronized video stack**

Use one foreground `<video>` as playback authority. A muted, non-interactive background `<video>` mirrors play/pause, seeking, playback rate, and current time. Correct drift above 80ms during `timeupdate`/`requestVideoFrameCallback` where available. Blur-off landscape uses a black canvas with contain-fit; blur-on uses cover, CSS blur, zoom, darkening, and centered configured foreground scale.

- [ ] **Step 5: Implement overlay formulas**

Use ratio positions relative to the rendered frame. Calculate text sizes from the same canonical 340px width formulas used by `_scale_from_preview_width`. Apply renderer ordering: hook, subtitle, watermark, credit. Hook is uppercase and visible only for `currentTime <= duration`. Use backend cue text/timing and `resolved_credit_text`; never perform frontend chunking or credit-template substitution.

- [ ] **Step 6: Add capability feedback**

Disable blur for non-landscape sources. Disable subtitle for unavailable cues. Disable active-word color for `static_segments`. Show short Indonesian explanations adjacent to affected controls.

- [ ] **Step 7: Verify**

```powershell
npm run test --prefix frontend
npm run lint --prefix frontend
npm run build --prefix frontend
```

Expected: live tests pass; toggles update DOM synchronously; production bundle includes local font assets.

---

### Task 5: Refactor Rendering into One Shared FFmpeg Scene

**Files:**
- Modify: `clipper_portrait.py:170-260`
- Modify: `clipper_export.py:203-269,433-492`
- Modify: `clipper_core.py:49-88`
- Test: `tests/test_job_manager.py:910-953,1387-1407`

**Interfaces:**
- Produces: `_portrait_filter(width: int, height: int, blur_enabled: bool) -> tuple[list[str], str]`
- `RenderAssets`: `{hook_overlay: Path | None, ass_file: Path | None, watermark_path: Path | None, credit_overlay: Path | None}`
- Produces: `_build_render_command(source: Path, output: Path, duration: float, target_size: tuple[int, int], output_size: tuple[int, int], assets: RenderAssets, profile: Literal["preview_fast", "final"]) -> list[str]`
- One source decode path; one video encoder per render

- [ ] **Step 1: Write failing one-pass tests**

Assert command has one source input, one `-c:v`, portrait filters before overlays, preview `scale` after all overlays, source audio mapping, and no `*.portrait.mp4` temporary artifact.

```python
def test_preview_scene_composes_at_target_then_downscales(tmp_path):
    harness = object.__new__(SubtitleHarness)
    harness.ffmpeg_path = "ffmpeg"
    harness.output_resolution = "1080:1920"
    harness.screen_size = "9:16"
    harness.landscape_blur = True
    harness.blur_background_settings = {"enabled": True, "zoom": 1.08, "strength": 30, "scale": 1.0}
    harness.get_video_encoder_args = lambda: ["-c:v", "libx264"]
    assets = {
        "hook_overlay": tmp_path / "hook.png",
        "ass_file": tmp_path / "captions.ass",
        "watermark_path": None,
        "credit_overlay": tmp_path / "credit.png",
    }
    command = harness._build_render_command(
        source=tmp_path / "source.mp4",
        output=tmp_path / "preview.mp4",
        duration=10.0,
        target_size=(1080, 1920),
        output_size=(540, 960),
        assets=assets,
        profile="preview_fast",
    )
    graph = command[command.index("-filter_complex") + 1]
    assert graph.index("ass=") < graph.rindex("scale=540:960")
    assert command.count("-c:v") == 1
```

- [ ] **Step 2: Run and confirm failure**

```powershell
pytest tests/test_job_manager.py -k "one_pass or composes_at_target or final_composite" -v
```

Expected: missing shared builder/current intermediate path fails contract.

- [ ] **Step 3: Convert portrait methods into filter fragments**

Extract blur-on and black-background formulas from `_preview_blur_filter()`/`convert_to_portrait_center()` into labeled filter fragments operating directly on `[0:v]`. Preserve landscape-only blur condition and 16:9 bypass.

- [ ] **Step 4: Build overlays at final target dimensions**

Generate hook PNG, credit PNG, watermark scale, and ASS PlayRes using final `video_quality` target dimensions for both preview and final. Append preview downscale only after credit composition. Map audio directly from source.

- [ ] **Step 5: Add explicit render profiles**

`preview_fast` selects 480 output dimensions and `libx264 -preset ultrafast -crf 30`; `final` preserves current encoder selection. Encoder profile affects cache digest but never layout calculations.

- [ ] **Step 6: Use one media probe**

Replace separate `_probe_render_input()` and `_has_audio_stream()` launches with one structured probe returning width, height, duration, rotation, and audio presence. Reuse persisted source geometry where valid.

- [ ] **Step 7: Verify regression and encode count**

```powershell
pytest tests/test_job_manager.py -k "blur or hook or ass or composite or preview" -v
```

Expected: renderer command contains one video encode; no portrait temporary; active-word colors and layer order remain correct.

---

### Task 6: Add Immutable Async Preview Jobs and Bounded Scheduling

**Files:**
- Create: `render_scheduler.py`
- Modify: `clipper_ffmpeg.py:24,237-240,345-362`
- Modify: `job_manager.py:39-42,991-1133`
- Modify: `server.py:120-145,193-201`
- Test: `tests/test_render_scheduler.py`
- Test: `tests/test_job_manager.py`

**Interfaces:**
- `RenderAttempt`: immutable user/clip/attempt/snapshot/digest/profile structure
- `RenderScheduler.submit(attempt: RenderAttempt, run: Callable[[RenderAttempt, threading.Event, ProgressCallback], Path], priority: int) -> str`
- `RenderScheduler.status(owner: str, clip_id: str, attempt_id: str) -> PreviewStatus`
- `RenderScheduler.cancel(owner: str, clip_id: str, attempt_id: str) -> bool`
- POST response: `{status: "queued" | "cached", preview_id: string, stream_url?: string}`
- GET status response: `{state: "queued" | "rendering" | "ready" | "cancelled" | "error", stage: string, progress: number, elapsed_seconds: number, stream_url?: string, error?: string}`

- [ ] **Step 1: Write failing scheduler tests**

Cover concurrency cap, final-before-preview priority, superseding preview cancellation, owner isolation, queued cancellation, running cancellation, status progression, and stale completion rejection.

```python
def test_final_job_runs_before_queued_preview():
    scheduler = RenderScheduler(max_workers=1)
    blocker = scheduler.submit(preview_attempt("a"), priority=20)
    scheduler.submit(preview_attempt("b"), priority=20)
    scheduler.submit(final_attempt("c"), priority=10)
    release(blocker)
    assert next_started_id() == "c"
```

- [ ] **Step 2: Run and confirm failure**

```powershell
pytest tests/test_render_scheduler.py -v
```

Expected: module/import failure.

- [ ] **Step 3: Implement immutable snapshots**

At request time normalize settings/hook text, resolve owned asset identities, load canonical cues, capture target dimensions and version constants, then compute the digest. Freeze/copy the snapshot; worker code cannot read mutable clip metadata except for guarded status commit.

- [ ] **Step 4: Implement bounded priority scheduler**

Use one process-wide priority queue and configured worker count. Final priority `10` is higher than preview priority `20`. Keep cancellation events per attempt. Both preview and final call `RenderScheduler.submit`; final no longer starts its own daemon thread or acquires `_GLOBAL_RENDER_LOCK`. Replace `_FFMPEG_PROCESS_LOCK` with the same configurable process-wide permit owned by the scheduler so the configured concurrency is real, while probes use a short separate semaphore or execute inside the worker permit. Retain per-clip CAS protection for final commit.

- [ ] **Step 5: Make preview start non-blocking**

`POST /api/clip/preview` returns queued state immediately. Add owner-scoped status and cancel methods/routes. Status state values are `queued`, `rendering`, `ready`, `cancelled`, `error`. Include stage/progress/elapsed and only include stream URL after atomic output completion.

- [ ] **Step 6: Prevent stale replacement**

Frontend and backend track the latest preview ID per owner/clip. Older completion remains retrievable only if retained but cannot become current. New preview cancels prior queued/running preview for that clip.

- [ ] **Step 7: Verify**

```powershell
pytest tests/test_render_scheduler.py tests/test_job_manager.py -k "preview or render_lifecycle or cancellation or stale" -v
python -m compileall render_scheduler.py job_manager.py server.py
```

Expected: POST returns before worker completion; final priority deterministic; cancellation stops worker; cross-user status returns not found.

---

### Task 7: Add Accurate Preview Progress, Cancellation, and Stale UI Protection

**Files:**
- Modify: `frontend/src/pages/Preview.tsx:15-154,184-200`
- Modify: `frontend/src/components/clip-editor/ClipEditorModal.tsx:16-33,84-123`
- Test: `frontend/src/pages/Preview.test.tsx`

**Interfaces:**
- Polls: `GET /api/clip/preview/status?clip_id&preview_id`
- Cancels: `POST /api/clip/preview/cancel {clip_id, preview_id}`
- Props: `previewMode`, `previewState`, `previewProgress`, `previewElapsed`, `previewStale`

- [ ] **Step 1: Write failing controller tests**

Create complete Vitest tests with mocked `apiPost`/`apiGet`: POST returns `{status: 'queued', preview_id: 'p2'}`; status progresses from `{state: 'rendering', stage: 'Menyusun video', progress: 0.5, elapsed_seconds: 2}` to `{state: 'ready', progress: 1, elapsed_seconds: 4, stream_url: '/preview-p2'}`; cancel returns `{status: 'ok'}`. Assert immediate queued state, polling cleanup on unmount, cancellation request body, modal close while rendering, stale state after setting change, and rejection of a late `p1` completion after `p2` is current.

- [ ] **Step 2: Replace blocking preview handler**

Start job, store returned ID, then poll every 1–1.5 seconds while active. Abort polling on unmount/clip change. Apply stream URL only when response ID equals current ID.

- [ ] **Step 3: Separate live and accurate modes**

Control edits switch to live mode and mark previous accurate output stale. “Render Preview Akurat” starts verification. Ready output switches video mode to accurate. Provide explicit “Kembali ke Live” action.

- [ ] **Step 4: Add progress and cancel UX**

Display stage, percentage, elapsed time, and “Batalkan Preview”. Cancellation does not discard settings or close editor. Allow modal close while preview continues/cancels safely.

- [ ] **Step 5: Verify**

```powershell
npm run test --prefix frontend
npm run lint --prefix frontend
npm run build --prefix frontend
```

Expected: out-of-order ready response never replaces latest preview; controls remain usable in live mode.

---

### Task 8: Harden Cache, Cleanup, Credit, and Media Delivery

**Files:**
- Modify: `job_manager.py:851-921,991-1023`
- Modify: `clipper_export.py:131-153,470-485`
- Modify: `server.py:622-667`
- Test: `tests/test_job_manager.py`
- Test: `tests/test_backend_security.py`

**Interfaces:**
- Produces deterministic digest over full immutable snapshot and renderer dependencies
- Retains at most 3 completed previews per clip; never deletes active output
- Credit renderer receives already resolved safe display text

- [ ] **Step 1: Write failing cache tests**

Prove digest changes for source/transcript/watermark stat changes, font hash, scene/cue versions, dimensions, FFmpeg key, hook text, and normalized settings. Prove identical snapshots hit cache without calling FFmpeg.

- [ ] **Step 2: Add versioned cache key**

Hash sorted JSON plus file identities. Use stable file size + nanosecond mtime + selected font SHA-256. Capture FFmpeg major/minor compatibility once at startup, not per request.

- [ ] **Step 3: Bound preview retention**

After successful output commit, remove completed preview artifacts beyond newest three under the clip lock. Ignore current/running IDs and tolerate missing files.

- [ ] **Step 4: Resolve credit before rendering**

Replace `{channel}` with channel name. If absent, remove unresolved token and normalize whitespace/punctuation. Reject enabled credit only when resulting text is empty. Browser and Pillow receive the same resolved text.

- [ ] **Step 5: Add immutable media caching**

Revision/digest URLs receive `Cache-Control: private, max-age=31536000, immutable`; non-versioned responses remain `no-store` or short-lived. Apply headers to both 200 and 206 responses.

- [ ] **Step 6: Verify**

```powershell
pytest tests/test_job_manager.py tests/test_backend_security.py -k "cache or preview or credit or range" -v
```

Expected: cache invalidates on every render dependency; fourth old preview is removed; Range response is cacheable and secure.

---

### Task 9: Add Visual Parity Fixtures and Reproducible Performance Gate

**Files:**
- Create: `tests/fixtures/preview/source-landscape.mp4`
- Create: `tests/fixtures/preview/transcript-words.json`
- Create: `tests/fixtures/preview/settings.json`
- Create: `tests/benchmark_preview.py`
- Modify: `tests/test_job_manager.py`
- Create: `frontend/src/components/clip-editor/LiveClipPreview.visual.test.tsx`

**Interfaces:**
- Benchmark CLI records JSON/Markdown measurements
- Fixture checksum and expected cue/layer geometry are stable
- Visual tests compare geometry/cue state exactly and pixels perceptually

- [ ] **Step 1: Preserve baseline and generate deterministic fixture**

Before Task 5 removes the old path, preserve its invocation as a benchmark-only callable in `tests/benchmark_preview.py` or capture the baseline executable/commit and command. Generate the fixture with:

```powershell
ffmpeg -y -f lavfi -i "testsrc2=size=1920x1080:rate=30:duration=60" -f lavfi -i "sine=frequency=440:sample_rate=48000:duration=60" -c:v libx264 -preset veryfast -crf 18 -pix_fmt yuv420p -c:a aac -b:a 128k -shortest "tests/fixtures/preview/source-landscape.mp4"
```

Store SHA-256, browser name/version, refresh rate, hardware, OS, and FFmpeg build in benchmark metadata. Use transcript words whose active windows hit selected capture timestamps.

- [ ] **Step 2: Add scene parity assertions**

Capture lossless frames from accurate-preview and final shared graphs before lossy encoding. Assert exact layer visibility, cue index, normalized bounding boxes, and color values. For decoded MP4 comparison, use an explicit perceptual threshold after common scaling rather than exact pixels.

- [ ] **Step 3: Add live-preview geometry assertions**

At the same timestamps, assert DOM layer centers/sizes within declared tolerances and exact configured CSS colors. Do not demand browser/libass glyph-pixel identity.

- [ ] **Step 4: Implement benchmark protocol**

Record hardware, OS, FFmpeg build, encoder, fixture checksum, settings, exact baseline/new commands, browser/version/refresh rate, and idle-load confirmation. Run one warm-up and five uncached old/new trials. Report medians and pass only when new median is at most 60% of baseline. Record encode count and verify it equals one. Add an HTTP timing test requiring preview POST acknowledgement within 500ms, a cancellation test requiring `cancelled` within 3 seconds, and Vault mocks proving zero editor-load/media Range calls.

- [ ] **Step 5: Measure live paint latency**

Use `requestAnimationFrame` instrumentation around setting state updates. Run repeated updates and require p95 first-painted-layer change at or below 50ms on the documented browser/target.

- [ ] **Step 6: Run complete verification**

```powershell
pytest tests -q
npm run test --prefix frontend
npm run lint --prefix frontend
npm run build --prefix frontend
python tests/benchmark_preview.py --trials 5
```

Expected: all tests pass; one encode; benchmark median ≤60% baseline; live p95 ≤50ms; cached render invokes no FFmpeg.

---

## Final Manual Acceptance Checklist

- [ ] Hook on/off appears immediately without clicking render.
- [ ] Subtitle on/off appears immediately when timed content exists.
- [ ] Spoken active word uses configured blue highlight for word-timestamp clips.
- [ ] Segment-only clips explicitly show static subtitle limitation.
- [ ] Captions-off legacy clips can use retained valid transcripts; unavailable clips show a clear reason.
- [ ] Watermark, credit, positions, opacity, font, size, and outline update live.
- [ ] Blur-on landscape shows blurred/darkened fill; blur-off shows black fill.
- [ ] Portrait input disables blur with renderer-accurate explanation.
- [ ] Accurate preview reports progress, can be cancelled, and never freezes editor navigation.
- [ ] Accurate preview and final preserve identical hook wrapping, subtitle cue, positions, and layer visibility.
- [ ] Final rendering still atomically preserves the prior master on failure.
- [ ] No absolute server path or cross-user media is exposed.
- [ ] Editor/media traffic performs no Vault/API request.
