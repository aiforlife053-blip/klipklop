import json
import mimetypes
import os
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if sys.version_info < (3, 11) and os.name == "nt" and os.environ.get("KLIPKLOP_PY_REEXEC") != "1":
    env = dict(os.environ, KLIPKLOP_PY_REEXEC="1")
    try:
        raise SystemExit(subprocess.call(["py", "-3.12", str(Path(__file__).resolve())], env=env))
    except FileNotFoundError:
        raise SystemExit("Python 3.11+ required. Run: py -3.12 server.py")

from job_manager import WebJobManager
from social_auth import get_youtube_credentials, is_youtube_connected, start_youtube_oauth, check_youtube_oauth_status, TOKEN_FILE
from youtube_uploader import delete_youtube_video, list_existing_youtube_videos, upload_youtube_video


MANAGER = WebJobManager()


class WebKlipHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self._json(MANAGER.status())
        elif parsed.path == "/api/settings":
            self._json(MANAGER.get_settings())
        elif parsed.path == "/api/outputs":
            self._json(MANAGER.list_outputs())
        elif parsed.path == "/api/download":
            self._download(parsed.query)
        elif parsed.path == "/api/social/status":
            self._json(is_youtube_connected())
        elif parsed.path == "/api/activity":
            self._json(MANAGER.list_activities())
        else:
            self._static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)

        # Different endpoints have different payload size limits
        if parsed.path == "/api/settings":
            payload, err = self._payload(max_size=65536)  # 64KB
        elif parsed.path == "/api/cookies":
            payload, err = self._payload(max_size=524288)  # 512KB
        elif parsed.path in ["/api/start", "/api/delete", "/api/save"]:
            payload, err = self._payload(max_size=16384)  # 16KB
        else:
            payload, err = self._payload(max_size=65536)  # 64KB default

        if err is not None:
            self._json(err[0], err[1])
            return
        if parsed.path == "/api/settings":
            self._json(MANAGER.save_settings(payload))
        elif parsed.path == "/api/cookies":
            self._json(MANAGER.save_cookies(payload.get("content", payload.get("cookie_text", ""))))
        elif parsed.path == "/api/start":
            result = MANAGER.start(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif parsed.path == "/api/delete":
            result = MANAGER.delete_output(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif parsed.path == "/api/save":
            result = MANAGER.save_output(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif parsed.path in {"/api/logs/clear", "/api/clear-logs", "/api/clear_logs"}:
            self._json(MANAGER.clear_logs())
        elif parsed.path == "/api/activity":
            result = MANAGER.log_activity(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif parsed.path == "/api/activity/clear":
            self._json(MANAGER.clear_activities())
        elif parsed.path == "/api/social/youtube/connect":
            try:
                result = start_youtube_oauth()
                self._json(result)
            except Exception as e:
                self._json({"status": "error", "message": str(e)}, 400)
        elif parsed.path == "/api/social/youtube/oauth-status":
            try:
                result = check_youtube_oauth_status()
                self._json(result)
            except Exception as e:
                self._json({"status": "error", "message": str(e)}, 400)
        elif parsed.path == "/api/social/youtube/disconnect":
            import os
            if os.path.exists(TOKEN_FILE):
                os.remove(TOKEN_FILE)
            self._json({"status": "ok"})
        elif parsed.path == "/api/social/youtube/upload":
            self._upload_youtube(payload)
        elif parsed.path == "/api/social/youtube/check":
            try:
                self._json({"status": "ok", "existing": list_existing_youtube_videos(payload.get("video_ids") or [])})
            except Exception as e:
                self._json({"status": "error", "message": str(e)}, 400)
        elif parsed.path == "/api/social/youtube/delete":
            try:
                result = {"status": "ok", **delete_youtube_video(str(payload.get("video_id") or ""))}
                MANAGER.log_activity({"action": "youtube_delete", "detail": result.get("video_id", "")})
                self._json(result)
            except Exception as e:
                self._json({"status": "error", "message": str(e)}, 400)
        else:
            self._json({"status": "error", "message": "Not found"}, 404)

    def _upload_youtube(self, payload):
        target = Path(str(payload.get("path", ""))).resolve()
        output_root = Path(MANAGER.get_settings()["output_dir"] or str(MANAGER.output_dir)).resolve()
        if not target.exists() or output_root not in target.parents or target.suffix.lower() not in {".mp4", ".webm", ".mkv", ".mov", ".avi"}:
            self._json({"status": "error", "message": "File video tidak ditemukan"}, 400)
            return
        title = str(payload.get("title") or target.stem).strip()
        description = str(payload.get("description") or "").strip()
        privacy = str(payload.get("privacy") or "private").strip()
        try:
            result = upload_youtube_video(target, title, description, privacy)
            MANAGER.log_activity({"action": "youtube_upload", "detail": result.get("video_id", target.name)})
            self._json({"status": "ok", **result})
        except Exception as e:
            self._json({"status": "error", "message": str(e)}, 400)

    def log_message(self, fmt, *args):
        return

    def _payload(self, max_size=65536):
        """Parse JSON payload with size limit. Default 64KB, can be overridden.
        Returns tuple: (payload_dict, error_response_tuple_or_None)
        If error is not None, caller should send the error and return.
        """
        try:
            size = int(self.headers.get("content-length", "0") or 0)
        except ValueError:
            return None, ({"status": "error", "message": "Invalid content-length"}, 400)
        if size > max_size:
            return None, ({"status": "error", "message": f"Payload too large (max {max_size} bytes)"}, 413)
        if size <= 0:
            return {}, None
        try:
            return json.loads(self.rfile.read(size).decode("utf-8")), None
        except json.JSONDecodeError:
            return None, ({"status": "error", "message": "Invalid JSON"}, 400)

    def _json(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._add_security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _add_security_headers(self):
        """Add security headers to all responses"""
        # CSP: allow self, inline styles (Tailwind), external fonts/scripts (CDN)
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob:; "
            "media-src 'self' blob:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("X-Frame-Options", "DENY")

    def _static(self, path):
        """Serve static files with allowlist for security"""
        # Allowlist: only serve specific safe files
        rel = "index.html" if path in {"", "/"} else unquote(path).lstrip("/")

        # Security: block dangerous file extensions
        blocked_exts = {".py", ".json", ".md", ".txt", ".log", ".cfg", ".ini", ".env", ".yml", ".yaml"}
        if any(rel.lower().endswith(ext) for ext in blocked_exts):
            self._json({"status": "error", "message": "Forbidden"}, 403)
            return

        target = (ROOT / rel).resolve()
        if target != ROOT and ROOT not in target.parents:
            self._json({"status": "error", "message": "Forbidden"}, 403)
            return
        if not target.exists() or not target.is_file():
            self._json({"status": "error", "message": "Not found"}, 404)
            return

        # Cache control: no-store for HTML (sensitive), immutable for static assets
        content_type, _ = mimetypes.guess_type(str(target))
        if content_type is None:
            content_type = "application/octet-stream"

        raw = target.read_bytes()
        self.send_response(200)
        self._add_security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))

        # Cache rules
        if target.suffix == ".html":
            self.send_header("Cache-Control", "no-store")
        elif target.suffix in {".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2"}:
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")

        self.end_headers()
        self.wfile.write(raw)

    def _download(self, query):
        path = parse_qs(query, keep_blank_values=True).get("path", [""])[0]
        if not path:
            self._json({"status": "error", "message": "Missing path"}, 400)
            return
        target = Path(path).resolve()
        output_root = Path(MANAGER.get_settings()["output_dir"] or str(MANAGER.output_dir)).resolve()
        allowed = {".mp4", ".webm", ".mkv", ".mov", ".avi", ".mp3", ".wav", ".json", ".srt", ".ass", ".txt", ".vtt"}
        if not target.exists() or output_root not in target.parents or target.suffix.lower() not in allowed:
            self._json({"status": "error", "message": "File not found"}, 404)
            return
        raw = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main():
    host = os.environ.get("KLIPKLOP_HOST", "127.0.0.1")
    port = int(os.environ.get("KLIPKLOP_PORT", "8765"))
    security_mode = os.environ.get("SECURITY_MODE", "local")

    # Startup guard: refuse to bind to non-localhost without explicit public mode
    if host != "127.0.0.1" and security_mode != "public":
        raise SystemExit(
            f"SECURITY ERROR: Cannot bind to {host} without SECURITY_MODE=public.\n"
            f"Set SECURITY_MODE=public environment variable to allow non-localhost binding.\n"
            f"Current mode: {security_mode}"
        )

    url = f"http://{host}:{port}"
    server = ThreadingHTTPServer((host, port), WebKlipHandler)
    print(f"KlipKlop Web running at {url}")
    print(f"Security mode: {security_mode}")
    webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
