"""B01: new document uploads cannot cross-link unrelated live records."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "stage-clone"))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))
import serve
from v1_two_agency_data import build


class DocumentAttachmentConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.stage = build("oaklettings")
        self.before = copy.deepcopy(self.stage)
        self.handler = serve.H.__new__(serve.H)
        self.handler.user = {
            "username": "office", "role": "agent", "display_name": "Agent"
        }
        self.responses = []
        self.handler._json = lambda payload, code=200: self.responses.append((payload, code))
        loader = patch.object(serve, "load_stage", return_value=self.stage)
        writer = patch.object(serve, "save_stage")
        storer = patch.object(self.handler, "store_document_body", return_value="synthetic-file-key")
        for p in (loader, writer, storer):
            p.start()
            self.addCleanup(p.stop)
        self.writer = writer
        self.storer = storer

    def upload(self, **kwargs):
        payload = {
            "document_type": "inventory",
            "file_name": "inventory.pdf",
            "content_b64": "U3ludGhldGlj",  # synthetic bytes; no physical file
            **kwargs,
        }
        self.handler.handle_document(payload)
        return self.responses[-1][1]

    def test_missing_case_is_not_silently_discarded(self):
        self.assertEqual(self.upload(
            property_id=self.stage["properties"][0]["id"], case_id="nonexistent-case"
        ), 404)
        self.assertEqual(self.stage, self.before)

    def test_tenancy_from_another_property_is_denied_before_file_write(self):
        self.assertEqual(self.upload(
            property_id=self.stage["properties"][1]["id"],
            tenancy_id=self.stage["tenancies"][0]["id"]
        ), 409)
        self.assertEqual(self.stage, self.before)

    def test_job_case_mismatch_denied_even_if_property_is_same(self):
        second = copy.deepcopy(self.stage["cases"][0])
        second["id"] = "repair-second"
        self.stage["cases"].append(second)
        self.assertEqual(self.upload(
            case_id=second["id"], job_id=self.stage["jobs"][0]["id"]
        ), 409)
        self.assertEqual(len(self.stage["documents"]), 1)

    def test_replacement_cannot_silently_switch_subject(self):
        self.assertEqual(self.upload(
            property_id=self.stage["properties"][1]["id"],
            supersedes_id=self.stage["documents"][0]["id"]
        ), 409)
        self.assertEqual(self.stage, self.before)

    def test_valid_upload_is_versioned_and_has_unique_id(self):
        self.stage["documents"].append({
            "id": "doc-3", "property_id": self.stage["properties"][0]["id"],
            "document_type": "other"
        })
        self.assertEqual(self.upload(
            property_id=self.stage["properties"][0]["id"],
            tenancy_id=self.stage["tenancies"][0]["id"]
        ), 200)
        document = self.stage["documents"][-1]
        self.assertEqual(document["id"], "doc-4")
        self.assertEqual(document["model_version"], 1)
        self.assertEqual(document["tenancy_id"], self.stage["tenancies"][0]["id"])
        self.assertEqual(document["property_id"], self.stage["properties"][0]["id"])

    def test_refused_upload_does_not_store_or_commit_file(self):
        self.upload(property_id=self.stage["properties"][1]["id"],
                    job_id=self.stage["jobs"][0]["id"])
        self.assertEqual(self.responses[-1][1], 409)
        self.storer.assert_not_called()
        self.writer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
