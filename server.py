import json
import mimetypes
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from job_manager import WebJobManager


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
        else:
            self._static(parsed.path)

    def do_POST(self):
        payload = self._payload()
        if payload is None:
            self._json({"status": "error", "message": "Invalid JSON"}, 400)
            return
        if self.path == "/api/settings":
            self._json(MANAGER.save_settings(payload))
        elif self.path == "/api/cookies":
            self._json(MANAGER.save_cookies(payload.get("content", payload.get("cookie_text", ""))))
        elif self.path == "/api/start":
            result = MANAGER.start(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif self.path == "/api/delete":
            result = MANAGER.delete_output(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif self.path == "/api/save":
            result = MANAGER.save_output(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        else:
            self._json({"status": "error", "message": "Not found"}, 404)

    def log_message(self, fmt, *args):
        return

    def _payload(self):
        try:
            size = int(self.headers.get("content-length", "0") or 0)
        except ValueError:
            return None
        if size <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(size).decode("utf-8"))
        except json.JSONDecodeError:
            return None

    def _json(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _static(self, path):
        rel = "index.html" if path in {"", "/"} else unquote(path).lstrip("/")
        target = (ROOT / rel).resolve()
        if target != ROOT and ROOT not in target.parents:
            self._json({"status": "error", "message": "Forbidden"}, 403)
            return
        if not target.exists() or not target.is_file():
            self._json({"status": "error", "message": "Not found"}, 404)
            return
        raw = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(raw)))
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
    host = "127.0.0.1"
    port = 8765
    url = f"http://{host}:{port}"
    server = ThreadingHTTPServer((host, port), WebKlipHandler)
    print(f"KlipKlop Web running at {url}")
    webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
