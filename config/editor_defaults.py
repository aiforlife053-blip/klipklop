from copy import deepcopy

SCENE_BUILDER_VERSION = "scene-v5"
CUE_BUILDER_VERSION = "cue-v3"
PREVIEW_PROFILE_VERSION = "preview-v4"
VISUAL_PRESET_VERSION = "visual-v3"

# Fixed V3 visual contract — not overridable by client payload.
V3_OUTPUT_WIDTH = 1080
V3_OUTPUT_HEIGHT = 1920
HOOK_MAX_WORDS = 7
HOOK_MAX_LINES = 4
HOOK_PAUSE_SECONDS = 0.3
HOOK_SLIDE_SECONDS = 0.3
SUBTITLE_WORD_MIN = 2
SUBTITLE_WORD_MAX = 2
TARGET_CLIP_MIN = 50
TARGET_CLIP_MAX = 70
HARD_CLIP_MIN = 40
HARD_CLIP_MAX = 70

EDITOR_DEFAULTS = {
    "watermark": {
        "enabled": False,
        "image_path": "",
        "position_x": 0.85,
        "position_y": 0.05,
        "opacity": 0.8,
        "scale": 0.15,
    },
    "credit_watermark": {
        "enabled": True,
        "text": "sc: @{channel}",
        "color": "#FFFFFF",
        "size": 0.03935185185185185,
        "letter_spacing": 0.000462962962962963,
        "opacity": 0.45,
        "outline_thickness": 0.0,
        "position_x": 0.82,
        "position_y": 0.06,
    },
    "hook_style": {
        "enabled": True,
        "font_size": 0.070,
        "letter_spacing": -0.001388888888888889,
        "font_family": "Poppins",
        "font_weight": 700,
        "text_color": "#FFFFFF",
        "outline_color": "#000000",
        "outline_thickness": 2.5185185185185186,
        "duration": 5.0,
        "position_x": 0.5,
        "position_y": 0.62,
        "max_words": HOOK_MAX_WORDS,
        "max_lines": HOOK_MAX_LINES,
        "pause_seconds": HOOK_PAUSE_SECONDS,
        "slide_seconds": HOOK_SLIDE_SECONDS,
    },
    "subtitle": {
        "enabled": True,
        "color": "#2CCDE7",
        "text_color": "#FFFFFF",
        # ~108px @1080 (was ~98px at 0.062)
        "size": 0.068,
        "position_x": 0.5,
        "position_y": 0.78,
        # Sentence case / as-transcribed — not ALL CAPS
        "text_transform": "none",
        "letter_spacing": 0.001388888888888889,
        "bg_color": "#000000",
        "bg_opacity": 0.0,
        "font_family": "Poppins",
        "font_weight": 700,
        "outline_color": "#000000",
        # ~6px stroke @1080 (was ~3px at 1.0)
        "outline_thickness": 2.0,
        "shadow": 0,
        "word_min": SUBTITLE_WORD_MIN,
        "word_max": SUBTITLE_WORD_MAX,
    },
    "blur_background": {"enabled": False, "scale": 1.6, "zoom": 1.08, "strength": 10},
    "video_layout": {"mode": "normal"},
}


def editor_defaults():
    return deepcopy(EDITOR_DEFAULTS)


def v3_locked_render_settings(base=None):
    """Server-side fixed visual preset. Client payload cannot override style fields."""
    settings = editor_defaults()
    if isinstance(base, dict):
        layout = base.get("video_layout") if isinstance(base.get("video_layout"), dict) else {}
        mode = str(layout.get("mode") or settings["video_layout"]["mode"])
        if mode in {"normal", "gaming", "vertical_full", "split_middle"}:
            settings["video_layout"] = {"mode": mode}
            for key in ("facecam_x", "facecam_y", "facecam_width", "facecam_height", "facecam_confidence"):
                if key in layout:
                    settings["video_layout"][key] = layout[key]
    # Force visual contract
    settings["watermark"]["enabled"] = False
    settings["blur_background"]["enabled"] = False
    settings["credit_watermark"]["enabled"] = True
    settings["credit_watermark"]["text"] = "sc: @{channel}"
    settings["hook_style"]["enabled"] = True
    settings["hook_style"]["font_family"] = "Poppins"
    settings["subtitle"]["enabled"] = True
    settings["subtitle"]["text_transform"] = "none"
    settings["subtitle"]["letter_spacing"] = EDITOR_DEFAULTS["subtitle"]["letter_spacing"]
    settings["subtitle"]["color"] = "#2CCDE7"
    settings["subtitle"]["text_color"] = "#FFFFFF"
    settings["subtitle"]["outline_color"] = "#000000"
    settings["subtitle"]["outline_thickness"] = EDITOR_DEFAULTS["subtitle"]["outline_thickness"]
    settings["subtitle"]["shadow"] = 0
    settings["subtitle"]["font_family"] = "Poppins"
    settings["subtitle"]["font_weight"] = 700
    settings["subtitle"]["size"] = EDITOR_DEFAULTS["subtitle"]["size"]
    settings["subtitle"]["word_min"] = SUBTITLE_WORD_MIN
    settings["subtitle"]["word_max"] = SUBTITLE_WORD_MAX
    settings["subtitle"]["position_x"] = 0.5
    settings["credit_watermark"]["size"] = EDITOR_DEFAULTS["credit_watermark"]["size"]
    settings["credit_watermark"]["opacity"] = 0.45
    settings["hook_style"]["max_words"] = HOOK_MAX_WORDS
    settings["hook_style"]["max_lines"] = HOOK_MAX_LINES
    settings["hook_style"]["letter_spacing"] = EDITOR_DEFAULTS["hook_style"]["letter_spacing"]
    mode = settings["video_layout"].get("mode")
    settings["hook_style"]["font_size"] = 0.070
    # Same subtitle size for vertical_full + split_middle (locked preset).
    settings["subtitle"]["size"] = EDITOR_DEFAULTS["subtitle"]["size"]
    if mode in {"split_middle"}:
        settings["subtitle"]["position_y"] = 0.5
    else:
        settings["subtitle"]["position_y"] = 0.78
    return settings
