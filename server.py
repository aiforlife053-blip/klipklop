import base64
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

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
from social_auth import delete_youtube_token, finish_youtube_oauth, is_youtube_connected, start_youtube_oauth, check_youtube_oauth_status
from youtube_uploader import delete_youtube_video, list_existing_youtube_videos


MANAGER = WebJobManager()
SESSION_COOKIE = "klipklop_session"
SESSION_TTL = 86400
_LOCAL_USER_ID = "00000000-0000-4000-8000-000000000001"
_LOCAL_PASSWORD = os.environ.get("KLIPKLOP_LOCAL_PASSWORD", "admin123")
_SCHEDULER_LOGGER = logging.getLogger("web_klip.scheduler")


def _supabase_config():
    url = os.environ.get("SUPABASE_URL", "")
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    secret = os.environ.get("KLIPKLOP_SECRET") or os.environ.get("SESSION_SECRET") or ""
    return url.rstrip("/"), anon_key, secret


_USER_MANAGERS = {}
_USER_MANAGER_LAST_USED = {}
_USER_MANAGER_IDLE_SECONDS = 1800
_USER_MANAGERS_LOCK = threading.Lock()
_LOGIN_ATTEMPTS = {}
_LOGIN_LOCK = threading.Lock()


def _run_youtube_scheduler():
    while True:
        now = time.monotonic()
        with _USER_MANAGERS_LOCK:
            stale_users = [user_id for user_id, last_used in _USER_MANAGER_LAST_USED.items() if now - last_used > _USER_MANAGER_IDLE_SECONDS and not (_USER_MANAGERS[user_id].thread and _USER_MANAGERS[user_id].thread.is_alive())]
            for user_id in stale_users:
                _USER_MANAGERS.pop(user_id, None)
                _USER_MANAGER_LAST_USED.pop(user_id, None)
            cached = dict(_USER_MANAGERS)
        managers = list(cached.values())
        for folder in (ROOT / "data").iterdir() if (ROOT / "data").exists() else []:
            if not folder.is_dir() or folder.name in cached:
                continue
            needs_scheduler = False
            for meta_path in folder.glob("output/*/**/data.json"):
                try:
                    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if metadata.get("status") in {"scheduled", "uploading", "rendering", "render_queued"} or metadata.get("pending_youtube_upload"):
                    needs_scheduler = True
                    break
            if not needs_scheduler:
                continue
            try:
                managers.append(WebJobManager(folder, user_id=folder.name))
            except ValueError:
                continue
        for manager in managers:
            try:
                manager.process_due_youtube_uploads()
            except Exception as exc:
                user_label = (manager.user_id or "local")[:12]
                safe_error = manager._public_text(type(exc).__name__)[:80]
                _SCHEDULER_LOGGER.error("scheduler failed user=%s error=%s", user_label, safe_error)
        time.sleep(60)


threading.Thread(target=_run_youtube_scheduler, daemon=True, name="klipklop-youtube-scheduler").start()


def _public_mode():
    return os.environ.get("SECURITY_MODE", "local") == "public"


def _allowed_origins():
    configured = os.environ.get("ALLOWED_ORIGINS", "")
    if configured:
        return {item.strip().rstrip("/") for item in configured.split(",") if item.strip()}
    return {"http://localhost:5173", "http://127.0.0.1:5173"} if not _public_mode() else set()


class WebKlipHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/login":
            self._login_page()
            return
        if parsed.path.startswith("/static/") or parsed.path == "/logo%20klipklop.png":
            self._static(parsed.path)
            return
        if parsed.path == "/api/youtube/callback":
            self._youtube_callback(parsed.query)
            return
        if not self._authenticated():
            self._redirect_login() if not parsed.path.startswith("/api/") else self._json({"status": "error", "message": "Unauthorized"}, 401)
            return
        if parsed.path == "/api/status":
            self._json(self._manager().status())
        elif parsed.path == "/api/modes":
            from layout_modes import V3_MODES, V3_OUTPUT_WIDTH, V3_OUTPUT_HEIGHT
            self._json({"modes": list(V3_MODES), "output": {"width": V3_OUTPUT_WIDTH, "height": V3_OUTPUT_HEIGHT}})
        elif parsed.path == "/api/settings":
            self._json(self._manager().get_settings())
        elif parsed.path == "/api/clips":
            self._json(self._manager().list_clips())
        elif parsed.path == "/api/clip":
            result = self._manager().get_clip(parse_qs(parsed.query).get("clip_id", [""])[0])
            self._json(result, 404 if result.get("status") == "error" else 200)
        elif parsed.path == "/api/clip/frame":
            self._serve_clip_frame(parsed.query)
        elif parsed.path == "/api/clip/media":
            self._serve_clip_media(parsed.query)
        elif parsed.path in {"/api/download", "/api/stream"}:
            # V3: raw path= removed. Only clip_id + artifact via /api/clip/media.
            self._json({"status": "error", "message": "Gunakan /api/clip/media?clip_id=&artifact="}, 404)
        elif parsed.path == "/api/social/status":
            self._json(is_youtube_connected(self._current_user()))
        elif parsed.path == "/api/activity":
            self._json(self._manager().list_activities())
        elif parsed.path.startswith("/api/meta"):
            self._handle_api_meta()
        elif parsed.path.startswith("/api/"):
            self._json({"status": "error", "message": "API endpoint not found"}, 404)
        else:
            # Frontend is served by Vite dev server (or built dist) — not by this server
            self._json({"status": "error", "message": "Not a valid API path. Open the frontend at http://localhost:5173"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/login":
            self._login()
            return
        if parsed.path == "/api/logout":
            if not self._origin_allowed():
                self._json({"status": "error", "message": "Invalid origin"}, 403)
                return
            self._logout()
            return
        if not self._authenticated():
            self._json({"status": "error", "message": "Unauthorized"}, 401)
            return
        if not self._origin_allowed():
            self._json({"status": "error", "message": "Invalid origin"}, 403)
            return

        # Different endpoints have different payload size limits
        if parsed.path == "/api/settings":
            payload, err = self._payload(max_size=65536)  # 64KB
        elif parsed.path == "/api/cookies":
            payload, err = self._payload(max_size=10485760)  # 10MB
        elif parsed.path == "/api/start":
            payload, err = self._payload(max_size=16384)  # 16KB
        else:
            payload, err = self._payload(max_size=65536)  # 64KB default

        if err is not None:
            self._json(err[0], err[1])
            return
        if parsed.path == "/api/settings":
            self._json(self._manager().save_settings(payload))
        elif parsed.path == "/api/check-api-key":
            result = self._manager().check_ai_provider(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif parsed.path == "/api/cookies":
            self._json(self._manager().save_cookies(payload.get("content", payload.get("cookie_text", ""))))
        elif parsed.path == "/api/start":
            result = self._manager().start(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif parsed.path == "/api/clip/gaming/detect":
            result = self._manager().detect_gaming_facecam(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif parsed.path == "/api/clip/facecam":
            result = self._manager().submit_facecam_roi(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif parsed.path in {"/api/clip/render", "/api/clip/render/retry"}:
            result = self._manager().render_clip(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif parsed.path == "/api/clip/schedule":
            result = self._manager().schedule_clip_upload(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif parsed.path == "/api/clip/schedule/cancel":
            result = self._manager().cancel_clip_upload(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif parsed.path == "/api/clip/upload/retry":
            result = self._manager().retry_clip_upload(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif parsed.path == "/api/clip/upload":
            result = self._manager().upload_clip_now(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif parsed.path == "/api/clip/hook":
            result = self._manager().update_hook_text(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif parsed.path == "/api/clip/delete":
            result = self._manager().delete_clip(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif parsed.path == "/api/clip/cancel":
            result = self._manager().cancel_clip_process(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif parsed.path == "/api/stop":
            self._json(self._manager().stop())
        elif parsed.path in {"/api/logs/clear", "/api/clear-logs", "/api/clear_logs"}:
            self._json(self._manager().clear_logs())
        elif parsed.path == "/api/activity":
            result = self._manager().log_activity(payload)
            self._json(result, 400 if result.get("status") == "error" else 200)
        elif parsed.path == "/api/activity/clear":
            self._json(self._manager().clear_activities())
        elif parsed.path == "/api/social/youtube/connect":
            try:
                result = start_youtube_oauth(self._current_user())
                self._json(result)
            except Exception as e:
                self._json({"status": "error", "message": str(e)}, 400)
        elif parsed.path == "/api/social/youtube/oauth-status":
            try:
                result = check_youtube_oauth_status(self._current_user())
                self._json(result)
            except Exception as e:
                self._json({"status": "error", "message": str(e)}, 400)
        elif parsed.path == "/api/social/youtube/disconnect":
            delete_youtube_token(self._current_user())
            self._json({"status": "ok"})
        elif parsed.path == "/api/social/youtube/check":
            try:
                self._json({"status": "ok", "existing": list_existing_youtube_videos(payload.get("video_ids") or [], self._current_user())})
            except Exception as e:
                self._json({"status": "error", "message": str(e)}, 400)
        elif parsed.path == "/api/social/youtube/delete":
            try:
                result = {"status": "ok", **delete_youtube_video(str(payload.get("video_id") or ""), self._current_user())}
                self._manager().log_activity({"action": "youtube_delete", "detail": result.get("video_id", "")})
                self._json(result)
            except Exception as e:
                self._json({"status": "error", "message": str(e)}, 400)
        else:
            self._json({"status": "error", "message": "Not found"}, 404)

    def do_PUT(self):
        """Handle PUT requests — treat PUT /api/settings same as POST /api/settings"""
        parsed = urlparse(self.path)
        if not self._authenticated():
            self._json({"status": "error", "message": "Unauthorized"}, 401)
            return
        if not self._origin_allowed():
            self._json({"status": "error", "message": "Invalid origin"}, 403)
            return
        if parsed.path == "/api/settings":
            payload, err = self._payload(max_size=65536)
            if err is not None:
                self._json(err[0], err[1])
                return
            self._json(self._manager().save_settings(payload))
        else:
            self._json({"status": "error", "message": "Not found"}, 404)


    def _access_token(self):
        for part in self.headers.get("Cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == SESSION_COOKIE:
                return value
        return ""

    def _current_user(self):
        cached = getattr(self, "_user_id", None)
        if cached is not None:
            return cached
        token = self._access_token()
        url, anon_key, secret = _supabase_config()
        if not url or "YOUR_" in url or not anon_key or "YOUR_" in anon_key:
            expected = hmac.new((secret or "klipklop-local-session").encode(), _LOCAL_USER_ID.encode(), hashlib.sha256).hexdigest()
            self._user_id = _LOCAL_USER_ID if token and hmac.compare_digest(token, expected) else ""
            return self._user_id
        if not token:
            self._user_id = ""
            return ""
        request = Request(f"{url}/auth/v1/user", headers={"apikey": anon_key, "Authorization": f"Bearer {token}"})
        try:
            with urlopen(request, timeout=10) as response:
                user_id = str(__import__("uuid").UUID(str(json.loads(response.read().decode()).get("id"))))
        except Exception:
            user_id = ""
        self._user_id = user_id
        return user_id

    def _manager(self):
        user_id = self._current_user()
        if not user_id:
            raise PermissionError("Unauthorized")
        with _USER_MANAGERS_LOCK:
            local_mode = user_id == _LOCAL_USER_ID and not _supabase_config()[0]
            manager = _USER_MANAGERS.setdefault(user_id, WebJobManager(ROOT / "data" / user_id, user_id=user_id, local_mode=local_mode))
            _USER_MANAGER_LAST_USED[user_id] = time.monotonic()
            return manager

    def _origin_allowed(self):
        origin = self.headers.get("Origin", "").rstrip("/")
        return bool(origin and origin in _allowed_origins())

    def _authenticated(self):
        return bool(self._current_user())

    def _login(self):
        if not self._origin_allowed():
            self._json({"status": "error", "message": "Invalid origin"}, 403)
            return
        now = __import__("time").monotonic()
        client = self.client_address[0]
        with _LOGIN_LOCK:
            attempts = [stamp for stamp in _LOGIN_ATTEMPTS.get(client, []) if now - stamp < 300]
            if len(attempts) >= 10:
                self._json({"status": "error", "message": "Too many login attempts"}, 429)
                return
            attempts.append(now)
            _LOGIN_ATTEMPTS[client] = attempts
        payload, err = self._payload(max_size=4096)
        if err is not None:
            self._json(err[0], err[1])
            return
        url, anon_key, secret = _supabase_config()
        email = str(payload.get("email", "")).strip()
        password = str(payload.get("password", ""))
        if not email or not password:
            self._json({"status": "error", "message": "Email dan password wajib diisi"}, 400)
            return
        if not url or "YOUR_" in url or not anon_key or "YOUR_" in anon_key:
            if not hmac.compare_digest(password, _LOCAL_PASSWORD):
                self._json({"status": "error", "message": "Password lokal salah"}, 401)
                return
            token = hmac.new((secret or "klipklop-local-session").encode(), _LOCAL_USER_ID.encode(), hashlib.sha256).hexdigest()
            self._send_session(token)
            return
        req = Request(
            f"{url}/auth/v1/token?grant_type=password",
            data=json.dumps({"email": email, "password": password}).encode(),
            headers={"apikey": anon_key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=15) as res:
                data = json.loads(res.read().decode())
        except HTTPError as e:
            try:
                error_data = json.loads(e.read().decode())
                message = error_data.get("msg") or error_data.get("message")
            except Exception:
                message = "Email/password salah atau Supabase gagal"
            self._json({"status": "error", "message": message}, 401)
            return
        except Exception:
            self._json({"status": "error", "message": "Supabase gagal dihubungi"}, 401)
            return
        token = str(data.get("access_token") or "")
        if not token:
            self._json({"status": "error", "message": "Supabase did not return an access token"}, 401)
            return
        self._send_session(token)

    def _send_session(self, token):
        self.send_response(200)
        self._add_security_headers()
        secure = "; Secure" if _public_mode() else ""
        self.send_header("Set-Cookie", f"{SESSION_COOKIE}={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={SESSION_TTL}{secure}")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def _logout(self):
        self.send_response(200)
        self._add_security_headers()
        secure = "; Secure" if _public_mode() else ""
        self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0{secure}")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def _redirect_login(self):
        self.send_response(302)
        self._add_security_headers()
        self.send_header("Location", "/login")
        self.end_headers()

    def _login_page(self):
        login_file = ROOT / "login.html"
        if login_file.exists():
            raw = login_file.read_bytes()
            self.send_response(200)
            self._add_security_headers()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)
            return
        raw = '''<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Masuk KlipKlop</title><script src="https://cdn.tailwindcss.com"></script></head><body class="min-h-dvh bg-[#182231] text-white antialiased"><main class="grid min-h-dvh lg:grid-cols-[1.05fr_.95fr]"><section class="hidden lg:flex flex-col justify-between border-r border-white/10 bg-[#111827] p-10"><div class="flex items-center gap-3 font-extrabold text-2xl"><img src="/logo%20klipklop.png?v=3" class="h-10 w-10 rounded-xl object-contain" alt="KlipKlop"><span>KlipKlop</span></div><div class="max-w-xl space-y-5"><p class="text-sm font-semibold text-[#f15a24]">Creator clipping workspace</p><h1 class="text-5xl font-extrabold tracking-tight leading-tight">Masuk, generate 1 klip terbaik, upload langsung.</h1><p class="text-lg leading-8 text-slate-300">Akun dipakai untuk mengamankan dashboard, riwayat upload, dan koneksi sosial.</p></div><p class="text-sm text-slate-500">KlipKlop Web</p></section><section class="flex items-center justify-center p-6"><div class="w-full max-w-sm rounded-2xl border border-white/10 bg-[#111827] p-5 shadow-2xl shadow-black/30"><div class="mb-7 lg:hidden flex items-center gap-3 font-extrabold text-xl"><img src="/logo%20klipklop.png?v=3" class="h-9 w-9 rounded-xl object-contain" alt="KlipKlop"><span>KlipKlop</span></div><div class="mb-6"><h2 id="title" class="text-2xl font-extrabold tracking-tight">Masuk</h2><p id="subtitle" class="mt-2 text-sm text-slate-300">Lanjutkan ke dashboard KlipKlop.</p></div><div class="mb-5 grid grid-cols-2 rounded-2xl bg-[#222b3b] p-1 text-sm font-bold"><button id="tab-login" class="rounded-xl bg-[#f15a24] px-3 py-2.5 text-white transition" type="button">Masuk</button><button id="tab-signup" class="rounded-xl px-3 py-2.5 text-slate-300 transition" type="button">Daftar</button></div><form id="form" class="space-y-4"><label class="block text-sm font-semibold text-slate-200" for="email">Email</label><input id="email" class="w-full rounded-2xl bg-[#222b3b] border border-[#3a4558] px-3.5 py-3 text-sm outline-none transition focus:border-[#f15a24] focus:ring-2 focus:ring-[#f15a24]/25" placeholder="nama@email.com" type="email" autocomplete="username" required><label class="block text-sm font-semibold text-slate-200" for="password">Password</label><input id="password" class="w-full rounded-2xl bg-[#222b3b] border border-[#3a4558] px-3.5 py-3 text-sm outline-none transition focus:border-[#f15a24] focus:ring-2 focus:ring-[#f15a24]/25" placeholder="Minimal 6 karakter" type="password" autocomplete="current-password" required><p id="err" class="min-h-5 text-sm text-red-300" role="alert"></p><button id="submit" class="w-full rounded-2xl bg-[#f15a24] py-3 font-bold text-white transition hover:bg-[#ff6a33] disabled:cursor-not-allowed disabled:opacity-60">Masuk</button></form></div></section></main><script>let mode='login';function setMode(next){mode=next;const isSignup=mode==='signup';title.textContent=isSignup?'Daftar':'Masuk';subtitle.textContent=isSignup?'Buat akun baru untuk akses dashboard.':'Lanjutkan ke dashboard KlipKlop.';submit.textContent=isSignup?'Buat akun':'Masuk';tab_login.className=isSignup?'rounded-xl px-3 py-2.5 text-slate-300 transition':'rounded-xl bg-[#f15a24] px-3 py-2.5 text-white transition';tab_signup.className=isSignup?'rounded-xl bg-[#f15a24] px-3 py-2.5 text-white transition':'rounded-xl px-3 py-2.5 text-slate-300 transition'}const tab_login=document.getElementById('tab-login'),tab_signup=document.getElementById('tab-signup');tab_login.onclick=()=>setMode('login');tab_signup.onclick=()=>setMode('signup');form.onsubmit=async e=>{e.preventDefault();const email=document.getElementById('email').value.trim();const password=document.getElementById('password').value;err.textContent='';submit.disabled=true;const r=await fetch(mode==='signup'?'/api/signup':'/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});submit.disabled=false;if(r.ok) location.href='/'; else {const msg=(await r.json()).message||'Gagal';err.textContent=msg==='Email not confirmed'?'Email belum dikonfirmasi. Cek inbox Supabase atau matikan Confirm email.':msg}};</script></body></html>'''.encode("utf-8")
        self.send_response(200)
        self._add_security_headers()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _youtube_callback(self, query):
        params = parse_qs(query)
        try:
            finish_youtube_oauth(params.get("state", [""])[0], params.get("code", [None])[0], params.get("error", [None])[0])
            self._json({"status": "connected"})
        except Exception as exc:
            self._json({"status": "error", "message": str(exc)}, 400)

    def log_message(self, fmt, *args):
        return

    def log_error(self, fmt, *args):
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
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
        except json.JSONDecodeError:
            return None, ({"status": "error", "message": "Invalid JSON"}, 400)
        if not isinstance(payload, dict):
            return None, ({"status": "error", "message": "JSON payload must be an object"}, 400)
        return payload, None

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
            "img-src 'self' data: blob: https://i.ytimg.com https://*.ytimg.com; "
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

    def _handle_api_meta(self):
        query = parse_qs(urlparse(self.path).query)
        url = query.get("url", [""])[0].strip()
        if not url:
            self._json({"status": "error", "message": "Missing URL"}, 400)
            return
        host = (urlparse(url).hostname or "").lower()
        if host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
            self._json({"status": "error", "message": "URL YouTube tidak valid"}, 400)
            return

        title = author = thumbnail = ""
        width = height = 0
        try:
            req = Request(f"https://www.youtube.com/oembed?url={quote(url)}&format=json")
            with urlopen(req, timeout=5) as res:
                data = json.loads(res.read().decode())
                title = data.get("title", "") or ""
                author = data.get("author_name", "") or ""
                thumbnail = data.get("thumbnail_url", "") or ""
                width = int(data.get("width") or 0)
                height = int(data.get("height") or 0)
        except Exception:
            pass

        # Prefer yt-dlp geometry when available (oembed often lacks reliable orientation)
        try:
            from utils.helpers import get_ytdlp_path, is_ytdlp_module_available
            if is_ytdlp_module_available():
                import yt_dlp
                with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "noplaylist": True}) as ydl:
                    info = ydl.extract_info(url, download=False) or {}
                width = int(info.get("width") or width or 0)
                height = int(info.get("height") or height or 0)
                title = title or str(info.get("title") or "")
                author = author or str(info.get("uploader") or info.get("channel") or "")
                thumbnail = thumbnail or str(info.get("thumbnail") or "")
            else:
                ytdlp = get_ytdlp_path()
                if ytdlp and ytdlp != "yt_dlp_module":
                    proc = subprocess.run(
                        [ytdlp, "--skip-download", "--print", "%(width)s", "--print", "%(height)s", "--print", "%(title)s", "--print", "%(uploader)s", "--print", "%(thumbnail)s", url],
                        capture_output=True, text=True, timeout=20,
                    )
                    if proc.returncode == 0:
                        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
                        if len(lines) >= 2:
                            width = int(float(lines[0] or 0)) if lines[0] not in {"NA", "None"} else width
                            height = int(float(lines[1] or 0)) if lines[1] not in {"NA", "None"} else height
                        if len(lines) >= 3 and not title:
                            title = lines[2]
                        if len(lines) >= 4 and not author:
                            author = lines[3]
                        if len(lines) >= 5 and not thumbnail:
                            thumbnail = lines[4]
        except Exception:
            pass

        is_landscape = bool(width and height and width > height)
        is_portrait = bool(width and height and height > width)
        self._json({
            "title": title,
            "author": author,
            "author_name": author,
            "thumbnail": thumbnail,
            "thumbnail_url": thumbnail,
            "width": width,
            "height": height,
            "is_landscape": is_landscape,
            "is_portrait": is_portrait,
            "orientation": "landscape" if is_landscape else ("portrait" if is_portrait else "unknown"),
        })

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

    def _serve_clip_media(self, query):
        params = parse_qs(query, keep_blank_values=True)
        target = self._manager().clip_artifact(params.get("clip_id", [""])[0], params.get("artifact", [""])[0], params.get("preview_id", [""])[0])
        if not target:
            self._json({"status": "error", "message": "Artifact klip tidak ditemukan"}, 404)
            return
        # Internal only: path resolved by manager ownership, not client-supplied.
        encoded = f"path={quote(str(target))}"
        try:
            if params.get("download", [""])[0] == "1":
                self._download(encoded, allow_text=False)
            else:
                self._stream_video(encoded)
        except (ConnectionResetError, BrokenPipeError):
            pass

    def _serve_clip_frame(self, query):
        params = parse_qs(query, keep_blank_values=True)
        clip_id = params.get("clip_id", [""])[0]
        seek = params.get("t", params.get("seek", ["0"]))[0]
        raw, error = self._manager().extract_clip_frame(clip_id, seek)
        if error or not raw:
            self._json({"status": "error", "message": error or "Frame gagal diekstrak"}, 404)
            return
        self.send_response(200)
        self._add_security_headers()
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "private, max-age=30")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _stream_video(self, query):
        """Stream video inline with Range request support for browser playback."""
        path = parse_qs(query, keep_blank_values=True).get("path", [""])[0]
        if not path:
            self._json({"status": "error", "message": "Missing path"}, 400)
            return
        target = Path(path).resolve()
        output_root = Path(self._manager().get_settings()["output_dir"] or str(self._manager().output_dir)).resolve()
        video_exts = {".mp4", ".webm", ".mkv", ".mov", ".avi"}
        img_exts = {".jpg", ".jpeg", ".png"}
        allowed = video_exts | img_exts
        if not target.exists() or output_root not in target.parents or target.suffix.lower() not in allowed:
            self._json({"status": "error", "message": "File not found"}, 404)
            return

        suffix = target.suffix.lower()
        if suffix in img_exts:
            import mimetypes as _mt
            ct = _mt.guess_type(str(target))[0] or "image/jpeg"
            raw = target.read_bytes()
            self.send_response(200)
            self._add_security_headers()
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
                pass
            return

        # Video streaming with Range support
        ct_map = {".mp4": "video/mp4", ".webm": "video/webm", ".mkv": "video/x-matroska", ".mov": "video/quicktime", ".avi": "video/x-msvideo"}
        content_type = ct_map.get(suffix, "video/mp4")
        file_size = target.stat().st_size
        range_header = self.headers.get("Range", "")

        if range_header and range_header.startswith("bytes="):
            byte_range = range_header[6:].split("-", 1)
            try:
                start = int(byte_range[0]) if byte_range[0] else 0
                end = int(byte_range[1]) if len(byte_range) > 1 and byte_range[1] else file_size - 1
            except ValueError:
                self._json({"status": "error", "message": "Invalid range"}, 416)
                return
            end = min(end, file_size - 1)
            if start < 0 or start > end:
                self._json({"status": "error", "message": "Invalid range"}, 416)
                return
            length = end - start + 1
            self.send_response(206)
            self._add_security_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            try:
                with open(target, "rb") as f:
                    f.seek(start)
                    remaining = length
                    chunk = 65536
                    while remaining > 0:
                        data = f.read(min(chunk, remaining))
                        if not data:
                            break
                        self.wfile.write(data)
                        remaining -= len(data)
            except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
                pass
        else:
            self.send_response(200)
            self._add_security_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            try:
                with open(target, "rb") as f:
                    chunk = 65536
                    while True:
                        data = f.read(chunk)
                        if not data:
                            break
                        self.wfile.write(data)
            except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
                pass

    def _download(self, query, allow_text=False):
        path = parse_qs(query, keep_blank_values=True).get("path", [""])[0]
        if not path:
            self._json({"status": "error", "message": "Missing path"}, 400)
            return
        target = Path(path).resolve()
        output_root = Path(self._manager().get_settings()["output_dir"] or str(self._manager().output_dir)).resolve()
        media = {".mp4", ".webm", ".mkv", ".mov", ".avi", ".mp3", ".wav", ".jpg", ".jpeg", ".png"}
        text = {".json", ".srt", ".ass", ".txt", ".vtt"} if allow_text else set()
        allowed = media | text
        if not target.exists() or output_root not in target.parents or target.suffix.lower() not in allowed:
            self._json({"status": "error", "message": "File not found"}, 404)
            return
        file_size = target.stat().st_size
        safe_name = quote(target.name.replace('"', '').replace('\r', '').replace('\n', ''))
        img_exts = {".jpg", ".jpeg", ".png"}
        if target.suffix.lower() in img_exts:
            import mimetypes as _mt
            content_type = _mt.guess_type(str(target))[0] or "image/jpeg"
        else:
            content_type = "application/octet-stream"
        self.send_response(200)
        self._add_security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(file_size))
        if target.suffix.lower() in img_exts:
            self.send_header("Cache-Control", "public, max-age=3600")
        else:
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{safe_name}")
        self.end_headers()
        try:
            with open(target, "rb") as file:
                while data := file.read(65536):
                    self.wfile.write(data)
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
            pass


def _warmup_ffmpeg():
    """Warm up FFmpeg at startup so filter libraries are cached in memory.
    
    Saves ~3-5 seconds on the first job by pre-loading FFmpeg's shared
    libraries and codec registries into the OS page cache.
    """
    import threading

    def _run():
        try:
            from utils.helpers import get_ffmpeg_path
            ffmpeg_path = get_ffmpeg_path()
            subprocess.run(
                [ffmpeg_path, "-version"],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass  # Warm-up is best-effort; silently ignore failures

    t = threading.Thread(target=_run, daemon=True, name="ffmpeg-warmup")
    t.start()


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
    if security_mode == "public":
        session_secret = os.environ.get("KLIPKLOP_SECRET", "")
        if len(session_secret.encode("utf-8")) < 32:
            raise SystemExit("SECURITY ERROR: KLIPKLOP_SECRET must contain at least 32 bytes in public mode")

    url = f"http://{host}:{port}"
    server = ThreadingHTTPServer((host, port), WebKlipHandler)
    print(f"KlipKlop API server running at {url}")
    print(f"Frontend (React/Vite): http://localhost:5173")
    print(f"Security mode: {security_mode}")
    _warmup_ffmpeg()
    server.serve_forever()


if __name__ == "__main__":
    main()
