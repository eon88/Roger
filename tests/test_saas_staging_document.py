"""Safety and API-flow tests for the synthetic Oak document test helper."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "ops" / "saas" / "seed_oak_test_document.py"
spec = importlib.util.spec_from_file_location("seed_oak_test_document", FILE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class OakSyntheticDocumentTests(unittest.TestCase):
    def agency(self, folder, slug="stg-oak"):
        path = Path(folder)
        (path / "agency.json").write_text(json.dumps({
            "agency_id": slug, "hostname": "stg-oak.agents.example.invalid",
            "port": 29101,
        }))
        return path

    def test_wrong_agency_fails_before_any_contact_with_docker(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.agency(d, slug="roger")
            with patch.object(mod, "ROOT", path), patch.object(mod, "require_healthy") as docker:
                with self.assertRaisesRegex(RuntimeError, "agency identity"):
                    mod.main()
                docker.assert_not_called()

    def test_single_synthetic_upload_and_authenticated_download(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.agency(d)
            key = hashlib.sha256(mod.BODY).hexdigest()
            stage = {"agency_id": "stg-oak",
                     "properties": [{"id": "ci-invite-home-1"}], "documents": []}
            answers = [
                (200, {"role": "agent", "password_change_required": False},
                 "session=testing; Secure; HttpOnly"),
                (200, stage, ""),
                (200, {"success": True, "document": {"id": "doc-9", "storage_key": key}}, ""),
                (200, mod.BODY, ""),
            ]
            with patch.object(mod, "ROOT", path), \
                 patch.object(mod, "require_healthy") as docker, \
                 patch.object(mod, "request", side_effect=answers) as call:
                self.assertEqual(mod.main(), 0)
                self.assertEqual(docker.call_count, 6)
                self.assertEqual(call.call_count, 4)
                self.assertEqual(call.call_args_list[2].args[1], "/api/document")
                self.assertEqual(call.call_args_list[2].kwargs["payload"]["content_type"], "text/plain")
                self.assertEqual(call.call_args_list[3].args[1], "/api/document/doc-9/file")

    def test_existing_synthetic_document_does_not_upload_twice(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.agency(d)
            stage = {"agency_id": "stg-oak",
                     "properties": [{"id": "ci-invite-home-1"}],
                     "documents": [{"id": "doc-1", "title": mod.TITLE,
                                    "storage_key": hashlib.sha256(mod.BODY).hexdigest()}]}
            with patch.object(mod, "ROOT", path), \
                 patch.object(mod, "require_healthy"), \
                 patch.object(mod, "request", side_effect=[
                     (200, {"role": "agent", "password_change_required": False}, "session=testing; Secure"),
                     (200, stage, ""),
                     (200, mod.BODY, ""),
                 ]) as request:
                self.assertEqual(mod.main(), 0)
                self.assertEqual(request.call_count, 3)
                self.assertEqual(request.call_args_list[-1].args[1], "/api/document/doc-1/file")


if __name__ == "__main__":
    unittest.main()
