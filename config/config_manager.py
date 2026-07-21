"""
Configuration manager for YT Short Clipper
"""

import json
import os
import tempfile
import uuid
from pathlib import Path

from config.editor_defaults import editor_defaults


class ConfigManager:
    """Manages application configuration"""
    
    def __init__(self, config_file: Path, output_dir: Path):
        self.config_file = config_file
        self.output_dir = output_dir
        self.config = self.load()
    
    def load(self):
        """Load configuration from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except json.JSONDecodeError:
                from datetime import datetime as _dt
                backup = self.config_file.with_name(f"{self.config_file.stem}.invalid.{_dt.now().strftime('%Y%m%d%H%M%S')}.json")
                self.config_file.replace(backup)
                return self.load()
            dirty = False
            if "api_key" in config and "ai_providers" not in config:
                config = self._migrate_to_multi_provider(config)
                dirty = True
            if "ai_providers" in config:
                default_providers = self._get_default_ai_providers()
                for provider_name, provider_data in default_providers.items():
                    provider = config["ai_providers"].setdefault(provider_name, {})
                    for key, value in provider_data.items():
                        if key not in provider:
                            provider[key] = value
                            dirty = True
            if "system_prompt" not in config:
                from clipper_core import AutoClipperCore
                config["system_prompt"] = AutoClipperCore.get_default_prompt()
                dirty = True
            defaults = {
                "temperature": 1.0,
                "tts_model": "tts-1",
                "installation_id": str(uuid.uuid4()),
                "face_tracking_mode": "center",
                "video_quality": "720",
                "landscape_blur": False,
                "subtitle_style": {"font": "Plus Jakarta Sans", "size": 58, "bottom_margin": 360},
            "subtitle": {"enabled": True, "color": "#00BFFF", "text_color": "#FFFFFF", "size": 0.04, "position_x": 0.5, "position_y": 0.85, "text_transform": "none", "bg_color": "#000000", "bg_opacity": 0.0, "font_family": "Plus Jakarta Sans", "font_weight": 800, "outline_color": "#000000", "outline_thickness": 1.0},

                "subtitle_position": "auto",
                "gpu_acceleration": {"enabled": False},
                "watermark": {
                    "enabled": False,
                    "image_path": "",
                    "position_x": 0.85,
                    "position_y": 0.05,
                    "opacity": 0.8,
                    "scale": 0.15
                },
                "credit_watermark": {"enabled": False, "text": "sc : {channel}", "color": "#FFFFFF", "size": 0.032, "opacity": 0.55, "position_x": 0.06, "position_y": 0.23},
                "hook_style": {"enabled": False, "font_size": 0.054, "font_family": "Plus Jakarta Sans", "font_weight": 800, "text_color": "#FFD700", "outline_color": "#000000", "outline_thickness": 1.5, "duration": 5.0, "position_x": 0.5, "position_y": 0.2},
            "blur_background": {"enabled": True, "scale": 1.6, "zoom": 1.08, "strength": 10},

                "ai_providers": self._get_default_ai_providers(),
            }
            for key, value in defaults.items():
                if key not in config:
                    config[key] = value
                    dirty = True
            hook_maker = config.setdefault("ai_providers", {}).setdefault("hook_maker", {})
            hook_defaults = {"base_url": "https://generativelanguage.googleapis.com/v1beta", "model": "gemini-3.1-flash-tts-preview", "voice": "Charon"}
            for key, value in hook_defaults.items():
                if not hook_maker.get(key) or hook_maker.get(key) in {"id-ID-ArdiNeural", "tts-1"}:
                    hook_maker[key] = value
                    dirty = True
            canonical_editor_defaults = editor_defaults()
            for section, section_defaults in canonical_editor_defaults.items():
                current_section = config.setdefault(section, {})
                for key, value in section_defaults.items():
                    if key not in current_section:
                        current_section[key] = value
                        dirty = True
            video_layout = config.setdefault("video_layout", {})
            mode = video_layout.get("mode") if video_layout.get("mode") in {"normal", "gaming"} else "normal"
            if video_layout != {"mode": mode}:
                config["video_layout"] = {"mode": mode}
                dirty = True
            if not config.get("_natural_text_defaults_migrated"):
                if config.setdefault("subtitle", {}).get("text_transform") == "uppercase":
                    config["subtitle"]["text_transform"] = "none"
                config["_natural_text_defaults_migrated"] = True
                dirty = True
            if not config.get("_preview_defaults_v2_migrated"):
                config.setdefault("subtitle", {})["enabled"] = True
                config.setdefault("blur_background", {}).update({"enabled": True, "scale": 1.6, "strength": 10})
                config["_preview_defaults_v2_migrated"] = True
                dirty = True
            if not config.get("_subtitle_default_enabled_migrated"):
                config.setdefault("subtitle", {})["enabled"] = True
                config["_subtitle_default_enabled_migrated"] = True
                dirty = True
            config["landscape_blur"] = bool(config.get("blur_background", {}).get("enabled", False))
            if not config.get("_blur_default_migrated"):
                config["_blur_default_migrated"] = True
                dirty = True
            if not config.get("_text_style_controls_migrated"):
                config["_text_style_controls_migrated"] = True
                dirty = True
            for obsolete_key in ("subtitle_engine", "local_whisper", "mediapipe_settings"):
                if obsolete_key in config:
                    config.pop(obsolete_key)
                    dirty = True
            if config.get("face_tracking_mode") == "mediapipe":
                config["face_tracking_mode"] = "center"
                dirty = True
            caption_maker = config.get("ai_providers", {}).get("caption_maker", {})
            if (caption_maker.get("api_key") == "" and
                caption_maker.get("base_url") == "https://api.openai.com/v1" and
                caption_maker.get("model") == "whisper-1"):
                caption_maker["base_url"] = "https://api.groq.com/openai/v1"
                caption_maker["model"] = "whisper-large-v3-turbo"
                dirty = True
            if dirty:
                self.save_config(config)
            return config
        
        # Default config with system prompt
        from clipper_core import AutoClipperCore
        config = {
            "api_key": "",  # Kept for backward compatibility
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",  # Kept for backward compatibility
            "model": "gemini-2.5-flash",  # Kept for backward compatibility
            "tts_model": "tts-1",  # Kept for backward compatibility
            "temperature": 1.0,
            "_text_style_controls_migrated": True,
            "output_dir": str(self.output_dir),
            "system_prompt": AutoClipperCore.get_default_prompt(),
            "installation_id": str(uuid.uuid4()),
            "ai_providers": self._get_default_ai_providers(),
            "watermark": {
                "enabled": False,
                "image_path": "",
                "position_x": 0.85,
                "position_y": 0.05,
                "opacity": 0.8,
                "scale": 0.15
            },
            "credit_watermark": {"enabled": False, "text": "sc : {channel}", "color": "#FFFFFF", "size": 0.032, "opacity": 0.55, "position_x": 0.06, "position_y": 0.23},
            "hook_style": {"enabled": False, "font_size": 0.054, "font_family": "Plus Jakarta Sans", "font_weight": 800, "text_color": "#FFD700", "outline_color": "#000000", "outline_thickness": 1.5, "duration": 5.0, "position_x": 0.5, "position_y": 0.2},
            "blur_background": {"enabled": False, "zoom": 1.08, "strength": 30},
            "face_tracking_mode": "center",
            "video_quality": "720",
            "landscape_blur": False,
            "subtitle_style": {"font": "Plus Jakarta Sans", "size": 58, "bottom_margin": 360},
            "subtitle": {"enabled": True, "color": "#00BFFF", "text_color": "#FFFFFF", "size": 0.04, "position_x": 0.5, "position_y": 0.85, "text_transform": "none", "bg_color": "#000000", "bg_opacity": 0.0, "font_family": "Plus Jakarta Sans", "font_weight": 800, "outline_color": "#000000", "outline_thickness": 1.0},
            "subtitle_position": "auto",
            "gpu_acceleration": {
                "enabled": False
            },
            "video_layout": {"mode": "normal"}
        }
        self.save_config(config)
        return config
    
    def _get_default_ai_providers(self):
        """Get default AI provider configuration"""
        return {
            "highlight_finder": {
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "api_key": "",
                "model": "gemini-2.5-flash"
            },
            "caption_maker": {
                "base_url": "https://api.groq.com/openai/v1",
                "api_key": "",
                "model": "whisper-large-v3-turbo"
            },
            "youtube_title_maker": {
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "api_key": "",
                "model": "gemini-2.5-flash"
            },
            "hook_maker": {
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
                "api_key": "",
                "model": "gemini-3.1-flash-tts-preview",
                "voice": "Charon"
            }
        }
    
    def _migrate_to_multi_provider(self, old_config):
        """Migrate old single-provider config to new multi-provider structure"""
        api_key = old_config.get("api_key", "")
        base_url = old_config.get("base_url", "https://api.openai.com/v1")
        model = old_config.get("model", "gpt-4.1")
        
        old_config["ai_providers"] = {
            "highlight_finder": {
                "base_url": base_url,
                "api_key": api_key,
                "model": model
            },
            "caption_maker": {
                "base_url": "https://api.groq.com/openai/v1",
                "api_key": "",
                "model": "whisper-large-v3-turbo"
            },
            "youtube_title_maker": {
                "base_url": base_url,
                "api_key": api_key,
                "model": model
            },
            "hook_maker": {
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
                "api_key": "",
                "model": "gemini-3.1-flash-tts-preview",
                "voice": "Charon"
            }
        }
        
        return old_config

    def save(self):
        """Save configuration to file"""
        self.save_config(self.config)
    
    def save_config(self, config):
        """Save configuration dict atomically."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.config_file.name}.", suffix=".tmp", dir=self.config_file.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_name, self.config_file)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
    
    def get(self, key, default=None):
        """Get configuration value"""
        return self.config.get(key, default)
    
    def set(self, key, value):
        """Set configuration value and save"""
        self.config[key] = value
        self.save()
