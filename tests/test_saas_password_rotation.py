"""First-login password rotation and SaaS account isolation regression tests."""
import hashlib
import io
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops" / "saas"))
import serve
import provision_agency


def hashed(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                          n=2**14, r=8, p=1).hex()


class SaaSPasswordRotationTests(unittest.TestCase):
    def setUp(self):
        serve.LOGIN_TRIES.clear()
        self.salt = "a" * 32
        self.original = "temporary-secret-password"
        self.person = {
            "username": "agency-admin", "role": "agent",
            "display_name": "Agency Administrator",
            "salt": self.salt, "hash": hashed(self.original, self.salt),
            "password_change_required": True,
        }
        expiry = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        self.users = {
            "users": [self.person, {"username": "other", "role": "agent"}],
            "sessions": {
                "first": {"username": "agency-admin", "exp": expiry},
                "second": {"username": "agency-admin", "exp": expiry},
                "other": {"username": "other", "exp": expiry},
            },
        }

    def handler(self, path="/api/change-password", cookie="first"):
        h = serve.H.__new__(serve.H)
        h.path = path
        h.user = self.person
        h.client_address = ("198.51.100.27", 5001)
        h.headers = {"Cookie": f"stage_session={cookie}"}
        h.wfile = io.BytesIO()
        h.results = []
        h.send_response = lambda status: h.results.append(("status", status))
        h.send_header = lambda name, value: h.results.append((name, value))
        h.end_headers = lambda: None
        h._json = lambda obj, code=200: h.results.append(("json", code, obj))
        return h

    def test_provisioned_admin_is_required_to_rotate_password(self):
        users, raw = provision_agency.single_admin("owner@example.test")
        admin = users["users"][0]
        self.assertTrue(admin["password_change_required"])
        self.assertEqual(admin["hash"], hashed(raw, admin["salt"]))
        self.assertNotIn(raw, json.dumps(users))

    def test_required_rotation_blocks_portal_and_business_apis(self):
        h = self.handler()
        h.session_user = lambda: self.person
        for path in ("/api/stage", "/api/tasks", "/api/case-action"):
            h.path = path
            h.results = []
            self.assertIsNone(h.require())
            self.assertIn(("json", 403, {"error": "password change required",
                                         "password_change_required": True}), h.results)
        h.path = "/agent"
        h.results = []
        self.assertIsNone(h.require({"agent"}))
        self.assertIn(("Location", "/change-password"), h.results)
        h.path = "/api/change-password"
        self.assertIs(h.require({"agent"}), self.person)
        h.path = "/change-password"
        self.assertIs(h.require(), self.person)

    def test_correct_change_invalidates_all_sessions_and_saves_new_hash(self):
        h = self.handler()
        new = "a-very-long-unique-passphrase"
        with patch.object(serve, "load_users", return_value=self.users), \
             patch.object(serve, "save_users") as save:
            h.do_POST_change_password({"current_password": self.original,
                                       "new_password": new})
            save.assert_called_once_with(self.users)
        self.assertNotIn("password_change_required", self.person)
        self.assertNotEqual(self.person["salt"], self.salt)
        self.assertEqual(self.person["hash"], hashed(new, self.person["salt"]))
        self.assertNotEqual(self.person["hash"], hashed(self.original, self.person["salt"]))
        self.assertEqual(list(self.users["sessions"]), ["other"])
        self.assertIn(("status", 200), h.results)
        self.assertTrue(any(k == "Set-Cookie" and "Max-Age=0" in value
                            for k, value in h.results))
        self.assertEqual(json.loads(h.wfile.getvalue()), {"ok": True, "login_required": True})

    def test_incorrect_current_password_preserves_account_and_sessions(self):
        h = self.handler()
        previous = json.loads(json.dumps(self.users))
        with patch.object(serve, "load_users", return_value=self.users), \
             patch.object(serve, "save_users") as save:
            h.do_POST_change_password({"current_password": "not-the-password",
                                       "new_password": "an-entirely-new-passphrase"})
            save.assert_not_called()
        self.assertEqual(self.users, previous)
        self.assertIn(("json", 401, {"error": "current password incorrect"}), h.results)

    def test_rejects_short_or_reused_password(self):
        for candidate in ("short", self.original, "agency-admin-weak-password"):
            with self.subTest(candidate=candidate):
                h = self.handler()
                with patch.object(serve, "load_users", return_value=self.users), \
                     patch.object(serve, "save_users") as save:
                    h.do_POST_change_password({"current_password": self.original,
                                               "new_password": candidate})
                    save.assert_not_called()
                self.assertTrue(any(r[0] == "json" and r[1] == 400 for r in h.results))

    def test_unauthenticated_cannot_change_password(self):
        h = self.handler()
        h.user = None
        h.session_user = lambda: None
        h.do_POST_change_password({"current_password": "anything",
                                   "new_password": "a-long-unique-passphrase"})
        self.assertIn(("json", 401, {"error": "authentication required"}), h.results)

    def test_password_change_route_is_never_public(self):
        h = self.handler()
        self.assertFalse(h.is_public("/api/change-password"))
        self.assertFalse(h.is_public("/change-password"))
        self.assertFalse(h.is_public("/change-password.html"))
        self.assertEqual(serve.H.ROLE_API["/api/change-password"],
                         {"agent", "landlord", "tenant", "trades"})


if __name__ == "__main__":
    unittest.main()
