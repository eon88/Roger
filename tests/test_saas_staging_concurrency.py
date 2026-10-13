"""Checks conservative staging-only concurrency smoke test safety and isolation."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops" / "saas" / "check_staging_concurrency.py"
spec = importlib.util.spec_from_file_location("check_staging_concurrency", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class BoundedConcurrencyTests(unittest.TestCase):
    def fixture(self, where):
        root = Path(where)
        for slug, port in mod.AGENCIES:
            folder = root / slug
            folder.mkdir()
            (folder / "agency.json").write_text(json.dumps({
                "agency_id": slug, "port": port,
                "hostname": slug + ".agents.example.invalid",
            }))
        return root

    def test_wrong_agency_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.fixture(d)
            file = root / "stg-birch" / "agency.json"
            data = json.loads(file.read_text())
            data["agency_id"] = "stg-oak"
            file.write_text(json.dumps(data))
            with patch.object(mod, "ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "identity/port mismatch"):
                    mod.agency_manifest("stg-birch", 29102)

    def test_memory_gate_prevents_any_docker_request(self):
        with patch.object(mod, "available_memory", return_value=500 * 1024 * 1024), \
             patch.object(mod, "healthy_containers") as docker:
            with self.assertRaisesRegex(RuntimeError, "memory"):
                mod.preflight()
            docker.assert_not_called()

    def test_non_loopback_url_refused_before_network(self):
        with patch.object(mod, "urlopen") as http:
            with self.assertRaisesRegex(ValueError, "loopback"):
                mod.api("https://agency.lifecompass.shop", "/api/stage")
            http.assert_not_called()

    def test_simulated_sessions_reject_cross_agency_stage(self):
        manifests = [
            {"agency_id": "stg-oak", "port": 29101, "hostname": "stg-oak.agents.invalid"},
            {"agency_id": "stg-birch", "port": 29102, "hostname": "stg-birch.agents.invalid"},
        ]
        def fake_api(base, path, *, cookie=None, payload=None, origin=None):
            slug = "stg-oak" if base.endswith("29101") else "stg-birch"
            if path == "/login":
                return (200, {"role": "agent", "password_change_required": False},
                        "session=abc; Secure; HttpOnly", 0.001)
            return 200, {"agency_id": "stg-birch" if slug == "stg-oak" else "stg-oak"}, "", 0.003

        with patch.object(mod, "api", side_effect=fake_api):
            with self.assertRaisesRegex(RuntimeError, "isolation mismatch"):
                mod.independent_sessions(manifests)

    def test_four_clients_three_rounds_only_staging_reads(self):
        sessions = [
            ("stg-oak", "http://127.0.0.1:29101", "session=oak1"),
            ("stg-oak", "http://127.0.0.1:29101", "session=oak2"),
            ("stg-birch", "http://127.0.0.1:29102", "session=birch1"),
            ("stg-birch", "http://127.0.0.1:29102", "session=birch2"),
        ]
        def fake_api(base, path, *, cookie=None, payload=None, origin=None):
            slug = "stg-oak" if base.endswith("29101") else "stg-birch"
            self.assertEqual(path, "/api/stage")
            self.assertIn(cookie, ("session=oak1", "session=oak2",
                                   "session=birch1", "session=birch2"))
            return 200, {"agency_id": slug}, "", 0.025

        with patch.object(mod, "api", side_effect=fake_api) as http, \
             patch.object(mod, "available_memory", return_value=2 * 1024 ** 3), \
             patch.object(mod.time, "sleep"):
            records = mod.simultaneous_rounds(sessions)
        self.assertEqual(len(records), 12)
        self.assertEqual(http.call_count, 12)
        self.assertEqual(len([r for r in records if r[0] == "stg-oak"]), 6)
        self.assertEqual(len([r for r in records if r[0] == "stg-birch"]), 6)

    def test_report_refuses_incomplete_requests(self):
        with self.assertRaisesRegex(RuntimeError, "not all"):
            mod.report([("stg-oak", 0.001)])


if __name__ == "__main__":
    unittest.main()
