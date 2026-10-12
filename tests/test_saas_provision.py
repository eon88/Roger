"""Offline security tests for agency stack generation (no Docker needed)."""
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops" / "saas"))
import provision_agency as saas


class AgencyProvisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def create(self, slug, port=29101):
        return saas.provision(
            slug, "Oak Lettings", "owner@example.test", port,
            "roger-saas:1234567890ab", "agents.example.com",
            self.root / slug,
        )

    def test_two_agencies_have_separate_stacks_and_no_demo_data(self):
        self.create("oaklettings", 29101)
        self.create("birchlettings", 29102)
        a = self.root / "oaklettings"
        b = self.root / "birchlettings"
        assert (a / "bootstrap.sql").read_text() != (b / "bootstrap.sql").read_text()
        for root, slug, port in [(a, "oaklettings", 29101), (b, "birchlettings", 29102)]:
            compose = (root / "compose.yaml").read_text()
            self.assertIn("name: roger-" + slug, compose)
            self.assertIn("roger-" + slug + "_public", compose)
            self.assertIn("127.0.0.1:" + str(port), compose)
            self.assertIn("ROGER_STORAGE_BACKEND: postgres", compose)
            self.assertIn("ROGER_AGENCY_ID: " + chr(34) + slug + chr(34), compose)
            self.assertIn("internal: true", compose)
            self.assertNotIn("5432:5432", compose)
            self.assertIn("agency_files:/data", compose)
            self.assertNotIn("roster", compose)
            self.assertNotIn("roger_data:/data", compose)
            for f in root.iterdir():
                self.assertEqual(f.stat().st_mode & 0o077, 0, f.name)
        self.assertNotEqual((a / ".env").read_text(), (b / ".env").read_text())
        self.assertNotEqual(
            (a / "initial-admin-credentials.txt").read_text(),
            (b / "initial-admin-credentials.txt").read_text(),
        )

    def test_seed_has_no_demo_clients_and_only_one_admin(self):
        stage = saas.empty_stage("oaklettings")
        self.assertEqual(stage["agency_id"], "oaklettings")
        for key in saas.COLLECTIONS:
            self.assertEqual(stage[key], [], key)
        users, pw = saas.single_admin("owner@example.test")
        self.assertEqual(len(users["users"]), 1)
        admin = users["users"][0]
        self.assertEqual(admin["username"], "agency-admin")
        self.assertEqual(admin["role"], "agent")
        self.assertNotIn("dev", json.dumps(users))
        self.assertNotIn(pw, json.dumps(users))
        actual = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(admin["salt"]),
                                n=2**14, r=8, p=1).hex()
        self.assertEqual(actual, admin["hash"])
        self.assertGreater(len(pw), 30)

    def test_no_existing_agency_can_be_overwritten(self):
        self.create("oaklettings")
        initial = (self.root / "oaklettings" / "bootstrap.sql").read_bytes()
        with self.assertRaises(FileExistsError):
            self.create("oaklettings")
        self.assertEqual((self.root / "oaklettings" / "bootstrap.sql").read_bytes(), initial)

    def test_rejects_unsafe_slug_host_image_and_port(self):
        args = [
            ("../oops", "Good Agency", 29101, "roger-saas:1234567890ab", "agents.example.com"),
            ("admin", "Good Agency", 29101, "roger-saas:1234567890ab", "agents.example.com"),
            ("oaklettings", "Bad\nNAME", 29101, "roger-saas:1234567890ab", "agents.example.com"),
            ("oaklettings", "Good Agency", 8901, "roger-saas:1234567890ab", "agents.example.com"),
            ("oaklettings", "Good Agency", 29101, "python:latest", "agents.example.com"),
            ("oaklettings", "Good Agency", 29101, "roger-saas:1234567890ab", "bad;example.com"),
        ]
        for slug, name, port, image, base in args:
            with self.subTest(slug=slug, name=name, image=image):
                with self.assertRaises(ValueError):
                    saas.provision(slug, name, "owner@example.test", port,
                                   image, base, self.root / "unused")
        self.assertFalse((self.root / "unused").exists())

    def test_sql_literal_does_not_escape_into_sql_commands(self):
        val = {"agency_id": "bad'; DROP TABLE roger_users_snapshot; --"}
        sql = saas.sql_literal(val)
        self.assertEqual(sql[0], "'")
        self.assertEqual(sql[-1], "'")
        self.assertIn("''; DROP TABLE", sql)
        self.assertEqual(sql.count("'") % 2, 0)

    def test_generated_manifest_explicitly_not_deployed_or_paid(self):
        self.create("oaklettings")
        data = json.loads((self.root / "oaklettings" / "agency.json").read_text())
        self.assertEqual(data["status"], "prepared-not-deployed")
        self.assertEqual(data["billing"], "manual-trial-not-active")
        self.assertNotIn("PASSWORD", json.dumps(data))

if __name__ == "__main__":
    unittest.main()
