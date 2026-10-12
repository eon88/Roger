"""Offline operator-only SaaS administrator recovery security tests."""
from contextlib import nullcontext
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import agency_recovery


class AgencyRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.private = Path(self.temp.name) / "private"
        self.private.mkdir(mode=0o700)
        self.out = self.private / "one-time.txt"
        self.data = {"users": [
            {"username": "agency-admin", "role": "agent", "salt": "a" * 32,
             "hash": "original", "email": "owner@example.test"},
            {"username": "other", "role": "tenant"},
        ], "sessions": {
            "admin1": {"username": "agency-admin"},
            "admin2": {"username": "agency-admin"},
            "tenant1": {"username": "other"},
        }}
        self.env = patch.dict(os.environ, {
            "ROGER_SAAS_MODE": "1", "ROGER_STORAGE_BACKEND": "postgres",
            "ROGER_AGENCY_ID": "oaklettings",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def run_reset(self, *, stage=None, save=None):
        stage = stage if stage is not None else {"agency_id": "oaklettings"}
        with patch.object(agency_recovery.serve, "storage_write_lock", return_value=nullcontext()), \
             patch.object(agency_recovery.serve, "load_users", return_value=self.data), \
             patch.object(agency_recovery.serve, "load_stage", return_value=stage), \
             patch.object(agency_recovery.serve, "save_users", side_effect=save) as save_mock:
            result = agency_recovery.recover_admin(self.out, "oaklettings")
            return result, save_mock

    def test_success_generates_private_one_time_secret_and_revokes_only_admin_sessions(self):
        result, saved = self.run_reset()
        self.assertEqual(result["revoked_sessions"], 2)
        saved.assert_called_once_with(self.data)
        self.assertEqual(set(self.data["sessions"]), {"tenant1"})
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o600)
        text = self.out.read_text()
        self.assertIn("AGENCY=oaklettings", text)
        secret = next(line.split("=", 1)[1] for line in text.splitlines()
                      if line.startswith("TEMPORARY_PASSWORD="))
        self.assertGreaterEqual(len(secret), 32)
        u = self.data["users"][0]
        self.assertTrue(u["password_change_required"])
        self.assertNotEqual(u["hash"], "original")
        self.assertEqual(u["hash"], hashlib.scrypt(secret.encode(),
                         salt=bytes.fromhex(u["salt"]), n=2**14, r=8, p=1).hex())
        self.assertNotIn(secret, str(result))

    def test_wrong_agency_denied_without_file_or_database_write(self):
        with self.assertRaises(RuntimeError):
            agency_recovery.recover_admin(self.out, "birchlettings")
        self.assertFalse(self.out.exists())
        with self.assertRaises(RuntimeError):
            self.run_reset(stage={"agency_id": "birchlettings"})
        self.assertFalse(self.out.exists())

    def test_non_saas_mode_rejected(self):
        with patch.dict(os.environ, {"ROGER_SAAS_MODE": "0"}):
            with self.assertRaises(RuntimeError):
                agency_recovery.recover_admin(self.out, "oaklettings")
        self.assertFalse(self.out.exists())

    def test_existing_file_cannot_be_overwritten(self):
        self.out.write_text("DO NOT OVERWRITE")
        with self.assertRaises(ValueError):
            agency_recovery.recover_admin(self.out, "oaklettings")
        self.assertEqual(self.out.read_text(), "DO NOT OVERWRITE")

    def test_world_readable_directory_denied(self):
        self.private.chmod(0o755)
        with self.assertRaises(ValueError):
            agency_recovery.recover_admin(self.out, "oaklettings")
        self.assertFalse(self.out.exists())

    def test_database_failure_removes_one_time_file(self):
        with self.assertRaisesRegex(OSError, "no database"):
            self.run_reset(save=OSError("no database"))
        self.assertFalse(self.out.exists())

    def test_missing_or_disabled_admin_refused(self):
        self.data["users"][0]["disabled_at"] = "2026-10-12T01:00:00Z"
        with self.assertRaises(RuntimeError):
            self.run_reset()
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
