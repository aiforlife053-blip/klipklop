"""V3 layout mode contracts: canonical modes, geometry, orientation validation,
state machine, and filtergraph builders for each mode."""

import math
import os

from gaming_layout import (
    GamingLayoutError,
    build_gaming_filtergraph as _build_gaming_filtergraph,
    validate_roi,
)

# --- Canonical modes ---

V3_MODES = ("vertical_full", "gaming", "split_middle")
V3_OUTPUT_WIDTH = 1080
V3_OUTPUT_HEIGHT = 1920
V3_OUTPUT_GEOMETRIES = {
    "480": (540, 960),
    "720": (720, 1280),
    "1080": (V3_OUTPUT_WIDTH, V3_OUTPUT_HEIGHT),
    "1440": (1440, 2560),
}


# Modes that only accept landscape sources
LANDSCAPE_ONLY_MODES = frozenset({"gaming", "split_middle"})

# --- State machine (plan.md) ---
# queued -> analyzing -> downloading -> detecting_layout -> rendering
#   -> ready_to_schedule -> scheduled -> uploading -> uploaded
# Special: detecting_layout -> needs_facecam -> rendering
#          rendering -> render_error -> rendering
#          uploading -> upload_error -> scheduled
#          any active -> cancelled

V3_STATUSES = frozenset({
    "queued", "analyzing", "downloading", "detecting_layout",
    "needs_facecam", "rendering", "render_error",
    "ready_to_schedule", "scheduled", "uploading", "upload_error",
    "uploaded", "cancelled", "error",
})

_V3_TRANSITIONS = {
    "queued":              frozenset({"analyzing", "cancelled", "error"}),
    "analyzing":           frozenset({"downloading", "cancelled", "error"}),
    "downloading":         frozenset({"detecting_layout", "cancelled", "error"}),
    "detecting_layout":    frozenset({"rendering", "needs_facecam", "cancelled", "error"}),
    "needs_facecam":       frozenset({"rendering", "cancelled", "error"}),
    "rendering":           frozenset({"ready_to_schedule", "render_error", "cancelled", "error"}),
    "render_error":        frozenset({"rendering", "cancelled"}),
    "ready_to_schedule":   frozenset({"scheduled", "cancelled"}),
    "scheduled":           frozenset({"uploading", "upload_error", "cancelled", "ready_to_schedule"}),
    "uploading":           frozenset({"uploaded", "upload_error", "cancelled"}),
    "upload_error":        frozenset({"scheduled", "cancelled"}),
    "uploaded":            frozenset({"cancelled"}),
    "cancelled":           frozenset(),
    "error":               frozenset({"queued"}),  # allow retry from error
}


class LayoutModeError(ValueError):
    """Raised when mode/orientation/geometry validation fails."""


def validate_mode(mode):
    """Return canonical mode string or raise LayoutModeError."""
    if not isinstance(mode, str):
        raise LayoutModeError("Mode layout wajib dipilih.")
    normalized = mode.strip().lower()
    if normalized not in V3_MODES:
        raise LayoutModeError(
            f"Mode tidak valid: '{mode}'. Pilih: {', '.join(V3_MODES)}."
        )
    return normalized


def validate_orientation(mode, is_landscape):
    """Raise LayoutModeError if portrait source used with landscape-only mode."""
    canonical = validate_mode(mode)
    if canonical in LANDSCAPE_ONLY_MODES and not is_landscape:
        raise LayoutModeError(
            f"Mode {canonical} hanya mendukung video landscape (horizontal). "
            "Gunakan mode vertical_full untuk video portrait."
        )
    return canonical


def output_geometry(quality=None):
    """Return (width, height) for final 9:16 canvas by quality.

    quality None/empty keeps legacy 1080 default for old callers.
    """
    if quality is None or str(quality).strip() == "":
        return (V3_OUTPUT_WIDTH, V3_OUTPUT_HEIGHT)
    key = str(quality).strip()
    if key not in V3_OUTPUT_GEOMETRIES:
        raise LayoutModeError(
            f"Quality tidak valid: '{quality}'. Pilih: {', '.join(V3_OUTPUT_GEOMETRIES)}."
        )
    return V3_OUTPUT_GEOMETRIES[key]


def is_legal_transition(from_status, to_status):
    """Check if a state transition is legal per V3 state machine."""
    if from_status not in V3_STATUSES or to_status not in V3_STATUSES:
        return False
    return to_status in _V3_TRANSITIONS.get(from_status, frozenset())


def validate_transition(from_status, to_status):
    """Raise LayoutModeError if transition is illegal."""
    if not is_legal_transition(from_status, to_status):
        raise LayoutModeError(
            f"Transisi status ilegal: {from_status} -> {to_status}"
        )
    return to_status


# --- Filtergraph builders ---

def build_vertical_full_filtergraph(source_w, source_h, out_w=None, out_h=None):
    """Vertical Full: crop center to 9:16 and scale to output.
    Accepts landscape and portrait sources."""
    out_w = out_w or V3_OUTPUT_WIDTH
    out_h = out_h or V3_OUTPUT_HEIGHT

    if source_w >= source_h:
        # Landscape: crop center to 9:16
        crop_w = min(source_w, int(source_h * 9 / 16))
        crop_w -= crop_w % 2
        crop_x = (source_w - crop_w) // 2
        crop_x -= crop_x % 2
        filters = [
            f"[0:v]setpts=PTS-STARTPTS,"
            f"crop={crop_w}:{source_h}:{crop_x}:0,"
            f"scale={out_w}:{out_h}:flags=lanczos,setsar=1[v0]",
        ]
    else:
        # Portrait: just scale
        filters = [
            f"[0:v]setpts=PTS-STARTPTS,"
            f"scale={out_w}:{out_h}:flags=lanczos,setsar=1[v0]",
        ]
    return filters, "v0"


def build_split_middle_filtergraph(source_w, source_h, out_w=None, out_h=None, rois=None):
    """Split Middle: person-aware ROIs -> top/bottom; blind halves only fallback."""
    out_w = out_w or V3_OUTPUT_WIDTH
    out_h = out_h or V3_OUTPUT_HEIGHT

    if source_w <= source_h:
        raise LayoutModeError(
            "Mode split_middle hanya mendukung video landscape (horizontal)."
        )

    panel_h = out_h // 2
    panel_h -= panel_h % 2

    def crop_from_roi(value, fallback_x):
        if isinstance(value, dict):
            try:
                x = max(0.0, min(0.95, float(value["x"])))
                y = max(0.0, min(0.95, float(value["y"])))
                w = max(0.05, min(1.0 - x, float(value["width"])))
                h = max(0.05, min(1.0 - y, float(value["height"])))
                px = int(x * source_w) // 2 * 2
                py = int(y * source_h) // 2 * 2
                pw = max(2, int(w * source_w) // 2 * 2)
                ph = max(2, int(h * source_h) // 2 * 2)
                return pw, ph, px, py
            except (KeyError, TypeError, ValueError):
                pass
        half_w = source_w // 2
        half_w -= half_w % 2
        return half_w, source_h, fallback_x, 0

    roi_map = rois if isinstance(rois, dict) else {}
    top_crop = crop_from_roi(roi_map.get("top"), 0)
    half_w = source_w // 2
    half_w -= half_w % 2
    bottom_crop = crop_from_roi(roi_map.get("bottom"), half_w)
    tw, th, tx, ty = top_crop
    bw, bh, bx, by = bottom_crop
    filters = [
        "[0:v]setpts=PTS-STARTPTS,split=2[top_src][bottom_src]",
        f"[top_src]crop={tw}:{th}:{tx}:{ty},scale={out_w}:{panel_h}:flags=lanczos,setsar=1[top]",
        f"[bottom_src]crop={bw}:{bh}:{bx}:{by},scale={out_w}:{panel_h}:flags=lanczos,setsar=1[bottom]",
        "[top][bottom]vstack=inputs=2,setsar=1[v0]",
    ]
    return filters, "v0"


def build_gaming_filtergraph(source_w, source_h, roi, out_w=None, out_h=None):
    """Gaming: facecam 1/3 top, gameplay 2/3 bottom. Delegates to gaming_layout.
    Normalizes return to (filters, label) for consistent router contract."""
    out_w = out_w or V3_OUTPUT_WIDTH
    out_h = out_h or V3_OUTPUT_HEIGHT
    filters, _info = _build_gaming_filtergraph(source_w, source_h, out_w, out_h, roi)
    return filters, "v0"


def validate_facecam_overlap(roi, source_w, source_h):
    """Check that facecam ROI doesn't overlap the center gameplay area.
    Gameplay center crop is 27/32 of source width, centered.
    Returns True if OK (no overlap), False if overlap detected."""
    valid = validate_roi(roi)
    if not valid:
        raise GamingLayoutError("ROI facecam tidak valid.")

    if source_w <= source_h:
        raise GamingLayoutError("Mode gaming hanya mendukung source landscape.")

    crop_width = min(source_w, int(source_h * 27 / 32))
    crop_width -= crop_width % 2
    crop_x = (source_w - crop_width) // 2

    face_left = valid["x"] * source_w
    face_right = (valid["x"] + valid["width"]) * source_w

    # Overlap if facecam extends into gameplay crop area
    if face_right > crop_x and face_left < crop_x + crop_width:
        return False
    return True


def build_filtergraph(mode, source_w, source_h, roi=None, out_w=None, out_h=None):
    """Central router: pick filtergraph builder based on mode.
    Returns (filters, label) tuple."""
    canonical = validate_mode(mode)

    if canonical == "vertical_full":
        return build_vertical_full_filtergraph(source_w, source_h, out_w, out_h)
    elif canonical == "split_middle":
        rois = None
        if isinstance(roi, dict) and ("top" in roi or "bottom" in roi):
            rois = roi
        return build_split_middle_filtergraph(source_w, source_h, out_w, out_h, rois=rois)
    elif canonical == "gaming":
        if roi is None:
            raise GamingLayoutError("Mode gaming memerlukan ROI facecam.")
        return build_gaming_filtergraph(source_w, source_h, roi, out_w, out_h)

    raise LayoutModeError(f"Mode tidak dikenal: {canonical}")


def probe_orientation(source_path):
    """Probe video file and return (width, height, is_landscape).
    Uses ffprobe. Returns (0, 0, True) on failure."""
    import subprocess
    import json as _json
    from pathlib import Path
    from utils.helpers import get_ffmpeg_path

    probe = Path(get_ffmpeg_path()).with_name(
        "ffprobe.exe" if os.name == "nt" else "ffprobe"
    )
    try:
        result = subprocess.run(
            [str(probe), "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "json", str(source_path)],
            capture_output=True, text=True, timeout=15,
        )
        stream = (_json.loads(result.stdout).get("streams") or [{}])[0]
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        if width <= 0 or height <= 0:
            return 0, 0, True
        return width, height, width > height
    except Exception:
        return 0, 0, True
