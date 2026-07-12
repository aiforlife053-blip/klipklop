# Blur Portrait Optimization Plan

**Goal:** Speed up landscape blur portrait conversion without losing visual quality.

**Problem:** `gblur=sigma=113:steps=2` on720×1280 full resolution is the bottleneck. Gaussian blur at high sigma is O(n × r²) per pixel.

## Optimizations

### 1. Replace `gblur` with `boxblur`

- `boxblur` is3-5x faster than `gblur` at large kernel sizes.
- At sigma >30, visual difference between gaussian and box blur is imperceptible on a blurred background.
- Change: `clipper_portrait.py:512`

```python
# Before
blur_filter = f"gblur=sigma={blur_sigma:.3f}:steps=2,"

# After
blur_radius = int(round(blur_sigma * 0.75))
blur_filter = f"boxblur={blur_radius}:{blur_radius},"
```

### 2. Blur at reduced resolution then upscale

Blur destroys detail anyway — no quality loss from blurring a smaller image.

- Scale background to320px wide (instead of784px at720p zoom1.08)
- Apply blur at small resolution
- Scale back up to target resolution

Change in `_preview_blur_filter`:

```python
# Before
f"[0:v]scale={bg_width}:{bg_height}:force_original_aspect_ratio=increase,"
f"{blur_filter}colorchannelmixer=rr=0.6:gg=0.6:bb=0.6,"
f"crop={width}:{height}[bg];"

# After — downscale → blur → upscale
blur_w = 320
blur_h = int(round(blur_w * height / width))
f"[0:v]scale={blur_w}:{blur_h}:force_original_aspect_ratio=increase,"
f"{blur_filter}scale={bg_width}:{bg_height},"
f"colorchannelmixer=rr=0.6:gg=0.6:bb=0.6,"
f"crop={width}:{height}[bg];"
```

### 3. Update test

`tests/test_job_manager.py:811` asserts `gblur=sigma=6.353:steps=2`. Update to match new `boxblur` output format.

## Files Modified

- `clipper_portrait.py:502-520` — `_preview_blur_filter`
- `tests/test_job_manager.py:806-815` — `test_blur_filter_matches_preview_geometry`

## Verification

```powershell
pytest tests/test_job_manager.py::test_blur_filter_matches_preview_geometry -v
pytest tests/test_job_manager.py -q
```

Visual: blur background should look identical — soft, dimmed, centered foreground.
