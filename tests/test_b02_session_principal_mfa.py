"""B02 bound sessions, TOTP, authentication lifecycle and replay safety."""
import base64
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import auth_security as a
import serve


def hashed(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                          n=2**14, r=8, p=1).hex()


class SessionPrincipalSecurityTests(unittest.TestCase):
    def setUp(self):
        self.salt = "a" * 32
        self.password = "correct long passphrase"
        self.user = {
            "username": "staffuser", "role": "agent", "account_id": "account-staff",
            "agency_id": "oaklettings", "display_name": "Office",
            "salt": self.salt, "hash": hashed(self.password, self.salt),
        }
        self.users = {"users": [self.user], "sessions": {}}
        self.expiry = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        serve.LOGIN_TRIES.clear()

    def valid_session(self):
        return {"username": "staffuser", "exp": self.expiry, **a.session_principal(self.user)}

    def test_session_is_credential_role_account_and_agency_bound(self):
        session = self.valid_session()
        self.assertTrue(a.current_session(session, self.user, "oaklettings"))
        for field, changed in [
            ("role", "landlord"), ("account_id", "other-account"),
            ("agency_id", "birchlettings"),
            ("password_fingerprint", "wrong"),
        ]:
            with self.subTest(field=field):
                bad = {**session, field: changed}
                self.assertFalse(a.current_session(bad, self.user, "oaklettings"))
        modified = {**self.user, "hash": "reset-or-rotated"}
        self.assertFalse(a.current_session(session, modified, "oaklettings"))
        disabled = {**self.user, "disabled_at": "2026-11-10T10:00:00Z"}
        self.assertFalse(a.current_session(session, disabled, "oaklettings"))
        self.assertFalse(a.current_session(session, self.user, "birchlettings"))

    def test_legacy_unbound_and_expired_tokens_never_regain_access(self):
        self.assertFalse(a.current_session(
            {"username": "staffuser", "exp": self.expiry}, self.user))
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.assertFalse(a.current_session(
            {**self.valid_session(), "exp": yesterday}, self.user))
        self.assertFalse(a.current_session(
            {**self.valid_session(), "auth_version": 1}, self.user))

    def test_session_user_accepts_bound_token_and_rejects_privilege_change(self):
        self.users["sessions"]["safe-cookie"] = self.valid_session()
        h = serve.H.__new__(serve.H)
        h.headers = {"Cookie": "stage_session=safe-cookie"}
        with patch.object(serve, "load_users", return_value=self.users), patch.dict(
                "os.environ", {"ROGER_SAAS_MODE": "1", "ROGER_AGENCY_ID": "oaklettings"}):
            self.assertEqual(h.session_user()["username"], "staffuser")
            self.user["role"] = "landlord"
            self.assertIsNone(h.session_user())

    def test_rfc_6238_standard_totp_vector_and_replay_denial(self):
        secret = base64.b32encode(b"12345678901234567890").decode()
        self.assertEqual(a.totp_at(secret, 59 // 30), "287082")
        self.assertEqual(a.verify_totp(secret, "287082", now=59), 1)
        self.assertIsNone(a.verify_totp(secret, "287082", now=59, last_step=1))
        self.assertIsNone(a.verify_totp(secret, "28708x", now=59))
        self.assertIsNone(a.verify_totp(secret, "000000", now=59))

    def test_login_guesses_are_throttled_per_account_without_raw_names(self):
        serve.LOGIN_ACCOUNT_TRIES.clear()
        self.addCleanup(serve.LOGIN_ACCOUNT_TRIES.clear)
        for _ in range(10):
            serve.account_login_note("victim@example.test", ok=False)
        self.assertTrue(serve.account_throttled("victim@example.test"))
        self.assertFalse(serve.account_throttled("other@example.test"))
        self.assertNotIn("victim@example.test", repr(serve.LOGIN_ACCOUNT_TRIES))
        serve.account_login_note("victim@example.test", ok=True)
        self.assertFalse(serve.account_throttled("victim@example.test"))

    def test_mfa_policy_blocks_agent_business_routes_until_enrolled(self):
        h = self.handler()
        h.path = "/api/stage"
        h.session_user = lambda: self.user
        with patch.dict("os.environ", {"ROGER_REQUIRE_AGENT_MFA": "1"}):
            self.assertIsNone(h.require({"agent"}))
            self.assertEqual(h.sent[-1][0], 403)
            self.assertTrue(h.sent[-1][1]["mfa_setup_required"])
            h.path = "/security"
            self.assertEqual(h.require({"agent"}), self.user)
            h.path = "/api/security/mfa/start"
            self.assertEqual(h.require({"agent"}), self.user)
            self.user["mfa_secret"] = a.new_totp_secret(b"b" * 20)
            h.path = "/api/stage"
            self.assertEqual(h.require({"agent"}), self.user)

    def test_totp_login_checks_one_time_code_and_denies_replayed_step(self):
        secret = a.new_totp_secret(b"b" * 20)
        self.user["mfa_secret"] = secret
        h = serve.H.__new__(serve.H)
        h.path = "/login"
        h.client_address = ("203.0.113.10", 5555)
        h.sent = []
        h.wfile = io.BytesIO()
        h.send_response = lambda code: h.sent.append(("status", code))
        h.send_header = lambda header, value: h.sent.append((header, value))
        h.end_headers = lambda: None
        h._json = lambda payload, code=200: h.sent.append(("error", code, payload))
        current = a.totp_at(secret, int(time.time()) // 30)
        with patch.object(serve, "load_users", return_value=self.users), \
             patch.object(serve, "save_users") as saved:
            h.do_POST_login({"username": "staffuser", "password": self.password,
                             "totp": "123x00"})
            self.assertEqual(h.sent[-1][1], 401)
            self.assertEqual(self.users["sessions"], {})
            h.do_POST_login({"username": "staffuser", "password": self.password,
                             "totp": current})
            self.assertIn(("status", 200), h.sent)
            self.assertEqual(len(self.users["sessions"]), 1)
            self.assertEqual(self.user["mfa_last_step"], int(time.time()) // 30)
            h.do_POST_login({"username": "staffuser", "password": self.password,
                             "totp": current})
            self.assertEqual(h.sent[-1][1], 401)
            self.assertEqual(len(self.users["sessions"]), 1)
            saved.assert_called()

    def test_invalid_totp_key_is_rejected(self):
        with self.assertRaises(ValueError):
            a.totp_at("too-short", 5)

    def handler(self):
        h = serve.H.__new__(serve.H)
        h.user = self.user
        h.path = "/api/security/mfa/start"
        h.headers = {"Cookie": "stage_session=safe-cookie"}
        h.client_address = ("198.51.100.12", 1234)
        h.sent = []
        h._json = lambda obj, code=200: h.sent.append((code, obj))
        return h

    def test_mfa_enrolment_requires_password_confirms_and_revokes_sessions(self):
        self.users["sessions"]["safe-cookie"] = self.valid_session()
        h = self.handler()
        with patch.object(serve, "load_users", return_value=self.users), \
             patch.object(serve, "save_users") as saved:
            h.handle_mfa_start({"current_password": "wrong"})
            self.assertEqual(h.sent[-1][0], 401)
            self.assertNotIn("mfa_pending_secret", self.user)
            h.handle_mfa_start({"current_password": self.password})
            self.assertEqual(h.sent[-1][0], 200)
            secret = h.sent[-1][1]["secret"]
            self.assertEqual(len(secret), 32)
            self.assertNotIn(secret, str(self.users.get("sessions")))
            self.assertNotIn(secret, h.sent[-1][1]["notice"])
            step = int(time.time()) // 30
            h.handle_mfa_confirm({"current_password": self.password, "totp": "00000x"})
            self.assertEqual(h.sent[-1][0], 400)
            h.handle_mfa_confirm({"current_password": self.password,
                                  "totp": a.totp_at(secret, step)})
            self.assertEqual(h.sent[-1][0], 200)
            self.assertTrue(h.sent[-1][1]["login_required"])
            self.assertEqual(self.user["mfa_secret"], secret)
            self.assertEqual(self.users["sessions"], {})
            saved.assert_called()

    def test_mfa_disable_requires_password_and_fresh_totp(self):
        self.user["mfa_secret"] = a.new_totp_secret(b"a" * 20)
        self.user["mfa_last_step"] = -1
        h = self.handler()
        with patch.object(serve, "load_users", return_value=self.users), \
             patch.object(serve, "save_users"):
            h.handle_mfa_disable({"current_password": self.password, "totp": "11111x"})
            self.assertEqual(h.sent[-1][0], 400)
            h.handle_mfa_disable({"current_password": self.password,
                "totp": a.totp_at(self.user["mfa_secret"], int(time.time()) // 30)})
            self.assertEqual(h.sent[-1][0], 200)
            self.assertNotIn("mfa_secret", self.user)

    def test_mfa_can_be_enforced_for_agency_staff(self):
        self.user["mfa_secret"] = a.new_totp_secret(b"a" * 20)
        h = self.handler()
        with patch.object(serve, "load_users", return_value=self.users), \
             patch.dict("os.environ", {"ROGER_REQUIRE_AGENT_MFA": "1"}):
            h.handle_mfa_disable({"current_password": self.password,
                                  "totp": a.totp_at(self.user["mfa_secret"], int(time.time()) // 30)})
        self.assertEqual(h.sent[-1][0], 403)
        self.assertIn("mfa_secret", self.user)

    def test_session_revoke_other_or_all_requires_current_password(self):
        self.users["sessions"] = {"safe-cookie": self.valid_session(),
                                  "another": self.valid_session(),
                                  "different-user": {"username": "someone-else"}}
        h = self.handler()
        with patch.object(serve, "load_users", return_value=self.users), \
             patch.object(serve, "save_users") as save:
            h.handle_sessions_revoke({"current_password": "wrong", "scope": "all"})
            self.assertEqual(h.sent[-1][0], 401)
            self.assertEqual(len(self.users["sessions"]), 3)
            h.handle_sessions_revoke({"current_password": self.password, "scope": "other"})
            self.assertEqual(h.sent[-1][0], 200)
            self.assertEqual(set(self.users["sessions"]), {"safe-cookie", "different-user"})
            h.handle_sessions_revoke({"current_password": self.password, "scope": "all"})
            self.assertEqual(h.sent[-1][0], 200)
            self.assertEqual(set(self.users["sessions"]), {"different-user"})
            save.assert_called()


if __name__ == "__main__":
    unittest.main()
