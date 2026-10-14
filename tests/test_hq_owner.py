import hashlib
import os
import unittest
from unittest.mock import patch

from stage_clone_import import hq_owner

class OwnerAuthTests(unittest.TestCase):
    def setUp(self):
        self.password = "test-only-password"
        salt = bytes.fromhex("0123456789abcdef0123456789abcdef")
        digest = hashlib.scrypt(self.password.encode(), salt=salt, n=2**14, r=8, p=1).hex()
        self.env = patch.dict(os.environ, {
            "ROGER_HQ_OWNER_USERNAME": "hq-owner",
            "ROGER_HQ_OWNER_PASSWORD_HASH": salt.hex() + ":" + digest,
            "ROGER_HQ_SESSION_SECRET": "test-secret-do-not-use-in-production"
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_owner_login(self):
        self.assertTrue(hq_owner.password_matches("hq-owner", self.password))
        self.assertFalse(hq_owner.password_matches("hq-oak-agent", self.password))
        self.assertFalse(hq_owner.password_matches("hq-owner", "wrong"))

    def test_signed_session(self):
        token = hq_owner.issue_token()
        self.assertTrue(hq_owner.valid_token(token))
        self.assertFalse(hq_owner.valid_token(token + "x"))
        self.assertFalse(hq_owner.valid_token("not-a-token"))

    def test_disabled_without_secret(self):
        with patch.dict(os.environ, {"ROGER_HQ_SESSION_SECRET": ""}):
            self.assertFalse(hq_owner.configured())
            self.assertFalse(hq_owner.valid_token(hq_owner.issue_token() if hq_owner.configured() else "invalid"))
