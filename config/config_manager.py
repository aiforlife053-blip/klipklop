"""
Configuration manager for YT Short Clipper
"""

import json
import uuid
from pathlib import Path


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
                backup = self.config_file.with_suffix(".invalid.json")
                self.config_file.replace(backup)
                return self.load()
            dirty = False
            if "api_key" in config and "ai_providers" not in config:
                config = self._migrate_to_multi_provider(config)
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
                "subtitle_style": {"font": "Arial Black", "size": 65, "bottom_margin": 400},
                "mediapipe_settings": {
                    "lip_activity_threshold": 0.15,
                    "switch_threshold": 0.3,
                    "min_shot_duration": 90,
                    "center_weight": 0.3
                },
                "repliz": {"access_key": "", "secret_key": ""},
                "gpu_acceleration": {"enabled": False},
                "watermark": {
                    "enabled": False,
                    "image_path": "",
                    "position_x": 0.85,
                    "position_y": 0.05,
                    "opacity": 0.8,
                    "scale": 0.15
                },
                "ai_providers": self._get_default_ai_providers(),
            }
            for key, value in defaults.items():
                if key not in config:
                    config[key] = value
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
            "face_tracking_mode": "center",
            "video_quality": "720",
            "landscape_blur": False,
            "subtitle_style": {"font": "Arial Black", "size": 65, "bottom_margin": 400},
            "mediapipe_settings": {
                "lip_activity_threshold": 0.15,
                "switch_threshold": 0.3,
                "min_shot_duration": 90,
                "center_weight": 0.3
            },
            "repliz": {
                "access_key": "",
                "secret_key": ""
            },
            "gpu_acceleration": {
                "enabled": False
            }
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
                "base_url": "https://api.openai.com/v1",
                "api_key": "",
                "model": "whisper-1"
            },
            "hook_maker": {
                "base_url": "https://api.openai.com/v1",
                "api_key": "",
                "model": "tts-1"
            },
            "youtube_title_maker": {
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "api_key": "",
                "model": "gemini-2.5-flash"
            }
        }
    
    def _migrate_to_multi_provider(self, old_config):
        """Migrate old single-provider config to new multi-provider structure"""
        api_key = old_config.get("api_key", "")
        base_url = old_config.get("base_url", "https://api.openai.com/v1")
        model = old_config.get("model", "gpt-4.1")
        tts_model = old_config.get("tts_model", "tts-1")
        
        old_config["ai_providers"] = {
            "highlight_finder": {
                "base_url": base_url,
                "api_key": api_key,
                "model": model
            },
            "caption_maker": {
                "base_url": base_url,
                "api_key": api_key,
                "model": "whisper-1"
            },
            "hook_maker": {
                "base_url": base_url,
                "api_key": api_key,
                "model": tts_model
            },
            "youtube_title_maker": {
                "base_url": base_url,
                "api_key": api_key,
                "model": model
            }
        }
        
        return old_config

    def save(self):
        """Save configuration to file"""
        self.save_config(self.config)
    
    def save_config(self, config):
        """Save configuration dict to file"""
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    
    def get(self, key, default=None):
        """Get configuration value"""
        return self.config.get(key, default)
    
    def set(self, key, value):
        """Set configuration value and save"""
        self.config[key] = value
        self.save()
