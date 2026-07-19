import json
import logging
import os
import queue
import re
import uuid
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openai import OpenAI

from clipper_core import AutoClipperCore, LocalClipRenderer
from config.config_manager import ConfigManager
from config.editor_defaults import editor_defaults, v3_locked_render_settings
from gaming_layout import DETECTOR_VERSION, FACE_NOT_FOUND_MESSAGE, GamingLayoutError, detect_facecam, validate_roi
from layout_modes import (
    V3_MODES,
    LayoutModeError,
    validate_mode,
    validate_facecam_overlap,
)
from subtitle_cues import build_subtitle_cues
from youtube_uploader import upload_youtube_video
from utils.helpers import get_app_dir, get_ffmpeg_path, get_ytdlp_path


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
GEMINI_MODEL = "gemini-2.5-flash"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "whisper-large-v3-turbo"
SUPPORTED_VIDEO_QUALITIES = frozenset({"480", "720", "1080", "1440"})
_GLOBAL_QUEUE = queue.Queue()
_GLOBAL_QUEUE_LOCK = threading.Lock()
_GLOBAL_PENDING = []
_GLOBAL_RENDER_LOCK = threading.Lock()
_GLOBAL_FINAL_RENDER_LOCK = threading.Lock()
_RENDER_LOGGER = logging.getLogger("web_klip.renderer")
_UPLOAD_LOGGER = logging.getLogger("web_klip.youtube_upload")
_CLIP_LOCKS = {}
_CLIP_LOCKS_GUARD = threading.Lock()
_CLIP_META_CACHE = {}  # (user_id, clip_id) -> meta_path; avoids glob scan
_CLIP_CANCEL_EVENTS = {}
_CLIP_CANCEL_GUARD = threading.Lock()
_CLIP_META_CACHE_GUARD = threading.Lock()
_ACTIVE_CLIP_STATUSES = {"render_queued", "rendering", "scheduled", "uploading", "needs_facecam"}
_UPLOAD_LEASE_SECONDS = 3600
_RENDER_LEASE_SECONDS = 3600


def _queue_position_for(manager):
    with _GLOBAL_QUEUE_LOCK:
        for index, item in enumerate(_GLOBAL_PENDING, 1):
            if item is manager:
                return index
    return None


def _global_worker():
    while True:
        manager, args = _GLOBAL_QUEUE.get()
        handle = manager.thread
        with _GLOBAL_QUEUE_LOCK:
            if _GLOBAL_PENDING and _GLOBAL_PENDING[0] is manager:
                _GLOBAL_PENDING.pop(0)
            elif manager in _GLOBAL_PENDING:
                _GLOBAL_PENDING.remove(manager)
        try:
            if manager._cancel_requested:
                manager._status, manager._message = "idle", "Stopped"
            else:
                manager._status, manager._message = "running", "Starting"
                manager._job_start_time = datetime.now()
                watchdog = threading.Timer(manager._job_timeout, manager._request_timeout)
                watchdog.daemon = True
                watchdog.start()
                try:
                    manager._run(*args)
                finally:
                    watchdog.cancel()
        finally:
            handle.done.set()
            _GLOBAL_QUEUE.task_done()


threading.Thread(target=_global_worker, daemon=True, name="klipklop-global-worker").start()


class _JobHandle:
    def __init__(self):
        self.done = threading.Event()

    def is_alive(self):
        return not self.done.is_set()

    def join(self, timeout=None):
        self.done.wait(timeout)


class WebJobManager:
    def __init__(self, app_dir=None, user_id=None, local_mode=False):
        self.user_id = str(uuid.UUID(str(user_id))) if user_id else None
        self._vault_enabled = bool(self.user_id and not local_mode)
        self.app_dir = Path(app_dir) if app_dir else get_app_dir()
        self.app_dir.mkdir(parents=True, exist_ok=True)
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
        self._timed_out = False
        self._active_url = ""
        self._v3_mode = None

    def _request_timeout(self):
        self._timed_out = True
        self._cancel_requested = True
        self._status = "error"
        self._message = "Processing timed out"
        self._error = "Job exceeded time limit"
        self._add_log("Job exceeded time limit", "Error")

    def start(self, payload):
        if not isinstance(payload, dict):
            return {"status": "error", "message": "Invalid start payload"}
        url = str(payload.get("url", payload.get("youtube_url", ""))).strip()
        if not self._is_url(url):
            return {"status": "error", "message": "YouTube URL validation error: empty or invalid URL"}

        # V3: validate layout mode if provided
        v3_mode = None
        if "mode" in payload:
            try:
                v3_mode = validate_mode(payload.get("mode"))
            except LayoutModeError as exc:
                return {"status": "error", "message": str(exc)}
        self._v3_mode = v3_mode

        # Check for job timeout
        if self._job_start_time and (datetime.now() - self._job_start_time).total_seconds() > self._job_timeout:
            self._status = "idle"
            self._message = "Idle"
            self._job_start_time = None
            self._add_log("Previous job timed out")

        with self._lock:
            if self.thread and self.thread.is_alive():
                return {"status": "busy", "message": "Processing is already running"}

        settings_payload = payload.get("settings")
        if not isinstance(settings_payload, dict):
            settings_payload = {}
        requested_quality = str(payload.get("video_quality") or settings_payload.get("video_quality") or "")
        if requested_quality and requested_quality not in SUPPORTED_VIDEO_QUALITIES:
            return {"status": "error", "message": "Kualitas video harus 480, 720, 1080, atau 1440"}

        if "settings" in payload and isinstance(payload["settings"], dict):
            self.save_settings(self._settings_from_start_payload(payload))
        elif "video_quality" in payload:
            # V3 form sends quality at top-level without style settings
            self.save_settings({"video_quality": payload.get("video_quality")})
            
        requested_clips = self._as_int(payload.get("num_clips"), 1)
        num_clips = requested_clips if requested_clips in {1, 3, 5} else 1
        add_captions = self._as_bool(payload.get("add_captions", payload.get("enable_captions", True)), True)
        add_hook = self._as_bool(payload.get("add_hook", True), True)
        subtitle_language = str(payload.get("subtitle_language", "id")).strip()[:10]
        instruction = str(payload.get("instruction", "")).strip()[:1000]
        # V3 locked: blur off, portrait screen, captions/hook on
        landscape_blur = False
        source_credit = True
        add_captions = True
        add_hook = True
        screen_size = "9:16"
        subtitle_language = "id"
        with self._lock:
            if self.thread and self.thread.is_alive():
                return {"status": "busy", "message": "Processing is already running"}
            self._status = "queued"
            self._message = "Queued"
            self._progress = 0.0
            self._error = ""
            self._cancel_requested = False
            self._timed_out = False
            self._active_url = url
            self._add_log(f"Task {datetime.now().strftime('%d %b %Y %H:%M:%S')} | {url}", "Task")
            self._add_log("Job started")
            self._add_log(f"URL accepted: {url}")
            self._add_log(f"Requested clips: {num_clips}, subtitles: {'on' if add_captions else 'off'}, hook: {'on' if add_hook else 'off'}, language: {subtitle_language}, screen: {screen_size}, blur: {'on' if landscape_blur else 'off'}, source credit: {'on' if source_credit else 'off'}")
            self._add_log(f"Subtitles: {'ON' if add_captions else 'OFF'}")
            if v3_mode:
                self._add_log(f"V3 layout mode: {v3_mode}")
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
            self.thread = _JobHandle()
            with _GLOBAL_QUEUE_LOCK:
                _GLOBAL_PENDING.append(self)
                queue_position = len(_GLOBAL_PENDING)
            _GLOBAL_QUEUE.put((self, args))
        return {"status": "queued", "queue_position": queue_position}

    @staticmethod
    def _parallel_workers_for_quality(configured_workers, quality):
        configured = max(1, int(configured_workers or 1))
        cap = {"1080": 2, "1440": 1, "2160": 1}.get(str(quality), configured)
        return min(configured, cap)

    def _settings_from_start_payload(self, payload):
        start_settings = dict(payload["settings"])
        if "video_quality" in payload:
            start_settings["video_quality"] = payload["video_quality"]
        if "landscape_blur" in payload:
            start_settings["landscape_blur"] = payload["landscape_blur"]
            blur_settings = dict(start_settings.get("blur_background") or {})
            blur_settings["enabled"] = payload["landscape_blur"]
            start_settings["blur_background"] = blur_settings
        return start_settings

    def status(self):
        with self._lock:
            st = self._status
            if self.thread and self.thread.is_alive() and st not in {"queued", "running", "stopping"}:
                st = "stopping"
        return {
            "status": st,
            "message": self._public_text(self._message),
            "progress": self._progress,
            "error": self._public_text(self._error),
            "url": self._active_url,
            "queue_position": _queue_position_for(self) if st == "queued" else None,
            "logs": self._logs[-500:],
            "v3_modes": list(V3_MODES),
        }

    def stop(self):
        with self._lock:
            self._cancel_requested = True
            if self.thread and self.thread.is_alive():
                self._status = "stopping"
                self._message = "Stopping"
                self._add_log("Stop requested")
                return {"status": "stopping", "message": "Stopping"}
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
                ticket_file = self.app_dir / "tickets.json"
                ticket_file.parent.mkdir(parents=True, exist_ok=True)
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

    def _vault_rpc(self, function, payload=None):
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not self.user_id or not url or not service_key:
            raise RuntimeError("Supabase Vault belum dikonfigurasi")
        request = Request(
            f"{url}/rest/v1/rpc/{function}",
            data=json.dumps({"p_user_id": self.user_id, **(payload or {})}).encode(),
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                raw = response.read()
        except HTTPError as exc:
            raise RuntimeError("Supabase Vault gagal") from exc
        return json.loads(raw.decode()) if raw else None

    def _vault_key_exists(self, provider):
        return bool(self._vault_rpc("klipklop_provider_key_exists", {"p_provider": provider}))

    def _vault_read_key(self, provider):
        value = self._vault_rpc("klipklop_read_provider_key", {"p_provider": provider})
        return str(value or "")

    def _vault_write_key(self, provider, value):
        self._vault_rpc("klipklop_set_provider_key", {"p_provider": provider, "p_secret": value})

    def _vault_delete_key(self, provider):
        self._vault_rpc("klipklop_delete_provider_key", {"p_provider": provider})

    def _hook_tts_config(self):
        cfg = self._config().config
        providers = cfg.get("ai_providers", {})
        hook = providers.get("hook_maker", {})
        api_key = self._vault_read_key("hook") if self._vault_enabled else hook.get("api_key", "")
        return {"tts_api_key": str(api_key or ""), "tts_api_keys": [api_key, *(hook.get("backup_api_keys") or [])], "tts_base_url": str(hook.get("base_url") or "https://generativelanguage.googleapis.com/v1beta"), "tts_model": str(hook.get("model") or "gemini-3.1-flash-tts-preview"), "tts_voice": str(hook.get("voice") or "Fenrir")}

    def get_settings(self):
        cfg = self._config().config
        provider = cfg.get("ai_providers", {}).get("highlight_finder", {})
        key_saved = self._vault_key_exists("highlight") if self._vault_enabled else bool(provider.get("api_key") or cfg.get("api_key"))
        caption_key_saved = self._vault_key_exists("caption") if self._vault_enabled else bool(cfg.get("ai_providers", {}).get("caption_maker", {}).get("api_key"))
        base_url = provider.get("base_url", cfg.get("base_url", GEMINI_BASE_URL))
        model = provider.get("model", cfg.get("model", GEMINI_MODEL))
        cookies = self.cookie_status()
        caption_provider = cfg.get("ai_providers", {}).get("caption_maker", {})
        hook_provider = cfg.get("ai_providers", {}).get("hook_maker", {})
        hook_key_saved = self._vault_key_exists("hook") if self._vault_enabled else bool(hook_provider.get("api_key"))
        return {
            "base_url": base_url,
            "api_key": "",
            "api_key_saved": key_saved,
            "caption_key_saved": caption_key_saved,
            "caption_api_key": "",
            "caption_base_url": caption_provider.get("base_url", GROQ_BASE_URL),
            "caption_model": caption_provider.get("model", GROQ_MODEL),
            "hook_key_saved": hook_key_saved,
            "hook_api_key": "",
            "hook_model": str(hook_provider.get("model") or "gemini-3.1-flash-tts-preview"),
            "hook_voice": str(hook_provider.get("voice") or "Fenrir"),
            "model": model,
            "provider": {"base_url": base_url, "api_key": "", "model": model},
            "subtitle_language": str(cfg.get("subtitle_language", "id")),
            "video_quality": str(cfg.get("video_quality", "720")),
            "landscape_blur": bool(cfg.get("landscape_blur", False)),
            "subtitle_style": cfg.get("subtitle_style", {"font": "Plus Jakarta Sans", "size": 58, "bottom_margin": 360}),
            "subtitle_position": cfg.get("subtitle_position", "auto"),
            "subtitle": cfg.get("subtitle", {"enabled": True, "color": "#00BFFF", "text_color": "#FFFFFF", "size": 0.04, "position_x": 0.5, "position_y": 0.85, "text_transform": "none", "bg_color": "#000000", "bg_opacity": 0.0, "font_family": "Plus Jakarta Sans", "font_weight": 800, "outline_color": "#000000", "outline_thickness": 1.0}),
            "watermark": cfg.get("watermark", {"enabled": False}),
            "credit_watermark": cfg.get("credit_watermark", {"enabled": True, "text": "sc : {channel}", "color": "#FFFFFF", "size": 0.032, "opacity": 0.55, "position_x": 0.06, "position_y": 0.23}),
            "hook_style": cfg.get("hook_style", {"enabled": True, "font_size": 0.054, "font_family": "Plus Jakarta Sans", "font_weight": 800, "text_color": "#FFD700", "outline_color": "#000000", "outline_thickness": 1.5, "duration": 5.0, "position_x": 0.5, "position_y": 0.2}),
            "blur_background": cfg.get("blur_background", {"enabled": True, "scale": 1.0, "zoom": 1.08, "strength": 30}),
            "video_layout": {"mode": cfg.get("video_layout", {}).get("mode", "normal")},
            "output_dir": cfg.get("output_dir", str(self.output_dir)),
            "parallel_workers": int(cfg.get("parallel_workers", 1)),
            "cookie_exists": cookies["exists"],
            "cookie_path": cookies["path"],
            "cookies_path": cookies["path"],
            "cookies": cookies,
        }

    def check_ai_provider(self, payload):
        if not isinstance(payload, dict):
            return {"status": "error", "message": "Invalid payload"}
        provider_name = str(payload.get("provider_name", "highlight_finder")).strip()
        provider_payload = payload.get("provider", {}) if isinstance(payload.get("provider", {}), dict) else {}
        base_url = str(payload.get("base_url", provider_payload.get("base_url", ""))).strip().rstrip("/")
        api_key = str(payload.get("api_key", provider_payload.get("api_key", ""))).strip()
        model = str(payload.get("model", provider_payload.get("model", ""))).strip()
        cfg_mgr = self._config()
        saved_provider = cfg_mgr.config.get("ai_providers", {}).get(provider_name, {})
        if not api_key:
            if provider_name == "highlight_finder":
                api_key = self._vault_read_key("highlight") if self._vault_enabled else saved_provider.get("api_key") or cfg_mgr.config.get("api_key", "")
            elif provider_name == "caption_maker":
                api_key = self._vault_read_key("caption") if self._vault_enabled else saved_provider.get("api_key", "")
            else:
                return {"status": "error", "message": "Provider tidak dikenal"}
            if base_url.rstrip("/") != str(saved_provider.get("base_url", "")).rstrip("/") or model != str(saved_provider.get("model", "")):
                return {"status": "error", "message": "Isi API key untuk menguji Base URL atau model baru"}

        if not base_url:
            return {"status": "error", "message": "Base URL kosong"}
        if not api_key:
            return {"status": "error", "message": "API key kosong"}
        if not model:
            return {"status": "error", "message": "Model kosong"}
        try:
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=20.0)
            if provider_name == "caption_maker":
                try:
                    import requests
                    headers = {"Authorization": f"Bearer {api_key}"}
                    resp = requests.get(f"{base_url}/models", headers=headers, timeout=20.0)
                    resp.raise_for_status()
                    models_data = resp.json().get("data", [])
                    available_models = [m.get("id") for m in models_data if isinstance(m, dict)]
                    if model not in available_models and len(available_models) > 0:
                        return {"status": "error", "message": f"Model '{model}' tidak tersedia di provider ini.", "base_url": base_url, "model": model}
                    return {"status": "ok", "message": "API key, base URL, dan model valid", "base_url": base_url, "model": model}
                except Exception as e:
                    # Fallback to standard OpenAI models check if requests fails
                    models = client.models.list()
                    available_models = [m.id for m in models.data]
                    if model not in available_models and len(available_models) > 0:
                        return {"status": "error", "message": f"Model '{model}' tidak tersedia.", "base_url": base_url, "model": model}
                    return {"status": "ok", "message": "API key, base URL, dan model valid", "base_url": base_url, "model": model}
            else:
                # Default text completion check for highlight finder
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "Reply OK only."}],
                    max_tokens=4,
                    temperature=0,
                )
                content = (response.choices[0].message.content or "").strip() if response and response.choices else ""
                return {"status": "ok", "message": "API key, base URL, dan model valid", "base_url": base_url, "model": model, "response": content[:80]}
        except Exception as exc:
            return {"status": "error", "message": str(exc).replace(api_key, "***") if api_key else str(exc), "base_url": base_url, "model": model}

    def save_settings(self, payload):
        if not isinstance(payload, dict):
            return {"status": "error", "message": "Invalid settings payload"}
        cfg_mgr = self._config()
        provider_payload = payload.get("provider", {}) if isinstance(payload.get("provider", {}), dict) else {}
        base_url = str(payload.get("base_url", provider_payload.get("base_url", GEMINI_BASE_URL))).strip() or GEMINI_BASE_URL
        api_key = str(payload.get("api_key", provider_payload.get("api_key", ""))).strip()
        clear_api_key = bool(payload.get("clear_api_key", False))
        clear_highlight_api_key = bool(payload.get("clear_highlight_api_key", False))
        clear_caption_api_key = bool(payload.get("clear_caption_api_key", False))
        clear_hook_api_key = bool(payload.get("clear_hook_api_key", False))
        model = str(payload.get("model", provider_payload.get("model", cfg_mgr.config.get("model", GEMINI_MODEL)))).strip() or GEMINI_MODEL
        caption_base_url = str(payload.get("caption_base_url", cfg_mgr.config.get("ai_providers", {}).get("caption_maker", {}).get("base_url", GROQ_BASE_URL))).strip() or GROQ_BASE_URL
        caption_api_key = str(payload.get("caption_api_key", "")).strip()
        caption_model = str(payload.get("caption_model", cfg_mgr.config.get("ai_providers", {}).get("caption_maker", {}).get("model", GROQ_MODEL))).strip() or GROQ_MODEL
        hook_api_key = str(payload.get("hook_api_key", "")).strip()
        hook_model = str(payload.get("hook_model", cfg_mgr.config.get("ai_providers", {}).get("hook_maker", {}).get("model", "gemini-3.1-flash-tts-preview"))).strip() or "gemini-3.1-flash-tts-preview"
        hook_voice = str(payload.get("hook_voice", cfg_mgr.config.get("ai_providers", {}).get("hook_maker", {}).get("voice", "Fenrir"))).strip() or "Fenrir"
        output_dir = str(self.output_dir)
        subtitle_language = str(payload.get("subtitle_language", cfg_mgr.config.get("subtitle_language", "id")) or "id")[:10]
        video_quality = str(payload.get("video_quality", cfg_mgr.config.get("video_quality", "720")) or "720")
        landscape_blur = self._as_bool(payload.get("landscape_blur", cfg_mgr.config.get("landscape_blur", True)), True)
        subtitle_position = str(payload.get("subtitle_position", cfg_mgr.config.get("subtitle_position", "auto")) or "auto")
        if subtitle_position not in {"auto", "top", "middle", "bottom"}:
            subtitle_position = "auto"
        if video_quality not in SUPPORTED_VIDEO_QUALITIES:
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
        watermark_root = (self.app_dir / "watermark").resolve()
        saved_watermark = Path(str(cfg_mgr.config.get("watermark", {}).get("image_path") or "")).resolve()
        watermark["image_path"] = str(saved_watermark) if saved_watermark.is_file() and watermark_root in saved_watermark.parents else ""
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
        hook_style["text_color"] = self._as_color(hook_style.get("text_color") or hook_style.get("font_color"), "#FFD700")
        hook_style["font_color"] = hook_style["text_color"]
        hook_style["font_weight"] = max(100, min(900, round(self._as_int(hook_style.get("font_weight"), 800) / 100) * 100))
        hook_style["outline_color"] = self._as_color(hook_style.get("outline_color"), "#000000")
        hook_style["outline_thickness"] = max(0.0, min(6.0, self._as_float(hook_style.get("outline_thickness"), 1.5)))
        hook_style["duration"] = max(1.0, min(10.0, float(self._as_float(hook_style.get("duration"), 5.0))))
        hook_style["position_x"] = max(0.0, min(1.0, float(self._as_float(hook_style.get("position_x"), 0.5))))
        hook_style["position_y"] = max(0.0, min(1.0, float(self._as_float(hook_style.get("position_y"), 0.2))))
        hook_style["font_family"] = str(hook_style.get("font_family") or "Plus Jakarta Sans")
        if hook_style["font_family"] not in {"Plus Jakarta Sans", "Poppins"}:
            hook_style["font_family"] = "Plus Jakarta Sans"
        # Subtitle settings
        _sub_payload = payload.get("subtitle") if isinstance(payload.get("subtitle"), dict) else {}
        subtitle_cfg = {**cfg_mgr.config.get("subtitle", {}), **_sub_payload}
        subtitle_cfg["enabled"] = self._as_bool(subtitle_cfg.get("enabled", False), False)
        subtitle_cfg["color"] = self._as_color(subtitle_cfg.get("color"), "#00BFFF")
        subtitle_cfg["text_color"] = self._as_color(subtitle_cfg.get("text_color"), "#FFFFFF")
        subtitle_cfg["bg_color"] = self._as_color(subtitle_cfg.get("bg_color"), "#000000")
        subtitle_cfg["size"] = max(0.01, min(0.1, float(self._as_float(subtitle_cfg.get("size"), 0.04))))
        subtitle_cfg["position_x"] = max(0.0, min(1.0, float(self._as_float(subtitle_cfg.get("position_x"), 0.5))))
        subtitle_cfg["position_y"] = max(0.0, min(1.0, float(self._as_float(subtitle_cfg.get("position_y"), 0.85))))
        subtitle_cfg["text_transform"] = str(subtitle_cfg.get("text_transform") or "none")
        subtitle_cfg["bg_opacity"] = max(0.0, min(1.0, float(self._as_float(subtitle_cfg.get("bg_opacity"), 0.0))))
        subtitle_cfg["font_family"] = str(subtitle_cfg.get("font_family") or "Plus Jakarta Sans")
        if subtitle_cfg["font_family"] not in {"Plus Jakarta Sans", "Poppins"}:
            subtitle_cfg["font_family"] = "Plus Jakarta Sans"
        subtitle_cfg["font_weight"] = max(100, min(900, round(self._as_int(subtitle_cfg.get("font_weight"), 800) / 100) * 100))
        subtitle_cfg["outline_color"] = self._as_color(subtitle_cfg.get("outline_color"), "#000000")
        subtitle_cfg["outline_thickness"] = max(0.0, min(6.0, self._as_float(subtitle_cfg.get("outline_thickness"), 1.0)))
        blur_background = {**cfg_mgr.config.get("blur_background", {"enabled": False, "zoom": 1.08, "strength": 30}), **(payload.get("blur_background") if isinstance(payload.get("blur_background"), dict) else {})}
        blur_background["enabled"] = self._as_bool(blur_background.get("enabled", False), False)
        blur_background["scale"] = max(1.0, min(2.0, float(self._as_float(blur_background.get("scale"), 1.6))))
        blur_background["zoom"] = max(1.0, min(3.0, float(blur_background.get("zoom", 1.08) or 1.08)))
        blur_background["strength"] = max(0, min(100, self._as_int(blur_background.get("strength"), 30)))
        video_layout_payload = payload.get("video_layout") if isinstance(payload.get("video_layout"), dict) else {}
        video_layout = {"mode": str(video_layout_payload.get("mode", cfg_mgr.config.get("video_layout", {}).get("mode", "normal")))}
        if video_layout["mode"] not in {"normal", "gaming"}:
            video_layout["mode"] = "normal"
        if self._vault_enabled:
            try:
                if clear_api_key or clear_highlight_api_key:
                    self._vault_delete_key("highlight")
                elif api_key:
                    self._vault_write_key("highlight", api_key)
                if clear_api_key or clear_caption_api_key:
                    self._vault_delete_key("caption")
                elif caption_api_key:
                    self._vault_write_key("caption", caption_api_key)
                if clear_api_key or clear_hook_api_key:
                    self._vault_delete_key("hook")
                elif hook_api_key:
                    self._vault_write_key("hook", hook_api_key)
            except RuntimeError as exc:
                return {"status": "error", "message": str(exc)}
        providers = cfg_mgr.config.setdefault("ai_providers", {})
        for name in ("highlight_finder", "youtube_title_maker"):
            current = providers.setdefault(name, {})
            current["base_url"] = base_url
            current["model"] = model
            if clear_api_key or clear_highlight_api_key or self._vault_enabled:
                current["api_key"] = ""
            elif api_key:
                current["api_key"] = api_key
        caption_current = providers.setdefault("caption_maker", {})
        caption_current["base_url"] = caption_base_url
        caption_current["model"] = caption_model
        if clear_api_key or clear_caption_api_key or self._vault_enabled:
            caption_current["api_key"] = ""
        elif caption_api_key:
            caption_current["api_key"] = caption_api_key
        hook_current = providers.setdefault("hook_maker", {})
        hook_current["base_url"] = "https://generativelanguage.googleapis.com/v1beta"
        hook_current["model"] = hook_model
        hook_current["voice"] = hook_voice
        if clear_api_key or clear_hook_api_key or self._vault_enabled:
            hook_current["api_key"] = ""
        elif hook_api_key:
            hook_current["api_key"] = hook_api_key
        cfg_mgr.config["base_url"] = base_url
        cfg_mgr.config["model"] = model
        if clear_api_key or clear_highlight_api_key or self._vault_enabled:
            cfg_mgr.config["api_key"] = ""
        elif api_key:
            cfg_mgr.config["api_key"] = api_key
        cfg_mgr.config["subtitle_language"] = subtitle_language
        cfg_mgr.config["video_quality"] = video_quality
        cfg_mgr.config["landscape_blur"] = landscape_blur
        cfg_mgr.config["subtitle_position"] = subtitle_position
        cfg_mgr.config["subtitle_style"] = subtitle_style
        cfg_mgr.config["watermark"] = watermark
        cfg_mgr.config["credit_watermark"] = credit_watermark
        cfg_mgr.config["hook_style"] = hook_style
        cfg_mgr.config["subtitle"] = subtitle_cfg
        cfg_mgr.config["blur_background"] = blur_background
        cfg_mgr.config["video_layout"] = video_layout
        cfg_mgr.config["output_dir"] = output_dir
        parallel_workers = max(1, min(8, self._as_int(payload.get("parallel_workers", cfg_mgr.config.get("parallel_workers", 1)), 1)))
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

    def recover_stale_clip_operations(self, now=None):
        now = now or datetime.now(timezone.utc)
        for meta_path in self._output_root().glob("*/**/data.json"):
            metadata = self._read_json(meta_path)
            clip_id = metadata.get("clip_id")
            if not clip_id:
                continue
            with self._clip_lock(clip_id):
                metadata = self._read_json(meta_path)
                status = metadata.get("status")
                upload = dict(metadata.get("youtube_upload") or {})
                stamp = upload.get("uploading_at") if status == "uploading" else metadata.get("render_started_at") or metadata.get("render_queued_at")
                lease = _UPLOAD_LEASE_SECONDS if status == "uploading" else _RENDER_LEASE_SECONDS
                if status not in {"uploading", "rendering", "render_queued"} or not self._is_stale_timestamp(stamp, now, lease):
                    continue
                if status == "uploading":
                    upload.update(status="upload_error", error="Upload terhenti. Coba lagi.")
                    metadata.update(status="upload_error", youtube_upload=upload)
                    self._add_log(f"Recovered stale upload for clip {str(clip_id)[:12]}", "Error")
                else:
                    metadata.update(status="render_error", render_error="Render terhenti. Coba lagi.", render_stage="Render terhenti")
                    self._add_log(f"Recovered stale render for clip {str(clip_id)[:12]}", "Error")
                self._write_json_atomic(meta_path, metadata)

    @staticmethod
    def _is_stale_timestamp(value, now, lease_seconds):
        try:
            stamp = datetime.fromisoformat(str(value or ""))
            return stamp.tzinfo is not None and (now - stamp.astimezone(timezone.utc)).total_seconds() > lease_seconds
        except (TypeError, ValueError):
            return True

    def process_due_youtube_uploads(self):
        self.recover_stale_clip_operations()
        for meta_path in self._output_root().glob("*/**/data.json"):
            metadata = self._read_json(meta_path)
            pending = metadata.get("pending_youtube_upload") if isinstance(metadata.get("pending_youtube_upload"), dict) else None
            if pending and metadata.get("status") == "ready_to_schedule":
                with self._clip_lock(metadata.get("clip_id") or str(meta_path)):
                    metadata = self._read_json(meta_path)
                    pending = metadata.pop("pending_youtube_upload", None)
                    if isinstance(pending, dict) and metadata.get("status") == "ready_to_schedule":
                        pending.update(status="scheduled", render_revision=int(metadata.get("render_revision", 0)))
                        metadata.update(status="scheduled", youtube_upload=pending)
                        self._write_json_atomic(meta_path, metadata)
            upload = metadata.get("youtube_upload") if isinstance(metadata.get("youtube_upload"), dict) else {}
            if upload.get("status") != "scheduled":
                continue
            try:
                scheduled_at = datetime.fromisoformat(str(upload.get("scheduled_at") or ""))
                due = scheduled_at.tzinfo is not None and scheduled_at <= datetime.now(timezone.utc)
            except ValueError:
                due = False
                with self._clip_lock(metadata.get("clip_id") or str(meta_path)):
                    current = self._read_json(meta_path)
                    current_upload = dict(current.get("youtube_upload") or {})
                    if current_upload.get("status") == "scheduled":
                        current_upload.update(status="upload_error", error="Waktu upload tidak valid")
                        current.update(status="upload_error", youtube_upload=current_upload)
                        self._write_json_atomic(meta_path, current)
            if not due:
                continue
            clip_id = metadata.get("clip_id")
            if clip_id:
                claim = self._upload_claim(str(clip_id), {"scheduled"})
                if claim is None:
                    continue
                claimed_path, attempt_id, revision, claimed_upload = claim
                current = self._read_json(claimed_path)
                if current.get("status") != "uploading" or current.get("attempt_id") != attempt_id or int(current.get("render_revision", 0)) != revision:
                    continue
                try:
                    result = upload_youtube_video(claimed_path.with_name("master.mp4"), claimed_upload.get("title"), claimed_upload.get("description"), "public", self.user_id)
                except Exception as exc:
                    self._complete_upload(claimed_path, attempt_id, revision)
                    _UPLOAD_LOGGER.exception("scheduled upload failed clip=%s error=%s", str(clip_id)[:12], type(exc).__name__)
                    self._add_log(f"Scheduled upload failed for clip {str(clip_id)[:12]} ({type(exc).__name__})", "Error")
                    continue
                if self._complete_upload(claimed_path, attempt_id, revision, result):
                    self.log_activity({"action": "youtube_upload", "detail": str(result.get("video_id", ""))[:80]})
                continue
            attempt_id = uuid.uuid4().hex
            upload.update(status="uploading", attempt_id=attempt_id, uploading_at=datetime.now(timezone.utc).isoformat(), render_revision=int(metadata.get("render_revision", 0)))
            metadata.update(status="uploading", attempt_id=attempt_id, youtube_upload=upload)
            self._write_json_atomic(meta_path, metadata)
            try:
                result = upload_youtube_video(meta_path.with_name("master.mp4"), upload.get("title"), upload.get("description"), "public", self.user_id)
                upload.update(status="uploaded", **result, uploaded_at=datetime.now(timezone.utc).isoformat())
                metadata.update(status="uploaded", youtube_upload=upload)
            except Exception as exc:
                upload.update(status="upload_error", error="Upload YouTube gagal. Coba lagi.")
                metadata.update(status="upload_error", youtube_upload=upload)
                _UPLOAD_LOGGER.exception("legacy scheduled upload failed error=%s", type(exc).__name__)
                self._add_log(f"Scheduled YouTube upload failed ({type(exc).__name__})", "Error")
            self._write_json_atomic(meta_path, metadata)

    @staticmethod
    def _source_geometry(source):
        try:
            probe = Path(get_ffmpeg_path()).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
            from clipper_ffmpeg import _FFMPEG_PROCESS_LOCK
            with _FFMPEG_PROCESS_LOCK:
                result = subprocess.run([str(probe), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,sample_aspect_ratio,display_aspect_ratio:stream_tags=rotate", "-of", "json", str(source)], capture_output=True, text=True, timeout=15)
            stream = (json.loads(result.stdout).get("streams") or [{}])[0]
            width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
            if width <= 0 or height <= 0:
                return {}
            rotation = int((stream.get("tags") or {}).get("rotate") or 0)
            displayed_width, displayed_height = (height, width) if abs(rotation) % 180 == 90 else (width, height)
            return {"width": width, "height": height, "sample_aspect_ratio": stream.get("sample_aspect_ratio") or "1:1", "display_aspect_ratio": stream.get("display_aspect_ratio") or "", "rotation": rotation, "is_landscape": displayed_width > displayed_height}
        except (OSError, ValueError, TypeError, subprocess.SubprocessError, json.JSONDecodeError):
            return {}

    def _clip_view(self, meta_path, meta):
        clip_dir = meta_path.parent
        draft = clip_dir / "draft.mp4"
        final = clip_dir / "master.mp4"
        thumbnail = clip_dir / "thumbnail.jpg"
        clip_id = str(meta.get("clip_id") or "")
        revision = int(meta.get("render_revision", 0))
        media_url = lambda artifact: f"/api/clip/media?clip_id={quote(clip_id)}&artifact={artifact}&v={revision}"
        draft_url = media_url("draft") if draft.is_file() else ""
        final_url = media_url("final") if final.is_file() else ""
        source = clip_dir / "source.mp4"
        source_geometry = meta.get("source_geometry") if isinstance(meta.get("source_geometry"), dict) else {}
        if source.is_file() and not source_geometry:
            probed_geometry = self._source_geometry(source)
            if probed_geometry:
                with self._clip_lock(clip_id):
                    current = self._read_json(meta_path)
                    source_geometry = current.get("source_geometry") if isinstance(current.get("source_geometry"), dict) else {}
                    if not source_geometry:
                        source_geometry = probed_geometry
                        current["source_geometry"] = source_geometry
                        self._write_json_atomic(meta_path, current)
        source_url = media_url("source") if source.is_file() else ""
        return {
            "clip_id": clip_id,
            "generation_id": str(meta.get("generation_id") or meta_path.parent.parent.name),
            "created_at": str(meta.get("created_at") or datetime.fromtimestamp(meta_path.stat().st_mtime, timezone.utc).isoformat()),
            "status": meta.get("status", "needs_edit"),
            "title": meta.get("title", final.stem if final.is_file() else draft.stem),
            "description": meta.get("description", ""),
            "hook_text": meta.get("hook_text", ""),
            "duration_seconds": meta.get("duration_seconds", 0),
            "virality_score": meta.get("virality_score", 5),
            "channel_name": meta.get("channel_name", ""),
            "draft_settings": meta.get("draft_settings", {}),
            "render_settings": meta.get("render_settings", {}),
            "source_url": source_url,
            "source_geometry": source_geometry,
            "render_revision": revision,
            "draft_url": draft_url,
            "final_url": final_url,
            "stream_url": final_url or draft_url,
            "final_download_url": f"/api/clip/media?clip_id={quote(clip_id)}&artifact=final&download=1&v={revision}" if final.is_file() else "",
            "final_file": {"exists": final.is_file(), "size": final.stat().st_size if final.is_file() else 0},
            "render_error": meta.get("render_error", ""),
            "render": {
                "progress": meta.get("render_progress", 0.0),
                "stage": meta.get("render_stage", ""),
                "started_at": meta.get("render_started_at"),
                "elapsed_seconds": meta.get("render_elapsed_seconds", 0.0),
                "error": meta.get("render_error", ""),
            },
            "needs_facecam": meta.get("status") == "needs_facecam",
            "gaming_detection": meta.get("gaming_detection") if isinstance(meta.get("gaming_detection"), dict) else {},
            "youtube_upload": meta.get("youtube_upload"),
            "youtube_upload_history": meta.get("youtube_upload_history", []),
            "thumbnail_url": media_url("thumbnail") if thumbnail.is_file() else "",
        }

    def clip_artifact(self, clip_id, artifact, preview_id=""):
        meta_path, metadata = self._clip_meta(str(clip_id or ""))
        if not meta_path:
            return None
        names = {"source": "source.mp4", "draft": "draft.mp4", "final": "master.mp4", "thumbnail": "thumbnail.jpg"}
        name = names.get(str(artifact or ""))
        if not name:
            return None
        target = (meta_path.parent / name).resolve()
        root = meta_path.parent.resolve()
        if root not in target.parents and target != root / name:
            # ensure resolved path stays under clip dir
            try:
                target.relative_to(root)
            except ValueError:
                return None
        return target if target.is_file() else None

    def list_clips(self):
        self._enforce_clip_limit()
        clips = []
        for meta_path in self._output_root().glob("*/**/data.json"):
            meta = self._read_json(meta_path)
            if not meta.get("clip_id"):
                continue
            has_media = (meta_path.parent / "draft.mp4").is_file() or (meta_path.parent / "master.mp4").is_file()
            if not has_media and meta.get("status") != "needs_facecam":
                continue
            clips.append(self._clip_view(meta_path, meta))
        return {"status": "ok", "clips": sorted(clips, key=lambda item: (item["created_at"], item["clip_id"]), reverse=True)[:15]}

    def _clip_meta(self, clip_id):
        cache_key = (self.user_id or str(self.app_dir.resolve()), str(clip_id))
        with _CLIP_META_CACHE_GUARD:
            cached = _CLIP_META_CACHE.get(cache_key)
        if cached and cached.is_file():
            meta = self._read_json(cached)
            if meta.get("clip_id") == clip_id:
                return cached, meta
            # stale cache entry — clean up
            with _CLIP_META_CACHE_GUARD:
                _CLIP_META_CACHE.pop(cache_key, None)
        for meta_path in self._output_root().glob("*/**/data.json"):
            meta = self._read_json(meta_path)
            if meta.get("clip_id") == clip_id:
                with _CLIP_META_CACHE_GUARD:
                    _CLIP_META_CACHE[cache_key] = meta_path
                return meta_path, meta
        return None, None

    def _clip_lock(self, clip_id):
        key = (self.user_id or str(self.app_dir.resolve()), str(clip_id))
        with _CLIP_LOCKS_GUARD:
            return _CLIP_LOCKS.setdefault(key, threading.RLock())

    def _cancel_event(self, clip_id):
        key = (self.user_id or str(self.app_dir.resolve()), str(clip_id or ""))
        with _CLIP_CANCEL_GUARD:
            event = _CLIP_CANCEL_EVENTS.get(key)
            if event is None:
                event = threading.Event()
                _CLIP_CANCEL_EVENTS[key] = event
            return event

    def _reset_cancel_event(self, clip_id):
        event = self._cancel_event(clip_id)
        event.clear()
        return event

    def _locked_clip_meta(self, clip_id):
        lock = self._clip_lock(clip_id)
        lock.acquire()
        meta_path, metadata = self._clip_meta(clip_id)
        return lock, meta_path, metadata

    def _cas_clip(self, meta_path, attempt_id, statuses, mutate):
        clip_id = self._read_json(meta_path).get("clip_id")
        with self._clip_lock(clip_id):
            current = self._read_json(meta_path)
            if current.get("attempt_id") != attempt_id or current.get("status") not in set(statuses):
                return None
            mutate(current)
            self._write_json_atomic(meta_path, current)
            return current


    def _safe_transcript_path(self, clip_dir, metadata):
        name = Path(str(metadata.get("transcript_path") or "transcript.json")).name
        if name != "transcript.json":
            name = "transcript.json"
        target = (Path(clip_dir) / name).resolve()
        root = Path(clip_dir).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return root / "transcript.json"
        return target

    def get_clip(self, clip_id):
        meta_path, meta = self._clip_meta(str(clip_id or ""))
        if not meta_path or not (meta_path.parent / "draft.mp4").is_file() and not (meta_path.parent / "master.mp4").is_file():
            return {"status": "error", "message": "Klip tidak ditemukan"}
        view = self._clip_view(meta_path, meta)
        transcript_path = self._safe_transcript_path(meta_path.parent, meta)
        try:
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            settings = self._render_settings({}, meta, require_gaming_roi=False)
            cues = build_subtitle_cues(transcript, settings["subtitle"].get("text_transform", "none"))
            if len(cues) > 3600 or len(json.dumps(cues, ensure_ascii=False).encode("utf-8")) > 2 * 1024 * 1024:
                raise ValueError("Subtitle terlalu besar")
            view["subtitle_cues"] = cues
            view["subtitle_capability"] = cues[0]["capability"] if cues else "unavailable"
            view["subtitle_reason"] = "" if cues else "Subtitle tidak memiliki waktu tampil"
        except (OSError, ValueError, json.JSONDecodeError, TypeError):
            view["subtitle_cues"] = []
            view["subtitle_capability"] = "unavailable"
            view["subtitle_reason"] = "Subtitle bertimestamp tidak tersedia"
        view["watermark_url"] = ""
        view["watermark_revision"] = ""
        view["resolved_credit_text"] = self._resolve_credit_text(self._render_settings({}, meta, require_gaming_roi=False)["credit_watermark"].get("text", ""), meta.get("channel_name", ""))
        return {"status": "ok", "clip": view, "defaults": self._editor_defaults()}

    @staticmethod
    def _resolve_credit_text(template, channel):
        text = str(template or "").replace("{channel}", str(channel or ""))
        return re.sub(r"\s+", " ", re.sub(r"\s*[:,-]\s*$", "", text)).strip()

    def _editor_defaults_local(self):
        return editor_defaults()

    def _editor_defaults(self):
        defaults = self._editor_defaults_local()
        mode = self._config().config.get("video_layout", {}).get("mode", "normal")
        defaults["video_layout"] = {"mode": mode if mode in {"normal", "gaming"} else "normal"}
        return defaults

    def _render_settings(self, payload, metadata, require_gaming_roi=True):
        """Return locked V3 visuals; client may choose layout/ROI, never style."""
        supplied = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
        stored = metadata.get("render_settings") if isinstance(metadata.get("render_settings"), dict) else {}
        draft = metadata.get("draft_settings") if isinstance(metadata.get("draft_settings"), dict) else {}
        selected = supplied or stored
        selected_layout = selected.get("video_layout") if isinstance(selected.get("video_layout"), dict) else {}
        mode = str(selected_layout.get("mode") or metadata.get("v3_mode") or self._v3_mode or "normal")
        if mode == "vertical_full":
            mode = "normal"
        if mode not in {"normal", "gaming", "split_middle"}:
            mode = "normal"
        locked_input = {"video_layout": {"mode": mode, **selected_layout}}
        settings = v3_locked_render_settings(locked_input)
        settings["video_quality"] = str(
            selected.get("video_quality")
            or draft.get("video_quality")
            or metadata.get("video_quality")
            or stored.get("video_quality")
            or self._config().config.get("video_quality")
            or "720"
        )
        if settings["video_quality"] not in SUPPORTED_VIDEO_QUALITIES:
            raise LayoutModeError("Kualitas video harus 480, 720, 1080, atau 1440")
        settings["screen_size"] = "9:16"
        settings["landscape_blur"] = False
        settings["watermark"]["enabled"] = False
        settings["blur_background"]["enabled"] = False
        if mode == "gaming":
            detected = metadata.get("gaming_detection") if isinstance(metadata.get("gaming_detection"), dict) else {}
            roi_source = selected_layout if all(key in selected_layout for key in ("facecam_x", "facecam_y", "facecam_width", "facecam_height")) else detected.get("facecam")
            roi = validate_roi({
                "x": roi_source.get("facecam_x", roi_source.get("x")),
                "y": roi_source.get("facecam_y", roi_source.get("y")),
                "width": roi_source.get("facecam_width", roi_source.get("width")),
                "height": roi_source.get("facecam_height", roi_source.get("height")),
            } if isinstance(roi_source, dict) else None)
            if not roi:
                if require_gaming_roi:
                    raise GamingLayoutError(FACE_NOT_FOUND_MESSAGE)
                return settings
            confidence = self._as_float(selected_layout.get("facecam_confidence", detected.get("confidence")), 0.0)
            settings["video_layout"].update(
                facecam_x=roi["x"], facecam_y=roi["y"],
                facecam_width=roi["width"], facecam_height=roi["height"],
                facecam_confidence=max(0.0, min(1.0, confidence)),
            )
        return settings

    def _auto_render_run(self, run_dir):
        """Render each staged clip independently. Source/transcript/TTS caches are reused."""
        results = []
        for meta_path in sorted(Path(run_dir).rglob("data.json")):
            metadata = self._read_json(meta_path)
            clip_id = str(metadata.get("clip_id") or "")
            if not clip_id or metadata.get("status") == "needs_facecam":
                continue
            if (meta_path.parent / "master.mp4").is_file() and metadata.get("status") == "ready_to_schedule":
                results.append({"clip_id": clip_id, "status": "cached"})
                continue
            output = meta_path.parent / "master.auto.tmp.mp4"
            try:
                settings = self._render_settings({}, metadata)
                metadata.update(
                    status="rendering", render_error="", render_stage="Merender final",
                    render_progress=0.0, render_started_at=datetime.now(timezone.utc).isoformat(),
                )
                self._write_json_atomic(meta_path, metadata)

                def persist_progress(stage, progress=None):
                    with self._clip_lock(clip_id):
                        current = self._read_json(meta_path)
                        if current.get("status") != "rendering":
                            return
                        current["render_stage"] = self._public_text(stage)[:120]
                        if progress is not None:
                            current["render_progress"] = max(0.0, min(1.0, self._as_float(progress, 0.0)))
                        self._write_json_atomic(meta_path, current)

                renderer = LocalClipRenderer(
                    ffmpeg_path=get_ffmpeg_path(), output_dir=str(meta_path.parent.parent),
                    watermark_settings=settings["watermark"], credit_watermark_settings=settings["credit_watermark"],
                    hook_style_settings={**settings["hook_style"], "blur_background": settings["blur_background"]},
                    subtitle_style=settings["subtitle"], video_quality=str(settings.get("video_quality") or "720"), landscape_blur=False,
                    screen_size="9:16", progress_callback=persist_progress,
                    cancel_check=lambda: self._cancel_requested, **self._hook_tts_config(),
                )
                renderer.render_existing_clip(meta_path.parent, metadata, settings, output, preview=False)
                if not output.is_file() or output.stat().st_size < 1000:
                    raise RuntimeError("Final render gagal")
                os.replace(output, meta_path.parent / "master.mp4")
                metadata.update(status="ready_to_schedule", render_error="", render_stage="Selesai", render_progress=1.0, render_revision=int(metadata.get("render_revision", 0)) + 1)
                self._write_json_atomic(meta_path, metadata)
                results.append({"clip_id": clip_id, "status": "ready_to_schedule"})
            except Exception as exc:
                output.unlink(missing_ok=True)
                metadata.update(status="render_error", render_error=str(exc), render_stage="Render gagal", render_progress=0.0)
                self._write_json_atomic(meta_path, metadata)
                self._add_log(f"Clip {clip_id[:8]} render failed: {exc}", "Error")
                results.append({"clip_id": clip_id, "status": "render_error", "error": str(exc)})
        return results

    def detect_gaming_facecam(self, payload):
        if not isinstance(payload, dict):
            return {"status": "error", "message": "Payload deteksi tidak valid"}
        clip_id = str(payload.get("clip_id") or "")
        lock, meta_path, metadata = self._locked_clip_meta(clip_id)
        try:
            if not meta_path:
                return {"status": "error", "message": "Klip tidak ditemukan"}
            source = meta_path.parent / "source.mp4"
            identity = {**self._file_identity(source), "detector_version": DETECTOR_VERSION}
            cached = metadata.get("gaming_detection") if isinstance(metadata.get("gaming_detection"), dict) else {}
            if not self._as_bool(payload.get("force"), False) and cached.get("source") == identity and validate_roi(cached.get("facecam")):
                return {"status": "ok", "facecam": cached["facecam"], "confidence": cached.get("confidence", 0.0), "cached": True}
            try:
                detected = detect_facecam(source)
            except GamingLayoutError as exc:
                metadata.pop("gaming_detection", None)
                self._write_json_atomic(meta_path, metadata)
                return {"status": "error", "message": str(exc)}
            facecam = {key: detected[key] for key in ("x", "y", "width", "height")}
            metadata["gaming_detection"] = {"source": identity, "facecam": facecam, "confidence": detected["confidence"]}
            self._write_json_atomic(meta_path, metadata)
            return {"status": "ok", "facecam": facecam, "confidence": detected["confidence"], "cached": False}
        finally:
            lock.release()

    def prepare_gaming_layout(self, clip_id, minimum_confidence=0.62):
        """Run facecam detect; mark needs_facecam on low confidence so job survives restart."""
        lock, meta_path, metadata = self._locked_clip_meta(str(clip_id or ""))
        try:
            if not meta_path:
                return {"status": "error", "message": "Klip tidak ditemukan"}
            source = meta_path.parent / "source.mp4"
            if not source.is_file():
                return {"status": "error", "message": "Source klip tidak ditemukan"}
            identity = {**self._file_identity(source), "detector_version": DETECTOR_VERSION}
            try:
                detected = detect_facecam(source, minimum_confidence=minimum_confidence)
            except GamingLayoutError as exc:
                metadata["status"] = "needs_facecam"
                metadata["layout_error"] = str(exc)
                metadata.pop("gaming_detection", None)
                self._write_json_atomic(meta_path, metadata)
                return {"status": "needs_facecam", "message": str(exc), "clip_id": clip_id}
            facecam = {key: detected[key] for key in ("x", "y", "width", "height")}
            if not validate_facecam_overlap(facecam, detected["source_width"], detected["source_height"]):
                # Still usable if gameplay_crop shifts; store but flag low confidence path for manual if needed
                pass
            metadata["gaming_detection"] = {
                "source": identity,
                "facecam": facecam,
                "confidence": detected["confidence"],
            }
            metadata["status"] = "needs_edit" if metadata.get("status") == "needs_facecam" else metadata.get("status", "needs_edit")
            metadata.pop("layout_error", None)
            self._write_json_atomic(meta_path, metadata)
            return {
                "status": "ok",
                "facecam": facecam,
                "confidence": detected["confidence"],
                "clip_id": clip_id,
            }
        finally:
            lock.release()

    def submit_facecam_roi(self, payload):
        """Accept manual facecam ROI for needs_facecam clips. No filesystem paths from client."""
        if not isinstance(payload, dict):
            return {"status": "error", "message": "Payload facecam tidak valid"}
        clip_id = str(payload.get("clip_id") or "")
        lock, meta_path, metadata = self._locked_clip_meta(clip_id)
        should_render = False
        response = None
        try:
            if not meta_path:
                return {"status": "error", "message": "Klip tidak ditemukan"}
            if metadata.get("status") not in {"needs_facecam", "needs_edit", "render_error"}:
                return {"status": "error", "message": "Klip tidak menunggu pemilihan facecam"}
            source = meta_path.parent / "source.mp4"
            if not source.is_file():
                return {"status": "error", "message": "Source klip tidak ditemukan"}
            roi = validate_roi({
                "x": payload.get("x", payload.get("facecam_x")),
                "y": payload.get("y", payload.get("facecam_y")),
                "width": payload.get("width", payload.get("facecam_width")),
                "height": payload.get("height", payload.get("facecam_height")),
            })
            if not roi:
                return {"status": "error", "message": "ROI facecam tidak valid"}
            geometry = metadata.get("source_geometry") if isinstance(metadata.get("source_geometry"), dict) else self._source_geometry(source)
            source_w = int(geometry.get("width") or 0)
            source_h = int(geometry.get("height") or 0)
            if source_w <= 0 or source_h <= 0:
                return {"status": "error", "message": "Geometry source tidak tersedia"}
            if source_w <= source_h:
                return {"status": "error", "message": "Mode gaming hanya mendukung source landscape."}
            if not validate_facecam_overlap(roi, source_w, source_h):
                return {"status": "error", "message": "Facecam overlap area gameplay tengah. Geser ke tepi frame."}
            identity = {**self._file_identity(source), "detector_version": DETECTOR_VERSION}
            confidence = max(0.0, min(1.0, self._as_float(payload.get("confidence"), 1.0)))
            metadata["gaming_detection"] = {
                "source": identity,
                "facecam": roi,
                "confidence": confidence,
                "manual": True,
            }
            # V3: ROI saved → queue final render immediately
            if metadata.get("status") == "needs_facecam":
                metadata["status"] = "needs_edit"
            metadata.pop("layout_error", None)
            self._write_json_atomic(meta_path, metadata)
            should_render = True
            response = {"status": "ok", "facecam": roi, "confidence": confidence, "clip_status": metadata["status"]}
        finally:
            lock.release()
        if should_render and response is not None:
            render_result = self.render_clip({
                "clip_id": clip_id,
                "settings": {
                    "video_layout": {
                        "mode": "gaming",
                        "facecam_x": response["facecam"]["x"],
                        "facecam_y": response["facecam"]["y"],
                        "facecam_width": response["facecam"]["width"],
                        "facecam_height": response["facecam"]["height"],
                        "facecam_confidence": response["confidence"],
                    }
                },
            }, preview=False)
            response["render"] = render_result
            if render_result.get("status") in {"queued", "cached"}:
                response["clip_status"] = "render_queued" if render_result.get("status") == "queued" else response["clip_status"]
            elif render_result.get("status") == "error":
                response["message"] = render_result.get("message") or "ROI disimpan, render gagal diantrikan"
            return response
        return response or {"status": "error", "message": "Payload facecam tidak valid"}

    def extract_clip_frame(self, clip_id, seek_seconds=0.0):
        """Return JPEG bytes for source frame at seek time. Ownership via _clip_meta."""
        meta_path, metadata = self._clip_meta(str(clip_id or ""))
        if not meta_path:
            return None, "Klip tidak ditemukan"
        source = meta_path.parent / "source.mp4"
        if not source.is_file():
            return None, "Source klip tidak ditemukan"
        try:
            seek = float(seek_seconds)
        except (TypeError, ValueError):
            return None, "Waktu frame tidak valid"
        if seek != seek or seek in (float("inf"), float("-inf")):  # NaN/inf
            return None, "Waktu frame tidak valid"
        seek = max(0.0, seek)
        duration = self._as_float(metadata.get("duration_seconds"), 0.0)
        if duration > 0:
            seek = min(seek, max(0.0, duration - 0.05))
        else:
            seek = min(seek, 3600.0)
        import tempfile
        from clipper_ffmpeg import _FFMPEG_PROCESS_LOCK
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
            target = Path(handle.name)
        try:
            cmd = [
                get_ffmpeg_path(), "-y",
                "-ss", f"{seek:.3f}",
                "-i", str(source),
                "-frames:v", "1",
                "-q:v", "3",
                str(target),
            ]
            with _FFMPEG_PROCESS_LOCK:
                result = subprocess.run(cmd, capture_output=True, timeout=20)
            if result.returncode != 0 or not target.is_file() or target.stat().st_size < 32:
                return None, "Frame gagal diekstrak"
            return target.read_bytes(), None
        except (OSError, subprocess.SubprocessError):
            return None, "Frame gagal diekstrak"
        finally:
            target.unlink(missing_ok=True)

    def render_clip(self, payload, preview=False):
        if preview:
            return {"status": "error", "message": "Preview akurat dihapus di V3. Gunakan render final."}
        clip_id = str(payload.get("clip_id") or "")
        lock, meta_path, metadata = self._locked_clip_meta(clip_id)
        try:
            if not meta_path:
                return {"status": "error", "message": "Klip tidak ditemukan"}
            if metadata.get("status") not in {"needs_edit", "render_error"}:
                return {"status": "error", "message": "Klip tidak dapat dirender pada status ini"}
            try:
                settings = self._render_settings(payload, metadata)
            except GamingLayoutError as exc:
                return {"status": "error", "message": str(exc)}
            if settings["video_layout"]["mode"] == "gaming":
                detection = metadata.get("gaming_detection") if isinstance(metadata.get("gaming_detection"), dict) else {}
                current_identity = {**self._file_identity(meta_path.parent / "source.mp4"), "detector_version": DETECTOR_VERSION}
                if detection.get("source") != current_identity:
                    return {"status": "error", "message": FACE_NOT_FOUND_MESSAGE}
                geometry = metadata.get("source_geometry") if isinstance(metadata.get("source_geometry"), dict) else self._source_geometry(meta_path.parent / "source.mp4")
                if not geometry.get("is_landscape"):
                    return {"status": "error", "message": "Mode gaming hanya mendukung source landscape."}
            if settings["subtitle"].get("enabled"):
                transcript_path = self._safe_transcript_path(meta_path.parent, metadata)
                try:
                    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
                    if not transcript.get("words") and not transcript.get("segments"):
                        raise ValueError
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    return {"status": "error", "message": "Subtitle bertimestamp tidak tersedia untuk klip ini"}
            if "hook_text" in payload:
                raw = str(payload.get("hook_text") or "").strip()
                if not raw:
                    return {"status": "error", "message": "Hook text kosong"}
                from visual_style import validate_hook_text
                try:
                    metadata["hook_text"] = validate_hook_text(raw)
                except ValueError as exc:
                    return {"status": "error", "message": str(exc)}
            acquired = _GLOBAL_RENDER_LOCK.acquire(blocking=False)
            if not acquired:
                return {"status": "error", "message": "Render lain sedang berjalan"}
            if not _GLOBAL_FINAL_RENDER_LOCK.acquire(blocking=False):
                _GLOBAL_RENDER_LOCK.release()
                return {"status": "error", "message": "Render final sedang berjalan"}
            attempt_id = uuid.uuid4().hex
            base_revision = int(metadata.get("render_revision", 0))
            queued_at = datetime.now(timezone.utc).isoformat()
            self._reset_cancel_event(clip_id)
            metadata.update(status="render_queued", attempt_id=attempt_id, render_base_revision=base_revision, render_queued_at=queued_at, render_settings=settings, render_error="", render_progress=0.0, render_stage="Menunggu render", render_started_at=None, render_elapsed_seconds=0.0)
            self._write_json_atomic(meta_path, metadata)
            output = meta_path.parent / f"master.{attempt_id}.tmp.mp4"
            try:
                threading.Thread(target=self._render_clip_file, args=(meta_path, dict(metadata), settings, output, True, True), daemon=True, name=f"clip-render-{clip_id[:8]}").start()
            except Exception:
                _GLOBAL_FINAL_RENDER_LOCK.release()
                _GLOBAL_RENDER_LOCK.release()
                raise
            return {"status": "queued", "attempt_id": attempt_id}
        finally:
            lock.release()

    @staticmethod
    def _file_identity(path):
        path = Path(path)
        if not path.is_file():
            return {}
        stat = path.stat()
        return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}

    def _render_clip_file(self, meta_path, metadata, settings, output, _commit=True, render_lock_held=False):
        started = time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        attempt_id = metadata.get("attempt_id")
        base_revision = int(metadata.get("render_base_revision", metadata.get("render_revision", 0)))

        def persist_progress(stage, progress=None):
            def mutate(current):
                current["render_stage"] = self._public_text(stage)[:120]
                current["render_progress"] = max(0.0, min(1.0, self._as_float(progress, current.get("render_progress", 0.0))))
                current["render_elapsed_seconds"] = round(time.monotonic() - started, 3)
            self._cas_clip(meta_path, attempt_id, {"render_queued", "rendering"}, mutate)

        def update_render(statuses, mutate):
            if attempt_id:
                return self._cas_clip(meta_path, attempt_id, statuses, mutate)
            with self._clip_lock(metadata.get("clip_id")):
                current = self._read_json(meta_path)
                if current.get("status") not in statuses:
                    return None
                mutate(current)
                self._write_json_atomic(meta_path, current)
                return current

        try:
            claimed = update_render({"needs_edit", "render_error", "render_queued", "rendering"}, lambda current: current.update(status="rendering", render_progress=0.0, render_stage="Memulai render", render_started_at=started_at, render_elapsed_seconds=0.0))
            if claimed is None:
                return
            if self._cancel_event(metadata.get("clip_id")).is_set():
                update_render({"rendering"}, lambda current: current.update(status="cancelled", render_stage="Dibatalkan", render_error="", render_progress=0.0, render_elapsed_seconds=round(time.monotonic() - started, 3)))
                Path(output).unlink(missing_ok=True)
                return
            cancel_event = self._cancel_event(metadata.get("clip_id"))
            core = LocalClipRenderer(ffmpeg_path=get_ffmpeg_path(), output_dir=str(meta_path.parent.parent), watermark_settings=settings["watermark"], credit_watermark_settings=settings["credit_watermark"], hook_style_settings={**settings["hook_style"], "blur_background": settings["blur_background"]}, subtitle_style=settings["subtitle"], video_quality=settings["video_quality"], landscape_blur=settings["landscape_blur"], screen_size=settings["screen_size"], progress_callback=persist_progress, cancel_check=cancel_event.is_set, **self._hook_tts_config())
            if hasattr(core, "convert_to_portrait_with_progress"):
                convert_portrait = core.convert_to_portrait_with_progress
                core.convert_to_portrait_with_progress = lambda input_path, output_path, callback: convert_portrait(input_path, output_path, lambda value: (persist_progress("Menyiapkan video", value * 0.45), callback(value)))
            if hasattr(core, "run_ffmpeg_with_progress"):
                run_ffmpeg = core.run_ffmpeg_with_progress
                core.run_ffmpeg_with_progress = lambda command, duration, callback, **kwargs: run_ffmpeg(command, duration, lambda value: (persist_progress("Menyusun video final", 0.5 + value * 0.5), callback(value)), **kwargs)
            core.render_existing_clip(meta_path.parent, metadata, settings, output, preview=False)
            final = meta_path.parent / "master.mp4"
            with self._clip_lock(metadata.get("clip_id")):
                current = self._read_json(meta_path)
                if current.get("attempt_id") != attempt_id or current.get("status") != "rendering" or int(current.get("render_revision", 0)) != base_revision:
                    Path(output).unlink(missing_ok=True)
                    return
                backup = meta_path.parent / f"master.{attempt_id}.previous.mp4"
                if final.is_file():
                    shutil.copyfile(final, backup)
                try:
                    os.replace(output, final)
                    current.update(status="ready_to_schedule", render_revision=base_revision + 1, render_error="", render_progress=1.0, render_stage="Selesai", render_elapsed_seconds=round(time.monotonic() - started, 3))
                    if isinstance(metadata.get("split_person_rois"), dict):
                        current["split_person_rois"] = metadata["split_person_rois"]
                        stored_settings = current.get("render_settings")
                        if not isinstance(stored_settings, dict):
                            stored_settings = {}
                        stored_layout = stored_settings.get("video_layout")
                        if not isinstance(stored_layout, dict):
                            stored_layout = {}
                        current["render_settings"] = {
                            **stored_settings,
                            "video_layout": {
                                **stored_layout,
                                "person_rois": metadata["split_person_rois"],
                            },
                        }
                    pending = current.pop("pending_youtube_upload", None)
                    if isinstance(pending, dict):
                        pending.update(status="scheduled", render_revision=base_revision + 1)
                        current.update(status="scheduled", youtube_upload=pending)
                    self._write_json_atomic(meta_path, current)
                except Exception:
                    if backup.is_file():
                        os.replace(backup, final)
                    else:
                        final.unlink(missing_ok=True)
                    raise
                finally:
                    backup.unlink(missing_ok=True)
        except Exception as exc:
            Path(output).unlink(missing_ok=True)
            _RENDER_LOGGER.exception("final render failed for %s", metadata.get("clip_id"))
            self._add_log(f"Render final gagal: {type(exc).__name__}", level="Error")
            public_error = "Render melewati batas waktu." if isinstance(exc, TimeoutError) else "Render gagal. Periksa source klip lalu coba lagi."
            update_render({"render_queued", "rendering"}, lambda current: current.update(status="render_error", render_error=public_error, render_stage="Render gagal", render_elapsed_seconds=round(time.monotonic() - started, 3)))
        finally:
            _RENDER_LOGGER.info("final render elapsed: %.1fs", time.monotonic() - started)
            _GLOBAL_FINAL_RENDER_LOCK.release()
            if render_lock_held:
                _GLOBAL_RENDER_LOCK.release()

    def _upload_text(self, payload, metadata):
        title = str(payload.get("title") if "title" in payload else metadata.get("title") or "").strip()[:100]
        description = str(payload.get("description") if "description" in payload else metadata.get("description") or "").strip()[:5000]
        metadata.update(title=title, description=description)
        return title, description

    def schedule_clip_upload(self, payload):
        clip_id = str(payload.get("clip_id") or "")
        lock, meta_path, metadata = self._locked_clip_meta(clip_id)
        try:
            if not meta_path or metadata.get("status") != "ready_to_schedule" or not (meta_path.parent / "master.mp4").is_file():
                return {"status": "error", "message": "Klip final belum siap dijadwalkan"}
            try:
                scheduled_at = datetime.fromisoformat(str(payload.get("scheduled_at") or "").strip())
            except ValueError:
                return {"status": "error", "message": "Waktu upload tidak valid"}
            if scheduled_at.tzinfo is not None:
                scheduled_at = scheduled_at.astimezone(ZoneInfo("Asia/Jakarta")).replace(tzinfo=None)
            scheduled_utc = scheduled_at.replace(tzinfo=ZoneInfo("Asia/Jakarta")).astimezone(timezone.utc)
            now_utc = datetime.now(timezone.utc)
            min_utc = now_utc + timedelta(minutes=10)
            if scheduled_utc <= now_utc:
                return {"status": "error", "message": "Waktu upload harus setelah sekarang"}
            if scheduled_utc < min_utc:
                return {"status": "error", "message": "Jadwal minimal 10 menit dari sekarang (WIB)"}
            title, description = self._upload_text(payload, metadata)
            upload = {"status": "scheduled", "scheduled_at": scheduled_utc.isoformat(), "title": title, "description": description, "privacy": "public", "render_revision": int(metadata.get("render_revision", 0))}
            metadata.update(status="scheduled", youtube_upload=upload)
            self._write_json_atomic(meta_path, metadata)
            return {"status": "scheduled", "youtube_upload": upload}
        finally:
            lock.release()

    def cancel_clip_upload(self, payload):
        clip_id = str(payload.get("clip_id") or "")
        lock, meta_path, metadata = self._locked_clip_meta(clip_id)
        try:
            if not meta_path or metadata.get("status") != "scheduled":
                return {"status": "error", "message": "Jadwal klip tidak ditemukan"}
            metadata.pop("youtube_upload", None)
            metadata.pop("pending_youtube_upload", None)
            metadata["status"] = "ready_to_schedule"
            self._write_json_atomic(meta_path, metadata)
            return {"status": "cancelled"}
        finally:
            lock.release()

    def retry_clip_upload(self, payload):
        clip_id = str(payload.get("clip_id") or "")
        lock, meta_path, metadata = self._locked_clip_meta(clip_id)
        try:
            if not meta_path or metadata.get("status") != "upload_error":
                return {"status": "error", "message": "Upload klip tidak dapat diulang"}
            upload = dict(metadata.get("youtube_upload") or {})
            # V3: back to schedule panel only — no immediate re-upload
            metadata["status"] = "ready_to_schedule"
            metadata.pop("youtube_upload", None)
            if upload:
                metadata["pending_youtube_upload"] = {
                    "title": upload.get("title", metadata.get("title", "")),
                    "description": upload.get("description", metadata.get("description", "")),
                }
            self._write_json_atomic(meta_path, metadata)
            return {"status": "ready", "clip_status": "ready_to_schedule"}
        finally:
            lock.release()

    def _upload_claim(self, clip_id, allowed_statuses, payload=None):
        lock, meta_path, metadata = self._locked_clip_meta(clip_id)
        try:
            if not meta_path or metadata.get("status") not in set(allowed_statuses) or not (meta_path.parent / "master.mp4").is_file():
                return None
            source = dict(metadata.get("youtube_upload") or {})
            if payload is not None:
                title, description = self._upload_text(payload, metadata)
                source.update(title=title, description=description, privacy="public")
            attempt_id = uuid.uuid4().hex
            revision = int(metadata.get("render_revision", 0))
            source.update(status="uploading", attempt_id=attempt_id, uploading_at=datetime.now(timezone.utc).isoformat(), render_revision=revision, privacy="public")
            source.pop("error", None)
            metadata.update(status="uploading", attempt_id=attempt_id, youtube_upload=source)
            self._write_json_atomic(meta_path, metadata)
            return meta_path, attempt_id, revision, source
        finally:
            lock.release()

    def _complete_upload(self, meta_path, attempt_id, revision, result=None):
        clip_id = self._read_json(meta_path).get("clip_id")
        with self._clip_lock(clip_id):
            current = self._read_json(meta_path)
            upload = dict(current.get("youtube_upload") or {})
            if current.get("status") != "uploading" or current.get("attempt_id") != attempt_id or upload.get("attempt_id") != attempt_id or int(upload.get("render_revision", -1)) != revision:
                return False
            if result is None:
                upload.update(status="upload_error", error="Upload YouTube gagal. Coba lagi.")
                current.update(status="upload_error", youtube_upload=upload)
            else:
                upload.update(status="uploaded", **result, uploaded_at=datetime.now(timezone.utc).isoformat())
                current.update(status="uploaded", youtube_upload=upload)
            self._write_json_atomic(meta_path, current)
            return True

    def upload_clip_now(self, payload):
        # V3: immediate public upload removed — schedule WIB only
        return {"status": "error", "message": "Upload langsung dinonaktifkan. Jadwalkan minimal 10 menit dari sekarang (WIB)."}

    def update_hook_text(self, payload):
        """Edit hook text only, then queue locked final re-render."""
        if not isinstance(payload, dict):
            return {"status": "error", "message": "Payload hook tidak valid"}
        clip_id = str(payload.get("clip_id") or "")
        raw_hook = str(payload.get("hook_text") or "").strip()
        if not raw_hook:
            return {"status": "error", "message": "Hook text kosong"}
        from visual_style import validate_hook_text
        try:
            hook = validate_hook_text(raw_hook)
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}
        lock, meta_path, metadata = self._locked_clip_meta(clip_id)
        try:
            if not meta_path:
                return {"status": "error", "message": "Klip tidak ditemukan"}
            if metadata.get("status") not in {"ready_to_schedule", "render_error", "needs_edit", "upload_error"}:
                return {"status": "error", "message": "Hook tidak bisa diedit pada status ini"}
            if metadata.get("status") == "upload_error":
                metadata.pop("youtube_upload", None)
            metadata["hook_text"] = hook
            metadata["status"] = "needs_edit"
            self._write_json_atomic(meta_path, metadata)
        finally:
            lock.release()
        return self.render_clip({"clip_id": clip_id, "hook_text": hook}, preview=False)

    def cancel_clip_process(self, payload):
        clip_id = str(payload.get("clip_id") or "")
        lock, meta_path, metadata = self._locked_clip_meta(clip_id)
        try:
            if not meta_path or metadata.get("status") not in {"render_queued", "rendering"}:
                return {"status": "error", "message": "Proses klip tidak dapat dibatalkan"}
            self._cancel_event(clip_id).set()
            metadata.update(status="cancelled", render_stage="Dibatalkan", render_error="", render_progress=0.0)
            self._write_json_atomic(meta_path, metadata)
            for temp in meta_path.parent.glob("master.*.tmp.mp4"):
                temp.unlink(missing_ok=True)
            for temp in meta_path.parent.glob("preview-*.mp4"):
                temp.unlink(missing_ok=True)
            return {"status": "cancelled", "clip_id": clip_id}
        finally:
            lock.release()

    def delete_clip(self, payload):
        clip_id = str(payload.get("clip_id") or "")
        lock, meta_path, metadata = self._locked_clip_meta(clip_id)
        try:
            if not meta_path:
                return {"status": "error", "message": "Klip tidak ditemukan"}
            if metadata.get("status") in _ACTIVE_CLIP_STATUSES:
                return {"status": "error", "message": "Batalkan proses atau jadwal terlebih dahulu"}
            try:
                shutil.rmtree(meta_path.parent)
            except OSError:
                return {"status": "error", "message": "Klip gagal dihapus"}
            cache_key = (self.user_id or str(self.app_dir.resolve()), clip_id)
            with _CLIP_META_CACHE_GUARD:
                _CLIP_META_CACHE.pop(cache_key, None)
            with _CLIP_CANCEL_GUARD:
                _CLIP_CANCEL_EVENTS.pop(cache_key, None)
            return {"status": "deleted"}
        finally:
            lock.release()

    def _write_json_atomic(self, path, data):
        temporary = path.with_name(f"{path.stem}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            for attempt, delay in enumerate((0.01, 0.02, 0.04, 0.08, 0.16), 1):
                try:
                    os.replace(temporary, path)
                    return
                except PermissionError:
                    if attempt == 5:
                        raise
                    time.sleep(delay)
        finally:
            temporary.unlink(missing_ok=True)

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
            ai_providers = {name: dict(value) for name, value in (cfg.get("ai_providers") or {}).items()}
            if self._vault_enabled:
                highlight_key = self._vault_read_key("highlight")
                caption_key = self._vault_read_key("caption")
                hook_key = self._vault_read_key("hook")
                for name in ("highlight_finder", "youtube_title_maker"):
                    ai_providers.setdefault(name, {})["api_key"] = highlight_key
                ai_providers.setdefault("hook_maker", {})["api_key"] = hook_key
                ai_providers.setdefault("caption_maker", {})["api_key"] = caption_key
            quality = str(cfg.get("video_quality", "720"))
            ai_providers["parallel_workers"] = self._parallel_workers_for_quality(cfg.get("parallel_workers", 1), quality)
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
                ai_providers=ai_providers,
                subtitle_language=subtitle_language,
                video_quality=str(cfg.get("video_quality", "720")),
                landscape_blur=landscape_blur,
                screen_size=screen_size,
                subtitle_style=subtitle_style,
                cookies_path=str(self.core_cookie_file) if self.core_cookie_file.is_file() else None,
                cancel_check=lambda: self._cancel_requested,
                log_callback=self._set_message,
                progress_callback=self._set_progress,
                draft_only=True,
            )
            if cfg.get("gpu_acceleration", {}).get("enabled", False):
                self._add_log("GPU acceleration requested")
                core.enable_gpu_acceleration(True)
            resolution_map = {"16:9": {"480": "854x480", "720": "1280x720", "1080": "1920x1080", "1440": "2560x1440", "2160": "3840x2160"}, "9:16": {"480": "540x960", "720": "720x1280", "1080": "1080x1920", "1440": "1440x2560", "2160": "2160x3840"}}
            resolution = resolution_map.get(screen_size, resolution_map["9:16"]).get(quality, resolution_map.get(screen_size, resolution_map["9:16"])["720"])
            self._add_log(f"Video quality: {quality}p")
            self._add_log(f"Output resolution: {resolution}")
            self._add_log(f"Screen size: {screen_size}")
            self._add_log(f"Landscape blur: {'on' if landscape_blur else 'off'}")
            self._add_log("Processor started")
            core.process(url, num_clips=num_clips, add_captions=add_captions, add_hook=add_hook)
            if self._cancel_requested:
                raise InterruptedError("Stopped")
            layout_mode = getattr(self, "_v3_mode", None) or str(cfg.get("video_layout", {}).get("mode", "normal"))
            if layout_mode == "normal":
                layout_mode = "vertical_full"
            if layout_mode not in V3_MODES and layout_mode != "gaming":
                layout_mode = "vertical_full"
            for meta_path in sorted(run_dir.rglob("data.json")):
                meta = self._read_json(meta_path)
                if not meta.get("clip_id"):
                    continue
                meta["v3_mode"] = layout_mode
                stored = meta.get("render_settings")
                if not isinstance(stored, dict):
                    stored = {}
                layout = stored.get("video_layout")
                if not isinstance(layout, dict):
                    layout = {}
                mode_for_render = "normal" if layout_mode == "vertical_full" else layout_mode
                quality = str(cfg.get("video_quality") or "720")
                meta["video_quality"] = quality
                draft = meta.get("draft_settings")
                if not isinstance(draft, dict):
                    draft = {}
                meta["draft_settings"] = {**draft, "video_quality": quality, "screen_size": "9:16"}
                meta["render_settings"] = {
                    **stored,
                    "video_quality": quality,
                    "video_layout": {**layout, "mode": mode_for_render},
                }
                self._write_json_atomic(meta_path, meta)
            if layout_mode == "gaming":
                for meta_path in sorted(run_dir.rglob("data.json")):
                    meta = self._read_json(meta_path)
                    clip_id = meta.get("clip_id")
                    if not clip_id:
                        continue
                    result = self.prepare_gaming_layout(clip_id)
                    if result.get("status") == "needs_facecam":
                        self._add_log(f"Facecam low confidence for {clip_id[:8]}… — awaiting manual ROI")
                    elif result.get("status") == "ok":
                        self._add_log(f"Facecam auto-detected for {clip_id[:8]}… conf={result.get('confidence', 0):.2f}")
            # V3: auto final render after analysis (skip needs_edit editor stage)
            if not self._cancel_requested:
                self._add_log("Auto-rendering final clips…")
                self._auto_render_run(run_dir)
            self._write_run_meta(run_dir, url, {**self._summarize_run(run_dir), "video_quality": quality, "landscape_blur": False, "screen_size": "9:16", "add_hook": True, "add_captions": True, "subtitle_language": subtitle_language, "status": "staged", "file_exists": True, "v3_mode": layout_mode})
            self._enforce_clip_limit()
            self._status = "complete"
            self._message = "Complete"
            self._progress = 1.0
            self._add_log("Complete", "Done")
        except InterruptedError:
            if self._timed_out:
                self._status = "error"
                self._message = "Processing timed out"
                self._error = "Job exceeded time limit"
                self._add_log("Job exceeded time limit", "Error")
            else:
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
            with self._lock:
                self.thread = None
                self._job_start_time = None

    def _config(self):
        return ConfigManager(self.config_file, self.output_dir)

    def _output_root(self):
        return self.output_dir

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
            clip_states = {self._read_json(path).get("status") for path in folder.rglob("data.json")}
            if clip_states & _ACTIVE_CLIP_STATUSES:
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

    def _enforce_clip_limit(self, limit=15):
        clips = []
        for meta_path in self._output_root().glob("*/**/data.json"):
            metadata = self._read_json(meta_path)
            if metadata.get("clip_id") and metadata.get("status") not in _ACTIVE_CLIP_STATUSES:
                created = str(metadata.get("created_at") or metadata.get("timestamp") or "")
                clips.append((created, meta_path.stat().st_mtime, str(metadata["clip_id"]), meta_path))
        all_count = sum(1 for path in self._output_root().glob("*/**/data.json") if self._read_json(path).get("clip_id"))
        for _, _, clip_id, meta_path in sorted(clips)[:max(0, all_count - limit)]:
            with self._clip_lock(clip_id):
                current = self._read_json(meta_path)
                if current.get("status") in _ACTIVE_CLIP_STATUSES:
                    continue
                try:
                    shutil.rmtree(meta_path.parent)
                except OSError:
                    continue
                cache_key = (self.user_id or str(self.app_dir.resolve()), clip_id)
                with _CLIP_META_CACHE_GUARD:
                    _CLIP_META_CACHE.pop(cache_key, None)

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
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if number != number or number in (float("inf"), float("-inf")):
            return default
        return number

    def _as_int(self, value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _as_color(self, value, default):
        color = str(value or "").strip()
        return color.upper() if re.fullmatch(r"#[0-9A-Fa-f]{6}", color) else default

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
