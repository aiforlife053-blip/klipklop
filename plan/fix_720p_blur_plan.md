# Rencana Perbaikan Video Blur & Penambahan Opsi Resolusi Tinggi (1080p, 1440p/2K, 2160p/4K)

## 1. Analisis & Pilihan Solusi (Option A)
Untuk mengatasi blur pada video 720p saat diubah ke format portrait (9:16), kita menerapkan **Option A (Dynamic Sizing)**:
- Saat user memilih `720p`, output video dipotong dan di-resize ke target dimensi **`720x1280`** (bukan di-upscale paksa ke `1080x1920`).
- Saat user memilih `1080p`, output video dipotong dan di-resize ke target dimensi **`1080x1920`**.
- Saat user memilih `1440p` (2K), output video dipotong dan di-resize ke target dimensi **`1440x2560`**.
- Saat user memilih `2160p` (4K), output video dipotong dan di-resize ke target dimensi **`2160x3840`**.

Hal ini mencegah degradasi kualitas pixel (blur akibat forced upscaling) dan mempercepat render saat user memilih kualitas di bawah 1080p.

---

## 2. Perbaikan Dynamic Target Portrait (`clipper_portrait.py`)
1. Tambahkan helper `_get_target_portrait_dims(self, orig_w: int, orig_h: int) -> tuple[int, int]` di `PortraitMixin`.
2. Ganti hardcode `out_w, out_h = 1080, 1920` di method:
   - `convert_to_portrait_opencv`
   - `convert_to_portrait_mediapipe`
   - `convert_to_portrait_opencv_with_progress`
   - `convert_to_portrait_mediapipe_with_progress`

---

## 3. Penambahan Dukungan Resolusi 1440p (2K) dan 2160p (4K)

### A. Backend Core (`clipper_core.py`)
Update peta pemetaan resolusi di `__init__`:
```python
resolutions = {
    "16:9": {
        "480": "854:480",
        "720": "1280:720",
        "1080": "1920:1080",
        "1440": "2560:1440",
        "2160": "3840:2160"
    },
    "9:16": {
        "480": "540:960",
        "720": "720:1280",
        "1080": "1080:1920",
        "1440": "1440:2560",
        "2160": "2160:3840"
    }
}
```

### B. Downloader Selector (`clipper_download.py`)
Update method `_format_selector` di `DownloadMixin`:
```python
max_height = {"480": 480, "720": 720, "1080": 1080, "1440": 1440, "2160": 2160}.get(quality, 720)
```

### C. Job Manager Validation (`job_manager.py`)
Update daftar resolusi valid dari `{"480", "720", "1080"}` menjadi:
```python
if video_quality not in {"480", "720", "1080", "1440", "2160"}:
    video_quality = "720"
```
Dan update `resolution_map` di dalam `_update_run_status`.

### D. Frontend Workspace UI (`Dashboard.tsx`)
Tambahkan opsi baru di dropdown Quality:
```tsx
<option value="480">480p</option>
<option value="720">720p</option>
<option value="1080">1080p (FHD)</option>
<option value="1440">1440p (2K)</option>
<option value="2160">2160p (4K)</option>
```
