import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clipper_core import AutoClipperCore
from config.config_manager import ConfigManager
from utils.helpers import get_app_dir, get_ffmpeg_path, get_ytdlp_path


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
GEMINI_MODEL = "gemini-2.0-flash"


class WebJobManager:
    def __init__(self, app_dir=None):
        self.app_dir = Path(app_dir) if app_dir else get_app_dir()
        self.output_dir = self.app_dir / "output"
        self.config_file = self.app_dir / "config.json"
        self.cookie_file = self.app_dir / "cookie.txt"
        self.core_cookie_file = self.app_dir / "cookies.txt"
        self.thread = None
        self._status = "idle"
        self._message = "Idle"
        self._progress = 0.0
        self._error = ""

    def start(self, payload):
        url = str(payload.get("url", "")).strip()
        if not self._is_url(url):
            return {"status": "error", "message": "URL YouTube wajib diisi"}
        if self.thread and self.thread.is_alive():
            return {"status": "busy", "message": "Processing is already running"}

        num_clips = int(payload.get("num_clips", 3) or 3)
        add_captions = bool(payload.get("add_captions", True))
        add_hook = bool(payload.get("add_hook", False))
        subtitle_language = str(payload.get("subtitle_language", "id") or "id")
        instruction = str(payload.get("instruction", "")).strip()

        self._status = "running"
        self._message = "Starting"
        self._progress = 0.0
        self._error = ""
        self.thread = threading.Thread(
            target=self._run,
            args=(url, num_clips, add_captions, add_hook, subtitle_language, instruction),
            daemon=True,
        )
        self.thread.start()
        return {"status": "started"}

    def status(self):
        return {
            "status": self._status,
            "message": self._message,
            "progress": self._progress,
            "error": self._error,
        }

    def get_settings(self):
        cfg = self._config().config
        provider = cfg.get("ai_providers", {}).get("highlight_finder", {})
        return {
            "base_url": provider.get("base_url", cfg.get("base_url", GEMINI_BASE_URL)),
            "api_key": "",
            "model": provider.get("model", cfg.get("model", GEMINI_MODEL)),
            "subtitle_language": cfg.get("subtitle_language", "id"),
            "output_dir": cfg.get("output_dir", str(self.output_dir)),
            "cookies": self.cookie_status(),
        }

    def save_settings(self, payload):
        cfg_mgr = self._config()
        base_url = str(payload.get("base_url", GEMINI_BASE_URL)).strip() or GEMINI_BASE_URL
        api_key = str(payload.get("api_key", "")).strip()
        model = str(payload.get("model", GEMINI_MODEL)).strip() or GEMINI_MODEL
        output_dir = str(payload.get("output_dir", cfg_mgr.config.get("output_dir", str(self.output_dir)))).strip() or str(self.output_dir)
        subtitle_language = str(payload.get("subtitle_language", "id") or "id")
        providers = cfg_mgr.config.setdefault("ai_providers", {})
        highlight = providers.setdefault("highlight_finder", {})
        highlight["base_url"] = base_url
        if api_key:
            highlight["api_key"] = api_key
        highlight["model"] = model
        cfg_mgr.config["base_url"] = base_url
        if api_key:
            cfg_mgr.config["api_key"] = api_key
        cfg_mgr.config["model"] = model
        cfg_mgr.config["subtitle_language"] = subtitle_language
        cfg_mgr.config["output_dir"] = output_dir
        cfg_mgr.save()
        return {"status": "saved"}

    def save_cookies(self, content):
        text = str(content or "").strip()
        if not text:
            return {"status": "error", "message": "cookie.txt kosong"}
        self.cookie_file.write_text(text + "\n", encoding="utf-8")
        self._sync_core_cookie_file()
        return {"status": "saved", "cookies": self.cookie_status()}

    def cookie_status(self):
        return {"exists": self.cookie_file.exists(), "path": str(self.cookie_file)}

    def _sync_core_cookie_file(self):
        if self.cookie_file.exists():
            self.core_cookie_file.write_text(self.cookie_file.read_text(encoding="utf-8"), encoding="utf-8")

    def list_outputs(self):
        output_value = str(self._config().config.get("output_dir", str(self.output_dir))).strip() or str(self.output_dir)
        output_dir = Path(output_value)
        files = []
        if output_dir.exists():
            for path in sorted(output_dir.rglob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
                if path.is_file() and path.suffix.lower() in {".mp4", ".json", ".srt", ".ass", ".txt"}:
                    files.append({"name": path.name, "path": str(path), "size": path.stat().st_size})
        return {"files": files[:50]}

    def _run(self, url, num_clips, add_captions, add_hook, subtitle_language, instruction):
        try:
            self._sync_core_cookie_file()
            cfg = self._config().config
            prompt = self._with_indonesian_instruction(cfg.get("system_prompt"), instruction)
            core = AutoClipperCore(
                client=None,
                ffmpeg_path=get_ffmpeg_path(),
                ytdlp_path=get_ytdlp_path(),
                output_dir=str(cfg.get("output_dir", str(self.output_dir))).strip() or str(self.output_dir),
                model=cfg.get("model", GEMINI_MODEL),
                tts_model=cfg.get("tts_model", "tts-1"),
                temperature=cfg.get("temperature", 1.0),
                system_prompt=prompt,
                watermark_settings=cfg.get("watermark", {"enabled": False}),
                credit_watermark_settings=cfg.get("credit_watermark", {"enabled": False}),
                hook_style_settings=cfg.get("hook_style", {}),
                face_tracking_mode=cfg.get("face_tracking_mode", "opencv"),
                mediapipe_settings=cfg.get("mediapipe_settings", {}),
                ai_providers=cfg.get("ai_providers"),
                subtitle_language=subtitle_language,
                log_callback=self._set_message,
                progress_callback=self._set_progress,
            )
            if cfg.get("gpu_acceleration", {}).get("enabled", False):
                core.enable_gpu_acceleration(True)
            core.process(url, num_clips=num_clips, add_captions=add_captions, add_hook=add_hook)
            self._status = "complete"
            self._message = "Complete"
            self._progress = 1.0
        except Exception as exc:
            self._status = "error"
            self._message = "Processing failed"
            self._error = str(exc)
        finally:
            self.thread = None

    def _config(self):
        return ConfigManager(self.config_file, self.output_dir)

    def _set_message(self, message):
        self._message = str(message)

    def _set_progress(self, stage, progress=None):
        value = progress if progress is not None else stage
        try:
            self._progress = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            self._progress = 0.0

    def _with_indonesian_instruction(self, prompt, instruction):
        viral = (
            "\n\nTarget user: penonton Indonesia. Pilih momen paling seru dan berpotensi viral: "
            "lucu, emosional, kontroversial ringan, edukatif singkat, quoteable, atau relatable. "
            "Gunakan Bahasa Indonesia natural, bukan terjemahan kaku."
        )
        user = f"\nArahan pengguna: {instruction}" if instruction else ""
        return f"{prompt or AutoClipperCore.get_default_prompt()}{viral}{user}"

    def _is_url(self, value):
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
