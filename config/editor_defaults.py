from copy import deepcopy

SCENE_BUILDER_VERSION = "scene-v4"
CUE_BUILDER_VERSION = "cue-v2"
PREVIEW_PROFILE_VERSION = "preview-v3"

EDITOR_DEFAULTS = {
    "watermark": {"enabled": False, "image_path": "", "position_x": 0.85, "position_y": 0.05, "opacity": 0.8, "scale": 0.15},
    "credit_watermark": {"enabled": False, "text": "sc : {channel}", "color": "#FFFFFF", "size": 0.032, "opacity": 0.55, "position_x": 0.06, "position_y": 0.23},
    "hook_style": {"enabled": False, "font_size": 0.054, "font_family": "Plus Jakarta Sans", "font_weight": 800, "text_color": "#FFD700", "outline_color": "#000000", "outline_thickness": 1.5, "duration": 5.0, "position_x": 0.5, "position_y": 0.2},
    "subtitle": {"enabled": True, "color": "#00BFFF", "text_color": "#FFFFFF", "size": 0.04, "position_x": 0.5, "position_y": 0.85, "text_transform": "none", "bg_color": "#000000", "bg_opacity": 0.0, "font_family": "Plus Jakarta Sans", "font_weight": 800, "outline_color": "#000000", "outline_thickness": 1.0},
    "blur_background": {"enabled": True, "scale": 1.6, "zoom": 1.08, "strength": 10},
    "video_layout": {"mode": "normal"},
}


def editor_defaults():
    return deepcopy(EDITOR_DEFAULTS)
