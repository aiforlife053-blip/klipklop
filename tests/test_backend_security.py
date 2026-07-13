import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import social_auth
from job_manager import WebJobManager


class BackendSecurityTests(unittest.TestCase):
    def setUp(self):
        self.user_a = str(uuid.uuid4())
        self.user_b = str(uuid.uuid4())

    def test_user_storage_isolated_and_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            a = WebJobManager(Path(root) / self.user_a, user_id=self.user_a)
            b = WebJobManager(Path(root) / self.user_b, user_id=self.user_b)
            a.output_dir.mkdir(parents=True)
            b.output_dir.mkdir(parents=True)
            foreign = b.output_dir / "secret.mp4"
            foreign.write_bytes(b"secret")
            self.assertEqual(a.delete_output({"path": str(foreign)})["status"], "error")
            self.assertTrue(foreign.exists())

    def test_cookie_files_are_isolated_per_user(self):
        with tempfile.TemporaryDirectory() as root:
            a = WebJobManager(Path(root) / self.user_a, user_id=self.user_a)
            b = WebJobManager(Path(root) / self.user_b, user_id=self.user_b)
            result = a.save_cookies("SID=user-a")
            self.assertEqual(result["status"], "saved")
            self.assertTrue(a.core_cookie_file.exists())
            self.assertFalse(b.core_cookie_file.exists())
            self.assertFalse((Path(root) / "cookies.txt").exists())

    def test_provider_key_fails_closed_without_vault(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""}, clear=False):
            manager = WebJobManager(Path(root) / self.user_a, user_id=self.user_a)
            result = manager.save_settings({"api_key": "plaintext"})
            self.assertEqual(result["status"], "error")
            self.assertNotIn("plaintext", manager.config_file.read_text(encoding="utf-8"))

    def test_provider_key_uses_vault_and_never_local_storage(self):
        with tempfile.TemporaryDirectory() as root:
            manager = WebJobManager(Path(root) / self.user_a, user_id=self.user_a)
            manager._vault_write_key = MagicMock()
            manager._vault_key_exists = MagicMock(return_value=True)
            result = manager.save_settings({"api_key": "highlight-secret", "caption_api_key": "caption-secret"})
            self.assertEqual(result["status"], "saved")
            self.assertEqual(manager._vault_write_key.call_count, 2)
            local = manager.config_file.read_text(encoding="utf-8")
            self.assertNotIn("highlight-secret", local)
            self.assertNotIn("caption-secret", local)

    def test_watermark_client_path_is_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            manager = WebJobManager(Path(root) / self.user_a, user_id=self.user_a)
            manager._vault_key_exists = MagicMock(return_value=False)
            outside = Path(root) / "foreign.png"
            outside.write_bytes(b"foreign")
            result = manager.save_settings({"watermark": {"enabled": True, "image_path": str(outside)}})
            self.assertEqual(result["settings"]["watermark"]["image_path"], "")

    def test_tickets_are_per_user(self):
        with tempfile.TemporaryDirectory() as root:
            a = WebJobManager(Path(root) / self.user_a, user_id=self.user_a)
            b = WebJobManager(Path(root) / self.user_b, user_id=self.user_b)
            a.log_activity({"action": "ticket", "detail": "a"})
            b.log_activity({"action": "ticket", "detail": "b"})
            self.assertIn('"a"', (a.app_dir / "tickets.json").read_text(encoding="utf-8"))
            self.assertNotIn('"b"', (a.app_dir / "tickets.json").read_text(encoding="utf-8"))

    def test_oauth_state_is_single_use_and_token_is_encrypted(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {
            "YOUTUBE_CLIENT_ID": "client",
            "YOUTUBE_CLIENT_SECRET": "secret",
            "YOUTUBE_REDIRECT_URI": "https://example.test/api/youtube/callback",
            "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        }, clear=False), patch.object(social_auth, "TOKEN_DIR", Path(root)), patch.object(
            social_auth, "_exchange_code", return_value={"access_token": "access", "refresh_token": "refresh"}
        ):
            result = social_auth.start_youtube_oauth(self.user_a)
            state = __import__("urllib.parse").parse.parse_qs(__import__("urllib.parse").parse.urlparse(result["auth_url"]).query)["state"][0]
            self.assertEqual(social_auth.finish_youtube_oauth(state, "code"), self.user_a)
            encrypted = social_auth._token_file(self.user_a).read_bytes()
            self.assertNotIn(b"access", encrypted)
            with self.assertRaises(ValueError):
                social_auth.finish_youtube_oauth(state, "code")

    def test_youtube_status_includes_channel_name(self):
        credentials = MagicMock(refresh_token="refresh", expired=False)
        response = {"items": [{"id": "channel-id", "snippet": {"title": "KlipKlop Channel"}}]}
        api = MagicMock()
        api.channels.return_value.list.return_value.execute.return_value = response
        with patch.object(social_auth, "_load_credentials", return_value=credentials), patch.object(
            social_auth, "get_youtube_credentials", return_value=credentials
        ), patch("googleapiclient.discovery.build", return_value=api):
            result = social_auth.is_youtube_connected(self.user_a)
        self.assertTrue(result["connected"])
        self.assertEqual(result["channel_id"], "channel-id")
        self.assertEqual(result["channel_title"], "KlipKlop Channel")

    def test_oauth_requires_https_callback(self):
        with patch.dict(os.environ, {"YOUTUBE_CLIENT_ID": "client", "YOUTUBE_CLIENT_SECRET": "secret", "YOUTUBE_REDIRECT_URI": "http://example.test/callback"}, clear=False):
            with self.assertRaises(RuntimeError):
                social_auth.start_youtube_oauth(self.user_a)


if __name__ == "__main__":
    unittest.main()
