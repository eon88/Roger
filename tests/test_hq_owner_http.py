"""Real loopback HTTP checks for private Roger HQ owner login and logout.

All users and secrets are fake and the server binds only to an ephemeral
loopback port in CI. No staging or production server is involved.
"""
import hashlib
from http.server import HTTPServer
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "stage-clone"
sys.path.insert(0, str(APP))
spec = importlib.util.spec_from_file_location("roger_hq_http_test_app", APP / "serve.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class HQOwnerHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = "only-for-disposable-local-unit-tests"
        salt = bytes.fromhex("0123456789abcdef0123456789abcdef")
        digest = hashlib.scrypt(cls.password.encode(), salt=salt,
                                n=2**14, r=8, p=1).hex()
        cls.patcher = patch.dict(os.environ, {
            "ROGER_HQ_OWNER_USERNAME": "hq-fixture-owner",
            "ROGER_HQ_OWNER_PASSWORD_HASH": salt.hex() + ":" + digest,
            "ROGER_HQ_SESSION_SECRET": "local-test-session-secret-never-production",
            "ROGER_COOKIE_SECURE": "0",
        })
        cls.patcher.start()
        cls.server = HTTPServer(("127.0.0.1", 0), app.H)
        cls.base = "http://127.0.0.1:" + str(cls.server.server_port)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.patcher.stop()

    def setUp(self):
        app.LOGIN_TRIES.clear()

    def send(self, path, *, data=None, cookie=None, origin=True):
        headers = {}
        if cookie:
            headers["Cookie"] = cookie
        if data is not None:
            headers["Content-Type"] = "application/json"
            if origin:
                headers["Origin"] = self.base
        request = Request(
            self.base + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers=headers, method="POST" if data is not None else "GET",
        )
        try:
            with urlopen(request, timeout=5) as r:
                return r.status, r.read(), r.headers.get("Set-Cookie", "")
        except HTTPError as exc:
            return exc.code, exc.read(), exc.headers.get("Set-Cookie", "")

    def login(self):
        code, body, cookie = self.send("/api/hq-owner/login", data={
            "username": "hq-fixture-owner", "password": self.password})
        self.assertEqual(code, 200, body)
        self.assertIn("roger_hq_owner=", cookie)
        self.assertIn("Path=/api/hq-owner/", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertNotIn("Secure", cookie)
        return cookie.split(";", 1)[0]

    def test_login_whoami_and_logout_without_legacy_agency_session(self):
        status, body, _ = self.send("/api/hq-owner/whoami")
        self.assertEqual(status, 401)
        cookie = self.login()
        status, body, _ = self.send("/api/hq-owner/whoami", cookie=cookie)
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["role"], "platform_owner")
        self.assertEqual(json.loads(body)["username"], "hq-fixture-owner")
        status, body, clear = self.send("/api/hq-owner/logout", cookie=cookie, data={})
        self.assertEqual(status, 200, body)
        self.assertIn("Max-Age=0", clear)
        self.assertIn("Path=/api/hq-owner/", clear)
        self.assertEqual(json.loads(body), {"ok": True})
        status, _, _ = self.send("/api/hq-owner/whoami")
        self.assertEqual(status, 401)

    def test_logout_rejects_cross_origin(self):
        cookie = self.login()
        status, _, _ = self.send("/api/hq-owner/logout", cookie=cookie,
                                 data={}, origin=False)
        self.assertEqual(status, 403)
        status, _, _ = self.send("/api/hq-owner/whoami", cookie=cookie)
        self.assertEqual(status, 200)

    def test_login_rejects_missing_origin_before_checking_password(self):
        status, body, _ = self.send("/api/hq-owner/login", data={
            "username": "hq-fixture-owner", "password": self.password
        }, origin=False)
        self.assertEqual(status, 403, body)
        self.assertIn("origin verification required", json.loads(body)["error"])

    def test_wrong_owner_password_is_rejected(self):
        status, body, _ = self.send("/api/hq-owner/login", data={
            "username": "hq-fixture-owner", "password": "nope"})
        self.assertEqual(status, 401, body)
        self.assertEqual(json.loads(body)["error"], "invalid owner credentials")

    def test_unconfigured_account_returns_useful_http_status(self):
        with patch.dict(os.environ, {"ROGER_HQ_OWNER_PASSWORD_HASH": ""}):
            code, body, _ = self.send("/api/hq-owner/login", data={
                "username": "hq-fixture-owner", "password": self.password})
        self.assertEqual(code, 503, body)
        self.assertIn("not configured", json.loads(body)["error"])

    def test_hq_page_contains_working_routes_and_error_feedback(self):
        code, body, _ = self.send("/hq")
        self.assertEqual(code, 200)
        markup = body.decode()
        self.assertIn("/api/hq-owner/login", markup)
        self.assertIn("/api/hq-owner/logout", markup)
        self.assertIn("method:'POST'", markup)
        self.assertIn("Password accepted, but your browser did not keep", markup)
        self.assertIn("credentials: 'same-origin'", markup)


if __name__ == "__main__":
    unittest.main()
