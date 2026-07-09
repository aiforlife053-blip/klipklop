import json
import re
import shutil
import sys
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clipper_core import AutoClipperCore
from config.config_manager import ConfigManager
from utils.helpers import get_app_dir, get_ffmpeg_path, get_ytdlp_path


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
GEMINI_MODEL = "gemini-2.5-flash"


class WebJobManager:
    def __init__(self, app_dir=None):
        self.app_dir = Path(app_dir) if app_dir else get_app_dir()
        self.output_dir = self.app_dir / "output"
        self.config_file = self.app_dir / "config.json"
        self.cookie_file = self.app_dir / "cookie.txt"
        self.core_cookie_file = self.app_dir / "cookies.txt"
        self.thread = None
        self._lock = threading.Lock()
        self._status = "idle"
        self._message = "Idle"
        self._progress = 0.0
        self._error = ""
        self._logs = []
        self._activities = []
        self._job_start_time = None
        self._job_timeout = 3600  # 1 hour default timeout
        self._cancel_requested = False

    def start(self, payload):
        if not isinstance(payload, dict):
            return {"status": "error", "message": "Invalid start payload"}
        url = str(payload.get("url", payload.get("youtube_url", ""))).strip()
        if not self._is_url(url):
            return {"status": "error", "message": "YouTube URL validation error: empty or invalid URL"}

        # Check for job timeout
        if self._job_start_time and (datetime.now() - self._job_start_time).total_seconds() > self._job_timeout:
            self._status = "idle"
            self._message = "Idle"
            self._job_start_time = None
            self._add_log("Previous job timed out")

        with self._lock:
            if self.thread and self.thread.is_alive():
                return {"status": "busy", "message": "Processing is already running"}
        if self._has_staged_outputs():
            return {"status": "busy", "message": "Simpan atau hapus klip di Beranda sebelum generate baru"}
            
        # Dynamically save settings from payload to ensure 100% sync with UI
        if "settings" in payload and isinstance(payload["settings"], dict):
            self.save_settings(payload["settings"])
            
        requested_clips = self._as_int(payload.get("num_clips"), 1)
        num_clips = requested_clips if requested_clips in {1, 3, 5} else 1
        add_captions = self._as_bool(payload.get("add_captions", True), True)
        add_hook = self._as_bool(payload.get("add_hook", True), True)
        subtitle_language = str(payload.get("subtitle_language", "id")).strip()[:10]
        instruction = str(payload.get("instruction", "")).strip()[:1000]
        landscape_blur = self._as_bool(payload.get("landscape_blur", self._config().config.get("landscape_blur", True)), True)
        source_credit = self._as_bool(payload.get("source_credit", True), True)
        screen_size = str(payload.get("screen_size", "9:16"))
        with self._lock:
            if self.thread and self.thread.is_alive():
                return {"status": "busy", "message": "Processing is already running"}
            self._status = "running"
            self._message = "Starting"
            self._progress = 0.0
            self._error = ""
            self._cancel_requested = False
            self._add_log(f"Task {datetime.now().strftime('%d %b %Y %H:%M:%S')} | {url}", "Task")
            self._add_log("Job started")
            self._add_log(f"URL accepted: {url}")
            self._add_log(f"Requested clips: {num_clips}, subtitles: {'on' if add_captions else 'off'}, hook: {'on' if add_hook else 'off'}, language: {subtitle_language}, screen: {screen_size}, blur: {'on' if landscape_blur else 'off'}, source credit: {'on' if source_credit else 'off'}")
            self._add_log(f"Subtitles: {'ON' if add_captions else 'OFF'}")
            args = (url, num_clips, add_captions, add_hook, subtitle_language, instruction, landscape_blur, self._make_run_dir(url), screen_size, source_credit)
            expected_args = self._run.__code__.co_argcount - int(hasattr(self._run, "__self__"))
            if expected_args == 6:
                args = args[:6]
            elif expected_args == 7:
                args = args[:7]
            elif expected_args == 8:
                args = args[:8]
            elif expected_args == 9:
                args = args[:9]
            self.thread = threading.Thread(
                target=self._run,
                args=args,
                daemon=True,
            )
            self.thread.start()
            self._job_start_time = datetime.now()
        return {"status": "started"}

    def status(self):
        return {
            "status": self._status,
            "message": self._public_text(self._message),
            "progress": self._progress,
            "error": self._public_text(self._error),
            "logs": self._logs[-500:],
        }

    def stop(self):
        self._cancel_requested = True
        self._status = "idle"
        self._message = "Stopped"
        self._progress = 0.0
        self._error = ""
        self._add_log("Stop requested")
        self._add_log("Stopped", "Done")
        return {"status": "idle", "message": "Stopped"}

    def clear_logs(self):
        self._logs = []
        return {"status": "cleared"}

    def log_activity(self, payload):
        if not isinstance(payload, dict):
            return {"status": "error", "message": "Invalid activity payload"}
        action = str(payload.get("action", "")).strip()[:40]
        max_len = 1500 if action == "ticket" else 200
        detail = self._public_text(payload.get("detail", "")).strip()[:max_len]
        if not action:
            return {"status": "error", "message": "Action kosong"}
        entry = {"timestamp": datetime.now().isoformat(timespec="seconds"), "action": action, "detail": detail}
        if action == "ticket":
            try:
                ticket_file = ROOT / "tickets.json"
                tickets = json.loads(ticket_file.read_text(encoding="utf-8")) if ticket_file.exists() else []
                tickets.append(entry)
                ticket_file.write_text(json.dumps(tickets, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
        self._activities.append(entry)
        self._activities = self._activities[-200:]
        self._add_log(f"[Activity] {action}: {detail}")
        return {"status": "logged"}

    def list_activities(self):
        return {"status": "ok", "activities": self._activities[-200:]}

    def clear_activities(self):
        self._activities = []
        return {"status": "cleared"}

    def get_settings(self):
        cfg = self._config().config
        provider = cfg.get("ai_providers", {}).get("highlight_finder", {})
        key_saved = bool(provider.get("api_key") or cfg.get("api_key"))
        caption_key_saved = bool(cfg.get("ai_providers", {}).get("caption_maker", {}).get("api_key"))
        base_url = provider.get("base_url", cfg.get("base_url", GEMINI_BASE_URL))
        model = provider.get("model", cfg.get("model", GEMINI_MODEL))
        cookies = self.cookie_status()
        caption_provider = cfg.get("ai_providers", {}).get("caption_maker", {})
        hook_provider = cfg.get("ai_providers", {}).get("hook_maker", {})
        hook_key_saved = bool(hook_provider.get("api_key") or provider.get("api_key") or cfg.get("api_key"))
        return {
            "base_url": base_url,
            "api_key": "",
            "api_key_saved": key_saved,
            "caption_key_saved": caption_key_saved,
            "caption_base_url": caption_provider.get("base_url", "https://api.openai.com/v1"),
            "caption_model": caption_provider.get("model", "whisper-1"),
            "hook_key_saved": hook_key_saved,
            "model": model,
            "provider": {"base_url": base_url, "api_key": "", "model": model},
            "subtitle_language": "id",
            "video_quality": str(cfg.get("video_quality", "720")),
            "landscape_blur": bool(cfg.get("landscape_blur", False)),
            "subtitle_engine": cfg.get("subtitle_engine", "local"),
            "local_whisper": cfg.get("local_whisper", {"enabled": True, "model": "small", "device": "cpu", "compute_type": "int8"}),
            "subtitle_style": cfg.get("subtitle_style", {"font": "Plus Jakarta Sans", "size": 58, "bottom_margin": 360}),
            "subtitle_position": cfg.get("subtitle_position", "auto"),
            "subtitle": cfg.get("subtitle", {"enabled": True, "color": "#ffff00", "size": 0.035, "position_x": 0.5, "position_y": 0.85, "text_transform": "none", "bg_color": "#000000", "bg_opacity": 0.8, "font_family": "Plus Jakarta Sans", "font_weight": 800}),
            "watermark": cfg.get("watermark", {"enabled": False}),
            "credit_watermark": cfg.get("credit_watermark", {"enabled": True, "text": "sc : {channel}", "color": "#FFFFFF", "size": 0.032, "opacity": 0.55, "position_x": 0.06, "position_y": 0.23}),
            "hook_style": cfg.get("hook_style", {"enabled": True, "font_size": 0.054, "text_color": "#0033ff", "background_color": "#ffffff", "corner_radius": 28, "duration": 5.0, "position_x": 0.5, "position_y": 0.2}),
            "blur_background": cfg.get("blur_background", {"enabled": True, "scale": 1.0, "zoom": 1.08, "strength": 30}),
            "output_dir": cfg.get("output_dir", str(self.output_dir)),
            "parallel_workers": int(cfg.get("parallel_workers", 3)),
            "cookie_exists": cookies["exists"],
            "cookie_path": cookies["path"],
            "cookies_path": cookies["path"],
            "cookies": cookies,
        }

    def save_settings(self, payload):
        if not isinstance(payload, dict):
            return {"status": "error", "message": "Invalid settings payload"}
        cfg_mgr = self._config()
        provider_payload = payload.get("provider", {}) if isinstance(payload.get("provider", {}), dict) else {}
        base_url = str(payload.get("base_url", provider_payload.get("base_url", GEMINI_BASE_URL))).strip() or GEMINI_BASE_URL
        api_key = str(payload.get("api_key", provider_payload.get("api_key", ""))).strip()
        clear_api_key = bool(payload.get("clear_api_key", False))
        model = str(payload.get("model", provider_payload.get("model", GEMINI_MODEL))).strip() or GEMINI_MODEL
        caption_base_url = str(payload.get("caption_base_url", cfg_mgr.config.get("ai_providers", {}).get("caption_maker", {}).get("base_url", "https://api.openai.com/v1"))).strip() or "https://api.openai.com/v1"
        caption_api_key = str(payload.get("caption_api_key", "")).strip()
        caption_model = str(payload.get("caption_model", cfg_mgr.config.get("ai_providers", {}).get("caption_maker", {}).get("model", "whisper-1"))).strip() or "whisper-1"
        hook_model = str(payload.get("hook_model", cfg_mgr.config.get("ai_providers", {}).get("hook_maker", {}).get("model", "gemini-3.1-flash-tts-preview"))).strip() or "gemini-3.1-flash-tts-preview"
        hook_voice = str(payload.get("hook_voice", cfg_mgr.config.get("ai_providers", {}).get("hook_maker", {}).get("voice", "Fenrir"))).strip() or "Fenrir"
        output_dir = str(payload.get("output_dir", cfg_mgr.config.get("output_dir", str(self.output_dir)))).strip() or str(self.output_dir)
        subtitle_language = "id"
        video_quality = str(payload.get("video_quality", cfg_mgr.config.get("video_quality", "720")) or "720")
        landscape_blur = self._as_bool(payload.get("landscape_blur", cfg_mgr.config.get("landscape_blur", True)), True)
        subtitle_engine = "local"
        subtitle_position = str(payload.get("subtitle_position", cfg_mgr.config.get("subtitle_position", "auto")) or "auto")
        if subtitle_position not in {"auto", "top", "middle", "bottom"}:
            subtitle_position = "auto"
        local_whisper = cfg_mgr.config.get("local_whisper", {"enabled": True, "model": "small", "device": "cpu", "compute_type": "int8"})
        local_whisper["model"] = "small"
        local_whisper["enabled"] = True
        local_whisper["device"] = str(local_whisper.get("device") or "cpu")
        local_whisper["compute_type"] = str(local_whisper.get("compute_type") or "int8")
        if video_quality not in {"480", "720", "1080"}:
            video_quality = "720"
        subtitle_style = cfg_mgr.config.get("subtitle_style", {"font": "Plus Jakarta Sans", "size": 58, "bottom_margin": 360})
        if isinstance(payload.get("subtitle_style"), dict):
            subtitle_style = {**subtitle_style, **payload["subtitle_style"]}
        subtitle_style["font"] = str(subtitle_style.get("font") or "Plus Jakarta Sans")[:80]
        if subtitle_style["font"] not in {"Plus Jakarta Sans", "Poppins", "Arial"}:
            subtitle_style["font"] = "Plus Jakarta Sans"
        subtitle_style["size"] = max(24, min(120, self._as_int(subtitle_style.get("size"), 58)))
        subtitle_style["bottom_margin"] = max(40, min(900, self._as_int(subtitle_style.get("bottom_margin"), 360)))
        watermark = {**cfg_mgr.config.get("watermark", {"enabled": False}), **(payload.get("watermark") if isinstance(payload.get("watermark"), dict) else {})}
        watermark["enabled"] = self._as_bool(watermark.get("enabled", False), False)
        watermark["image_path"] = str(watermark.get("image_path") or "")
        watermark["opacity"] = max(0.0, min(1.0, float(self._as_float(watermark.get("opacity"), 0.8))))
        watermark["scale"] = max(0.1, min(2.0, float(self._as_float(watermark.get("scale"), 0.15))))
        watermark["position_x"] = max(0.0, min(1.0, float(self._as_float(watermark.get("position_x"), 0.5))))
        watermark["position_y"] = max(0.0, min(1.0, float(self._as_float(watermark.get("position_y"), 0.1))))
        credit_watermark = {**cfg_mgr.config.get("credit_watermark", {"enabled": False}), **(payload.get("credit_watermark") if isinstance(payload.get("credit_watermark"), dict) else {})}
        credit_watermark["enabled"] = self._as_bool(credit_watermark.get("enabled", False), False)
        credit_watermark["text"] = str(credit_watermark.get("text") or "sc : {channel}")[:120]
        credit_watermark["color"] = str(credit_watermark.get("color") or "#FFFFFF")[:16]
        credit_watermark["size"] = max(0.01, min(0.1, float(self._as_float(credit_watermark.get("size"), 0.032))))
        credit_watermark["opacity"] = max(0.0, min(1.0, float(self._as_float(credit_watermark.get("opacity"), 0.55))))
        credit_watermark["position_x"] = max(0.0, min(1.0, float(self._as_float(credit_watermark.get("position_x"), 0.5))))
        credit_watermark["position_y"] = max(0.0, min(1.0, float(self._as_float(credit_watermark.get("position_y"), 0.1))))
        hook_style = {**cfg_mgr.config.get("hook_style", {}), **(payload.get("hook_style") if isinstance(payload.get("hook_style"), dict) else {})}
        hook_style["enabled"] = self._as_bool(hook_style.get("enabled", False), False)
        hook_style["font_size"] = max(0.01, min(0.1, float(self._as_float(hook_style.get("font_size"), 0.054))))
        hook_style["text_color"] = str(hook_style.get("text_color") or hook_style.get("font_color") or "#0033ff")[:16]
        hook_style["font_color"] = hook_style["text_color"]
        hook_style["background_color"] = str(hook_style.get("background_color") or hook_style.get("bg_color") or "#ffffff")[:16]
        hook_style["bg_color"] = hook_style["background_color"]
        hook_style["corner_radius"] = max(0, min(100, self._as_int(hook_style.get("corner_radius"), 28)))
        hook_style["duration"] = max(1.0, min(10.0, float(self._as_float(hook_style.get("duration"), 5.0))))
        hook_style["position_x"] = max(0.0, min(1.0, float(self._as_float(hook_style.get("position_x"), 0.5))))
        hook_style["position_y"] = max(0.0, min(1.0, float(self._as_float(hook_style.get("position_y"), 0.2))))
        hook_style["shape"] = str(hook_style.get("shape") or "rectangle")
        hook_style["font_family"] = str(hook_style.get("font_family") or "Capo Sfogliato")[:80]
        # Subtitle settings
        _sub_payload = payload.get("subtitle") if isinstance(payload.get("subtitle"), dict) else {}
        subtitle_cfg = {**cfg_mgr.config.get("subtitle", {}), **_sub_payload}
        subtitle_cfg["enabled"] = self._as_bool(subtitle_cfg.get("enabled", False), False)
        subtitle_cfg["color"] = str(subtitle_cfg.get("color") or "#ffff00")[:16]
        subtitle_cfg["bg_color"] = str(subtitle_cfg.get("bg_color") or "#000000")[:16]
        subtitle_cfg["size"] = max(0.01, min(0.1, float(self._as_float(subtitle_cfg.get("size"), 0.035))))
        subtitle_cfg["position_x"] = max(0.0, min(1.0, float(self._as_float(subtitle_cfg.get("position_x"), 0.5))))
        subtitle_cfg["position_y"] = max(0.0, min(1.0, float(self._as_float(subtitle_cfg.get("position_y"), 0.85))))
        subtitle_cfg["text_transform"] = str(subtitle_cfg.get("text_transform") or "none")
        subtitle_cfg["bg_opacity"] = max(0.0, min(1.0, float(self._as_float(subtitle_cfg.get("bg_opacity"), 0.8))))
        subtitle_cfg["font_family"] = str(subtitle_cfg.get("font_family") or "Plus Jakarta Sans")[:80]
        subtitle_cfg["font_weight"] = max(100, min(900, int(subtitle_cfg.get("font_weight") or 800)))
        blur_background = {**cfg_mgr.config.get("blur_background", {"enabled": False, "zoom": 1.08, "strength": 30}), **(payload.get("blur_background") if isinstance(payload.get("blur_background"), dict) else {})}
        blur_background["enabled"] = self._as_bool(blur_background.get("enabled", False), False)
        blur_background["scale"] = max(0.5, min(1.5, float(self._as_float(blur_background.get("scale"), 1.0))))
        blur_background["zoom"] = max(1.0, min(2.0, float(blur_background.get("zoom", 1.08) or 1.08)))
        blur_background["strength"] = max(0, min(100, self._as_int(blur_background.get("strength"), 30)))
        providers = cfg_mgr.config.setdefault("ai_providers", {})
        for name in ("highlight_finder", "youtube_title_maker"):
            current = providers.setdefault(name, {})
            current["base_url"] = base_url
            current["model"] = model
            if clear_api_key:
                current["api_key"] = ""
            elif api_key:
                current["api_key"] = api_key
        caption_current = providers.setdefault("caption_maker", {})
        caption_current["base_url"] = caption_base_url
        caption_current["model"] = caption_model
        if clear_api_key:
            caption_current["api_key"] = ""
        elif caption_api_key:
            caption_current["api_key"] = caption_api_key
        hook_current = providers.setdefault("hook_maker", {})
        hook_current["model"] = hook_model
        hook_current["voice"] = hook_voice
        if clear_api_key:
            hook_current["api_key"] = ""
        elif api_key:
            hook_current["api_key"] = api_key
        cfg_mgr.config["base_url"] = base_url
        cfg_mgr.config["model"] = model
        if clear_api_key:
            cfg_mgr.config["api_key"] = ""
        elif api_key:
            cfg_mgr.config["api_key"] = api_key
        cfg_mgr.config["subtitle_language"] = subtitle_language
        cfg_mgr.config["video_quality"] = video_quality
        cfg_mgr.config["landscape_blur"] = landscape_blur
        cfg_mgr.config["subtitle_engine"] = subtitle_engine
        cfg_mgr.config["subtitle_position"] = subtitle_position
        cfg_mgr.config["local_whisper"] = local_whisper
        cfg_mgr.config["subtitle_style"] = subtitle_style
        cfg_mgr.config["watermark"] = watermark
        cfg_mgr.config["credit_watermark"] = credit_watermark
        cfg_mgr.config["hook_style"] = hook_style
        cfg_mgr.config["subtitle"] = subtitle_cfg
        cfg_mgr.config["blur_background"] = blur_background
        cfg_mgr.config["output_dir"] = output_dir
        parallel_workers = max(1, min(8, self._as_int(payload.get("parallel_workers", cfg_mgr.config.get("parallel_workers", 2)), 2)))
        cfg_mgr.config["parallel_workers"] = parallel_workers
        cfg_mgr.save()
        settings = self.get_settings()
        return {"status": "saved", "settings": settings, "local_ai_provider": settings["provider"], "provider": settings["provider"]}

    def save_cookies(self, content):
        text = self._normalize_cookie_text(str(content or ""))
        if not text:
            return {"status": "error", "message": "Login file kosong"}
        self.cookie_file.write_text(text + "\n", encoding="utf-8")
        self._sync_core_cookie_file()
        return {"status": "saved", "success": True, "message": "login file saved", "cookies": self.cookie_status()}

    def cookie_status(self):
        return {"exists": self.cookie_file.exists(), "path": str(self.cookie_file)}

    def _normalize_cookie_text(self, text):
        text = text.strip()
        if not text:
            return ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if any(line.startswith("# Netscape HTTP Cookie File") or line.count("\t") >= 6 for line in lines):
            return "\n".join(lines)
        ignored = {"path", "domain", "expires", "max-age", "secure", "httponly", "samesite"}
        rows = ["# Netscape HTTP Cookie File"]
        for part in re.split(r";\s*", " ; ".join(lines)):
            if "=" not in part:
                continue
            name, value = part.split("=", 1)
            name = name.strip()
            if not name or name.lower() in ignored:
                continue
            rows.append(f".youtube.com\tTRUE\t/\tTRUE\t0\t{name}\t{value.strip()}")
        return "\n".join(rows) if len(rows) > 1 else ""

    def _sync_core_cookie_file(self):
        if self.cookie_file.exists():
            self.core_cookie_file.write_text(self.cookie_file.read_text(encoding="utf-8"), encoding="utf-8")

    def list_outputs(self):
        output_dir = self._output_root()
        output_dir.mkdir(parents=True, exist_ok=True)
        allowed = {".mp4", ".webm", ".mkv", ".mov", ".avi", ".mp3", ".wav", ".json", ".srt", ".ass", ".txt", ".vtt"}
        files = []
        groups = []
        for folder in sorted((p for p in output_dir.iterdir() if p.is_dir() and p.name != "_temp"), key=lambda p: p.stat().st_mtime, reverse=True):
            group_files = [self._file_item(path) for path in sorted(folder.rglob("*"), key=lambda p: p.stat().st_mtime, reverse=True) if path.is_file() and path.suffix.lower() in allowed and "_temp" not in path.parts and not path.name.startswith("temp_")]
            clips = [file for file in group_files if file["name"].lower() == "master.mp4"]
            meta = self._read_json(folder / "run.json")
            if not clips and meta.get("status") in {"deleted", "expired"}:
                groups.append({"name": folder.name, "path": str(folder), "title": meta.get("title") or folder.name, "caption": "file expired/dihapus otomatis", "timestamp": meta.get("deleted_at") or meta.get("timestamp") or datetime.fromtimestamp(folder.stat().st_mtime).isoformat(timespec="seconds"), "video_quality": str(meta.get("video_quality", "720")), "landscape_blur": bool(meta.get("landscape_blur", False)), "thumbnail": "", "saved": bool(meta.get("saved")), "saved_clips": [], "clips": [], "files": [], "status": meta.get("status"), "file_exists": False})
            if clips:
                clip_meta = [self._read_json(Path(file["path"]).with_name("data.json")) for file in clips]
                title = next((item.get("source_title") for item in clip_meta if item.get("source_title")), "")
                description = next((item.get("source_description") for item in clip_meta if item.get("source_description")), "")
                items = []
                for i, file in enumerate(clips):
                    cm = clip_meta[i]
                    dur_s = cm.get("duration_seconds")
                    dur_str = f"{round(dur_s)}s" if dur_s is not None else ""
                    viral = int(cm.get("virality_score") or 5)
                    score_pct = f"{min(100, round(viral * 10))}%"
                    # Thumbnail: look for thumbnail.jpg next to master.mp4
                    thumb_path = Path(file["path"]).with_name("thumbnail.jpg")
                    img_url = f"/api/download?path={quote(str(thumb_path))}" if thumb_path.exists() else ""
                    items.append(dict(
                        file,
                        title=(cm.get("title") or file["name"]),
                        description=(cm.get("description") or ""),
                        duration_seconds=dur_s,
                        duration=dur_str,
                        channel_name=cm.get("channel_name", ""),
                        virality_score=viral,
                        score=score_pct,
                        img=img_url,
                    ))
                groups.append({
                    "name": folder.name,
                    "path": str(folder),
                    "title": title or meta.get("title") or folder.name,
                    "caption": description or meta.get("caption") or meta.get("url") or f"{len(clips)} klip",
                    "timestamp": meta.get("timestamp") or datetime.fromtimestamp(folder.stat().st_mtime).isoformat(timespec="seconds"),
                    "video_quality": str(meta.get("video_quality", "720")),
                    "landscape_blur": bool(meta.get("landscape_blur", False)),
                    "thumbnail": self._thumbnail(clips),
                    "saved": bool(meta.get("saved")),
                    "saved_clips": meta.get("saved_clips", []),
                    "clips": items,
                    "files": items,
                })
                files.extend(clips)
        for path in sorted((p for p in output_dir.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True):
            if path.suffix.lower() in allowed:
                files.append(self._file_item(path))
        files = files[:50]
        return {"files": files, "outputs": files, "groups": groups[:50], "output_dir": str(output_dir)}

    def delete_output(self, payload):
        target = Path(str(payload.get("path", ""))).resolve()
        output_root = self._output_root().resolve()
        if not target.exists() or output_root not in target.parents:
            return {"status": "error", "message": "Output tidak ditemukan"}
        if target.is_file() and target.name.lower() == "master.mp4":
            shutil.rmtree(target.parent)
        elif target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        self.log_activity({"action": "local_delete", "detail": target.name})
        return {"status": "deleted"}

    def save_output(self, payload):
        target = Path(str(payload.get("path", ""))).resolve()
        output_root = self._output_root().resolve()
        if not target.exists() or not target.is_dir() or output_root not in target.parents:
            return {"status": "error", "message": "Session tidak ditemukan"}
        meta_path = target / "run.json"
        meta = self._read_json(meta_path)
        meta["saved"] = True
        meta["status"] = "saved"
        meta["saved_at"] = datetime.now().isoformat(timespec="seconds")
        clips = payload.get("clips") or []
        if not isinstance(clips, list):
            return {"status": "error", "message": "Invalid clips payload"}
        valid_clips = []
        for clip in clips:
            clip_path = Path(str(clip)).resolve()
            if clip_path.exists() and target in clip_path.parents:
                valid_clips.append(str(clip_path))
        keep = set(meta.get("saved_clips", [])) | set(valid_clips)
        meta["saved_clips"] = sorted(keep)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        self._enforce_saved_retention()
        self.log_activity({"action": "gallery_save", "detail": f"{len(valid_clips)} clip dari {target.name}"})
        return {"status": "saved"}

    def _run(self, url, num_clips, add_captions, add_hook, subtitle_language, instruction, landscape_blur, run_dir, screen_size="9:16", source_credit=True):
        try:
            self._sync_core_cookie_file()
            cfg = self._config().config
            prompt = self._with_indonesian_instruction(cfg.get("system_prompt"), instruction)
            add_hook = add_hook and bool(cfg.get("hook_style", {"enabled": True}).get("enabled", True))
            run_dir.mkdir(parents=True, exist_ok=True)
            self._write_run_meta(run_dir, url, {"video_quality": str(cfg.get("video_quality", "720")), "landscape_blur": landscape_blur, "screen_size": screen_size, "add_hook": add_hook, "add_captions": add_captions, "subtitle_language": subtitle_language, "status": "staged", "file_exists": True})
            self._add_log(f"Output folder: {run_dir}")
            self._add_log("Preparing AI/video processor")
            # Merge rich subtitle settings with legacy subtitle_style
            subtitle_style = {
                **cfg.get("subtitle_style", {"font": "Plus Jakarta Sans", "size": 58, "bottom_margin": 360}),
                **cfg.get("subtitle", {}),
                "position": cfg.get("subtitle_position", "auto")
            }
            ai_providers = dict(cfg.get("ai_providers") or {})
            ai_providers["parallel_workers"] = int(cfg.get("parallel_workers", 2))
            core = AutoClipperCore(
                client=None,
                ffmpeg_path=get_ffmpeg_path(),
                ytdlp_path=get_ytdlp_path(),
                output_dir=str(run_dir),
                model=cfg.get("model", GEMINI_MODEL),
                tts_model=cfg.get("tts_model", "tts-1"),
                temperature=cfg.get("temperature", 1.0),
                system_prompt=prompt,
                watermark_settings=cfg.get("watermark", {"enabled": False}),
                credit_watermark_settings={**cfg.get("credit_watermark", {"enabled": True, "position_x": 0.06, "position_y": 0.23, "opacity": 0.55, "size": 0.032}), "enabled": source_credit and bool(cfg.get("credit_watermark", {"enabled": True}).get("enabled", True))},
                hook_style_settings={**cfg.get("hook_style", {}), "blur_background": cfg.get("blur_background", {"enabled": True, "zoom": 1.08, "strength": 30})},
                face_tracking_mode=cfg.get("face_tracking_mode", "center"),
                mediapipe_settings=cfg.get("mediapipe_settings", {}),
                ai_providers=ai_providers,
                subtitle_language=subtitle_language,
                video_quality=str(cfg.get("video_quality", "720")),
                landscape_blur=landscape_blur,
                screen_size=screen_size,
                subtitle_style=subtitle_style,
                subtitle_engine="local",
                local_whisper=cfg.get("local_whisper", {"enabled": True, "model": "small", "device": "cpu", "compute_type": "int8"}),
                cancel_check=lambda: self._cancel_requested,
                log_callback=self._set_message,
                progress_callback=self._set_progress,
            )
            if cfg.get("gpu_acceleration", {}).get("enabled", False):
                self._add_log("GPU acceleration requested")
                core.enable_gpu_acceleration(True)
            quality = str(cfg.get("video_quality", "720"))
            resolution_map = {"16:9": {"480": "854x480", "720": "1280x720", "1080": "1920x1080"}, "9:16": {"480": "540x960", "720": "720x1280", "1080": "1080x1920"}}
            resolution = resolution_map.get(screen_size, resolution_map["9:16"]).get(quality, resolution_map.get(screen_size, resolution_map["9:16"])["720"])
            self._add_log(f"Video quality: {quality}p")
            self._add_log(f"Output resolution: {resolution}")
            self._add_log(f"Screen size: {screen_size}")
            self._add_log(f"Landscape blur: {'on' if landscape_blur else 'off'}")
            self._add_log("Processor started")
            core.process(url, num_clips=num_clips, add_captions=add_captions, add_hook=add_hook)
            if self._cancel_requested:
                raise InterruptedError("Stopped")
            self._write_run_meta(run_dir, url, {**self._summarize_run(run_dir), "video_quality": quality, "landscape_blur": landscape_blur, "screen_size": screen_size, "add_hook": add_hook, "add_captions": add_captions, "subtitle_language": subtitle_language, "status": "staged", "file_exists": True})
            self._enforce_retention()
            self._status = "complete"
            self._message = "Complete"
            self._progress = 1.0
            self._add_log("Complete", "Done")
        except InterruptedError:
            self._status = "idle"
            self._message = "Stopped"
            self._error = ""
            self._add_log("Stopped", "Done")
        except TimeoutError as exc:
            self._status = "error"
            self._message = "Processing timed out"
            self._error = "Job exceeded time limit"
            self._add_log(f"Timeout: {str(exc)}", "Error")
        except Exception as exc:
            if self._cancel_requested:
                self._status = "idle"
                self._message = "Stopped"
                self._error = ""
                self._add_log("Stopped", "Done")
            else:
                self._status = "error"
                self._message = "Processing failed"
                self._error = str(exc)
                self._add_log(str(exc), "Error")
        finally:
            self.thread = None
            self._job_start_time = None

    def _config(self):
        return ConfigManager(self.config_file, self.output_dir)

    def _output_root(self):
        output_value = str(self._config().config.get("output_dir", str(self.output_dir))).strip() or str(self.output_dir)
        return Path(output_value)

    def _set_message(self, message):
        self._message = str(message)
        self._add_log(message)

    def _format_log(self, level, message):
        text = self._public_text(message).strip()
        return f"{datetime.now().strftime('%H:%M:%S')} [{level}] {text}"

    def _add_log(self, message, level=None):
        text = self._public_text(message).strip()
        if not text:
            return
        level = level or ("Error" if any(token in text.lower() for token in ("error", "failed", "gagal", "no subtitle", "exception")) else "Running")
        line = self._format_log(level, text)
        if not self._logs or self._logs[-1].split('] ', 1)[-1] != text:
            self._logs.append(line)
        self._logs = self._logs[-120:]

    def _set_progress(self, stage, progress=None):
        if isinstance(stage, str):
            self._message = stage
            self._add_log(stage)
        value = progress if progress is not None else stage
        try:
            self._progress = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            self._progress = 0.0

    def _make_run_dir(self, url):
        parsed = urlparse(url)
        video_id = parse_qs(parsed.query).get("v", [""])[0] if parsed.query else ""
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", video_id or parsed.path.strip("/") or parsed.netloc).strip("-").lower() or "youtube"
        return self._output_root() / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{slug[:40]}"

    def _file_item(self, path):
        path_value = str(path)
        return {"name": path.name, "filename": path.name, "file": path_value, "output": path_value, "path": path_value, "size": path.stat().st_size, "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")}

    def _read_json(self, path):
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_run_meta(self, run_dir, url, extra=None):
        data = {"url": url, "title": "YouTube export", "caption": url, "timestamp": datetime.now().isoformat(timespec="seconds")}
        data.update(extra or {})
        (run_dir / "run.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _summarize_run(self, run_dir):
        clips = [self._read_json(path) for path in sorted(run_dir.rglob("data.json"))]
        source_title = next((clip.get("source_title") for clip in clips if clip.get("source_title")), "")
        source_description = next((clip.get("source_description") for clip in clips if clip.get("source_description")), "")
        channel_name = next((clip.get("channel_name") for clip in clips if clip.get("channel_name")), "")
        return {"title": source_title or run_dir.name, "caption": source_description or f"{len(clips)} klip diekspor", "channel_name": channel_name, "saved": False}

    def _has_staged_outputs(self):
        output_dir = self._output_root()
        if not output_dir.exists():
            return False
        for folder in output_dir.iterdir():
            if not folder.is_dir() or folder.name == "_temp":
                continue
            meta = self._read_json(folder / "run.json")
            if meta.get("status") in {"deleted", "expired"} or meta.get("file_exists") is False:
                continue
            saved = set(meta.get("saved_clips", []))
            clips = [path for path in folder.rglob("master.mp4") if path.is_file() and "_temp" not in path.parts]
            if any(str(path) not in saved for path in clips):
                return True
        return False

    def _is_url_in_gallery(self, url):
        url = url.strip()
        if not url: return False
        
        from utils.helpers import extract_video_id
        vid = extract_video_id(url)
        
        output_dir = self._output_root()
        if not output_dir.exists():
            return False
            
        for folder in output_dir.iterdir():
            if not folder.is_dir() or folder.name == "_temp":
                continue
            meta = self._read_json(folder / "run.json")
            if not meta.get("saved_clips"):
                continue
            
            saved_url = meta.get("url", "")
            if vid and extract_video_id(saved_url) == vid:
                return True
            elif not vid and saved_url == url:
                return True
                
        return False

    def _enforce_retention(self, max_active=10):
        output_dir = self._output_root()
        sessions = []
        for folder in output_dir.iterdir() if output_dir.exists() else []:
            if not folder.is_dir() or folder.name == "_temp":
                continue
            meta_path = folder / "run.json"
            meta = self._read_json(meta_path)
            if meta.get("status") in {"deleted", "expired"} or meta.get("file_exists") is False:
                continue
            sessions.append((folder.stat().st_mtime, folder, meta_path, meta))
        for _, folder, meta_path, meta in sorted(sessions, reverse=True)[max_active:]:
            for path in sorted(folder.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if path == meta_path:
                    continue
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    try:
                        path.rmdir()
                    except OSError:
                        pass
            meta.update({"status": "expired", "deleted_at": datetime.now().isoformat(timespec="seconds"), "file_exists": False})
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            self._add_log(f"Expired old session: {folder.name}")

    def _enforce_saved_retention(self, max_saved=10):
        output_dir = self._output_root()
        saved_sessions = []
        for folder in output_dir.iterdir() if output_dir.exists() else []:
            meta_path = folder / "run.json"
            meta = self._read_json(meta_path)
            if not folder.is_dir() or not meta.get("saved_clips"):
                continue
            stamp = meta.get("saved_at") or meta.get("timestamp") or ""
            saved_sessions.append((stamp, folder, meta_path, meta))
        for _, folder, meta_path, meta in sorted(saved_sessions, reverse=True)[max_saved:]:
            saved = set(meta.get("saved_clips", []))
            for clip in saved:
                clip_path = Path(clip)
                if clip_path.exists() and folder in clip_path.parents:
                    shutil.rmtree(clip_path.parent, ignore_errors=True)
            meta.update({"status": "expired", "saved_clips": [], "deleted_at": datetime.now().isoformat(timespec="seconds"), "file_exists": any(folder.rglob("master.mp4"))})
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            self._add_log(f"Expired saved gallery item: {folder.name}")

    def _thumbnail(self, files):
        # Prefer thumbnail.jpg if exists alongside the mp4
        for file in files:
            thumb = Path(file["path"]).with_name("thumbnail.jpg")
            if thumb.exists():
                return str(thumb)
        video = next((file for file in files if file["name"].lower().endswith(".mp4")), None)
        return video["path"] if video else ""

    def _public_text(self, value):
        text = str(value or "")
        text = re.sub("cookie|cookies", "login file", text, flags=re.IGNORECASE)
        return text.replace(str(self.cookie_file), "local login file").replace(str(self.core_cookie_file), "local login file")

    def _with_indonesian_instruction(self, prompt, instruction):
        viral = (
            "\n\nTarget user: penonton Indonesia. Pilih momen paling seru dan berpotensi viral: "
            "lucu, emosional, kontroversial ringan, edukatif singkat, quoteable, atau relatable. "
            "Gunakan Bahasa Indonesia natural, bukan terjemahan kaku."
        )
        user = f"\nArahan pengguna: {instruction}" if instruction else ""
        return f"{prompt or AutoClipperCore.get_default_prompt()}{viral}{user}"

    def _as_float(self, value, default=0.0):
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _as_int(self, value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _as_bool(self, value, default=False):
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _is_url(self, value):
        """Validate URL - restrict to YouTube domains only for security"""
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            return False
        if not parsed.netloc:
            return False
        # Restrict to YouTube domains only
        allowed_domains = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
        return parsed.netloc.lower() in allowed_domains
