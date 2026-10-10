"""Verify logout method, CSRF checks and session revocation."""
import io
import os
import sys
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "stage-clone"))

import serve

ORIGIN = "http://127.0.0.1:8902"


class LogoutSecurityTests(unittest.TestCase):

    def make_handler(self, origin=None, referer=None, token="test-token"):
        h = serve.H.__new__(serve.H)
        h.path = "/logout"
        h.headers = Message()

        if token:
            h.headers.add_header(
                "Cookie", "stage_session=" + token
            )
        if origin is not None:
            h.headers.add_header("Origin", origin)
        if referer is not None:
            h.headers.add_header("Referer", referer)

        body = b"intent=logout"
        h.headers.add_header(
            "Content-Length", str(len(body))
        )
        h.rfile = io.BytesIO(body)
        h.close_connection = False

        h.sent = []
        h.send_response = lambda status: h.sent.append(
            ("STATUS", status)
        )
        h.send_header = lambda key, value: h.sent.append(
            (key, value)
        )
        h.end_headers = lambda: None
        h._json = lambda data, code=200: h.sent.append(
            ("STATUS", code)
        )
        return h

    def run_post(self, h):
        with patch.dict(
            os.environ,
            {"ROGER_ALLOWED_ORIGINS": ORIGIN}
        ):
            h.do_POST()
        return [
            value for key, value in h.sent
            if key == "STATUS"
        ][-1]

    def test_get_cannot_logout(self):
        h = self.make_handler()

        with patch.object(serve, "load_users") as load, \
             patch.object(serve, "save_users") as save:
            h.do_GET()
            load.assert_not_called()
            save.assert_not_called()

        self.assertIn(("STATUS", 405), h.sent)
        self.assertIn(("Allow", "POST"), h.sent)
        self.assertFalse(
            any(key == "Set-Cookie" for key, _ in h.sent)
        )

    def test_valid_post_revokes_only_current_session(self):
        users = {
            "sessions": {
                "test-token": {"username": "agent"},
                "other-token": {"username": "agent"},
            }
        }
        h = self.make_handler(origin=ORIGIN)

        with patch.object(
            serve, "load_users", return_value=users
        ), patch.object(serve, "save_users") as save:
            status = self.run_post(h)
            save.assert_called_once()

        self.assertEqual(status, 303)
        self.assertNotIn("test-token", users["sessions"])
        self.assertIn("other-token", users["sessions"])
        self.assertIn(("Location", "/login"), h.sent)

        cookies = [
            value for key, value in h.sent
            if key == "Set-Cookie"
        ]
        self.assertEqual(len(cookies), 1)
        self.assertIn("Max-Age=0", cookies[0])

    def test_cross_origin_post_denied(self):
        h = self.make_handler(
            origin="https://untrusted.example"
        )
        with patch.object(serve, "load_users") as load, \
             patch.object(serve, "save_users") as save:
            self.assertEqual(self.run_post(h), 403)
            load.assert_not_called()
            save.assert_not_called()

    def test_missing_origin_and_referer_denied(self):
        h = self.make_handler()
        with patch.object(serve, "load_users") as load:
            self.assertEqual(self.run_post(h), 403)
            load.assert_not_called()

    def test_valid_referer_fallback_allows_logout(self):
        users = {
            "sessions": {
                "test-token": {"username": "agent"}
            }
        }
        h = self.make_handler(
            referer=ORIGIN + "/agent"
        )
        with patch.object(
            serve, "load_users", return_value=users
        ), patch.object(serve, "save_users") as save:
            self.assertEqual(self.run_post(h), 303)
            save.assert_called_once()

        self.assertNotIn("test-token", users["sessions"])

    def test_logout_without_cookie_is_safe(self):
        h = self.make_handler(
            origin=ORIGIN, token=None
        )
        with patch.object(serve, "load_users") as load, \
             patch.object(serve, "save_users") as save:
            self.assertEqual(self.run_post(h), 303)
            load.assert_not_called()
            save.assert_not_called()

    def test_all_four_portals_use_post_forms(self):
        for name in ("agent", "tenant", "landlord", "trades"):
            with self.subTest(portal=name):
                html = (
                    ROOT / "stage-clone" /
                    (name + ".html")
                ).read_text()

                self.assertIn(
                    'action="/logout" method="POST"',
                    html
                )
                self.assertNotIn(
                    'href="/logout"', html
                )

    def test_logout_route_is_public_post_not_public_get(self):
        self.assertIn("/logout", serve.H.PUBLIC_POST)
        self.assertNotIn("/logout", serve.H.PUBLIC_GET)


if __name__ == "__main__":
    unittest.main()
