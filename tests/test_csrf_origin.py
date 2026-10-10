"""CSRF Origin/Referer validation for browser POST endpoints."""
import io
import os
import sys
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "stage-clone")
)
import serve

LAB_ORIGIN = "http://127.0.0.1:8902"
PROD_ORIGIN = "https://agency.lifecompass.shop"


class CSRFOriginTests(unittest.TestCase):

    def make_handler(self, path, headers=()):
        h = serve.H.__new__(serve.H)
        h.path = path
        h.headers = Message()
        for name, value in headers:
            h.headers.add_header(name, value)

        body = b"{}"
        h.headers.add_header(
            "Content-Length", str(len(body))
        )
        h.rfile = io.BytesIO(body)
        h.close_connection = False

        h.require = lambda roles=None: {
            "role": "agent",
            "display_name": "Test Agent",
        }

        h.responses = []
        h._json = lambda obj, code=200: (
            h.responses.append(code)
        )

        h.handle_public_post = lambda data: h._json(
            {"ok": True}
        )
        h.handle_appointment_action = lambda data: h._json(
            {"ok": True}
        )
        return h

    def run_post(self, path, headers=(), expected=403):
        h = self.make_handler(path, headers)
        with patch.dict(
            os.environ,
            {"ROGER_ALLOWED_ORIGINS": LAB_ORIGIN}
        ):
            h.do_POST()
        self.assertEqual(h.responses[-1], expected)

    def test_valid_browser_origin(self):
        self.run_post(
            "/api/appointment-action",
            [("Origin", LAB_ORIGIN)],
            200,
        )

    def test_public_form_valid_origin(self):
        self.run_post(
            "/api/public",
            [("Origin", LAB_ORIGIN)],
            200,
        )

    def test_cross_origin_authenticated_rejected(self):
        self.run_post(
            "/api/appointment-action",
            [("Origin", "https://attacker.example")],
        )

    def test_cross_origin_public_rejected(self):
        self.run_post(
            "/api/public",
            [("Origin", "https://attacker.example")],
        )

    def test_missing_origin_and_referer_rejected(self):
        self.run_post("/api/appointment-action")

    def test_null_origin_rejected(self):
        self.run_post(
            "/api/appointment-action",
            [("Origin", "null")],
        )

    def test_valid_referer_fallback(self):
        self.run_post(
            "/api/appointment-action",
            [("Referer", LAB_ORIGIN + "/tenant")],
            200,
        )

    def test_cross_origin_referer_rejected(self):
        self.run_post(
            "/api/appointment-action",
            [("Referer", "https://attacker.example/")],
        )

    def test_invalid_origin_overrides_good_referer(self):
        self.run_post(
            "/api/appointment-action",
            [
                ("Origin", "https://attacker.example"),
                ("Referer", LAB_ORIGIN + "/tenant"),
            ],
        )

    def test_duplicate_origins_rejected(self):
        self.run_post(
            "/api/appointment-action",
            [
                ("Origin", LAB_ORIGIN),
                ("Origin", LAB_ORIGIN),
            ],
        )

    def test_origin_with_extra_path_rejected(self):
        self.run_post(
            "/api/appointment-action",
            [("Origin", LAB_ORIGIN + "/tenant")],
        )

    def test_cross_site_fetch_metadata_rejected(self):
        self.run_post(
            "/api/appointment-action",
            [
                ("Origin", LAB_ORIGIN),
                ("Sec-Fetch-Site", "cross-site"),
            ],
        )

    def test_spoofed_host_does_not_help(self):
        self.run_post(
            "/api/appointment-action",
            [
                ("Host", LAB_ORIGIN.removeprefix("http://")),
                ("Origin", "https://attacker.example"),
            ],
        )

    def test_referer_userinfo_trick_rejected(self):
        self.run_post(
            "/api/appointment-action",
            [
                (
                    "Referer",
                    LAB_ORIGIN + "@attacker.example/path",
                ),
            ],
        )

    def test_production_origin_default(self):
        h = self.make_handler(
            "/api/appointment-action",
            [("Origin", PROD_ORIGIN)],
        )
        with patch.dict(os.environ):
            os.environ.pop("ROGER_ALLOWED_ORIGINS", None)
            h.do_POST()

        self.assertEqual(h.responses[-1], 200)


if __name__ == "__main__":
    unittest.main()
