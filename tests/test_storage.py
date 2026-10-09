"""Tests for atomic JSON snapshot writes."""
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
import base64

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import serve
from extract_document_files import extract_document_files


class AtomicStorageTests(unittest.TestCase):
    def test_document_upload_writes_private_file_and_keeps_only_metadata_in_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(serve, "FILES_DIR", tmp):
                handler = serve.H.__new__(serve.H)
                handler.user = {"username": "agent", "display_name": "Agent"}
                handler._json = lambda payload, status=200: (payload, status)
                stage = {"properties": [{"id": "home-1"}], "documents": [], "audit_log": []}
                content = b"private certificate"
                response = []
                handler._json = lambda payload, status=200: response.append((payload, status))
                with patch.object(serve, "load_stage", return_value=stage), patch.object(serve, "save_stage"):
                    serve.H.handle_document(handler, {
                        "property_id": "home-1", "document_type": "other",
                        "file_name": "cert.pdf", "content_type": "application/pdf",
                        "content_b64": base64.b64encode(content).decode("ascii"),
                    })
                doc = stage["documents"][0]
                path = serve.H.document_path(handler, doc)
                self.assertTrue(Path(path).is_file())
                self.assertEqual(Path(path).read_bytes(), content)
                self.assertNotIn("data_b64", doc)
                self.assertFalse("data_b64" in response[0][0]["document"])

    def test_document_upload_links_entities_and_supersedes_prior_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(serve, "FILES_DIR", tmp):
                handler = serve.H.__new__(serve.H)
                handler.user = {"username": "agent", "display_name": "Agent"}
                response = []
                handler._json = lambda payload, status=200: response.append((payload, status))
                stage = {
                    "properties": [{"id": "home-1", "title": "Home"}],
                    "cases": [{"id": 490, "property_id": "home-1"}],
                    "tenancies": [{"id": "tenancy-1", "property_id": "home-1", "document_ids": []}],
                    "jobs": [{"id": "job-1", "property_id": "home-1", "document_ids": []}],
                    "parties": [{"id": "party-1", "display_name": "Landlord", "roles": ["landlord"]}],
                    "documents": [{"id": "doc-old", "version": 1, "status": "verified"}],
                    "audit_log": [],
                }
                with patch.object(serve, "load_stage", return_value=stage), patch.object(serve, "save_stage"):
                    serve.H.handle_document(handler, {
                        "case_id": "490", "property_id": "home-1", "party_id": "party-1",
                        "tenancy_id": "tenancy-1", "job_id": "job-1",
                        "document_type": "compliance_certificate",
                        "file_name": "new-cert.pdf", "content_type": "application/pdf",
                        "content_b64": base64.b64encode(b"new version").decode("ascii"),
                        "expiry_date": "2027-10-09",
                        "access_roles": ["landlord", "tenant"],
                        "supersedes_id": "doc-old",
                    })
                doc = stage["documents"][-1]
                self.assertEqual(doc["version"], 2)
                self.assertEqual(doc["party_id"], "party-1")
                self.assertEqual(doc["tenancy_id"], "tenancy-1")
                self.assertEqual(doc["job_id"], "job-1")
                self.assertEqual(doc["expiry_date"], "2027-10-09")
                self.assertEqual(doc["access_roles"], ["agent", "landlord", "tenant"])
                self.assertEqual(stage["documents"][0]["status"], "superseded")
                self.assertEqual(stage["documents"][0]["replaced_by_id"], doc["id"])
                self.assertEqual(stage["tenancies"][0]["document_ids"], [doc["id"]])
                self.assertEqual(stage["jobs"][0]["document_ids"], [doc["id"]])
                self.assertEqual(response[-1][1], 200)

    def test_legacy_document_extraction_preserves_body_and_removes_base64(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage_path = root / "stage.json"
            files = root / "files"
            body = b"legacy document"
            encoded = base64.b64encode(body).decode("ascii")
            stage_path.write_text(json.dumps({"documents": [{"id": "doc-1", "data_b64": encoded}]}), encoding="utf-8")
            self.assertEqual(extract_document_files(stage_path, files, apply=False), 1)
            self.assertFalse(files.exists())
            self.assertEqual(extract_document_files(stage_path, files, apply=True), 1)
            stage = json.loads(stage_path.read_text(encoding="utf-8"))
            doc = stage["documents"][0]
            self.assertNotIn("data_b64", doc)
            stored = files / doc["storage_key"][:2] / doc["storage_key"]
            self.assertEqual(stored.read_bytes(), body)
            if os.name == "posix":
                self.assertEqual(stored.stat().st_mode & 0o777, 0o600)

    def test_appointment_links_case_job_and_supports_reschedule_outcome(self):
        handler = serve.H.__new__(serve.H)
        handler.user = {"username": "agent", "role": "agent", "display_name": "Agent"}
        response = []
        handler._json = lambda payload, status=200: response.append((payload, status))
        stage = {
            "properties": [{"id": "home-1", "title": "Home"}],
            "cases": [{"id": 10, "property_id": "home-1", "appointment_ids": []}],
            "jobs": [{"id": "job-1", "case_id": 10, "property_id": "home-1", "appointment_ids": []}],
            "parties": [{"id": "party-1", "display_name": "Tenant", "roles": ["tenant"]}],
            "appointments": [],
            "audit_log": [],
        }
        with patch.object(serve, "load_stage", return_value=stage), patch.object(serve, "save_stage"):
            serve.H.handle_appointment(handler, {
                "property_id": "home-1",
                "case_id": "10",
                "job_id": "job-1",
                "appointment_type": "contractor_visit",
                "title": "Boiler visit",
                "start_time": "2027-01-12T10:00:00Z",
                "end_time": "2027-01-12T11:00:00Z",
                "participant_roles": ["tenant", "trades"],
                "participant_party_ids": ["party-1"],
                "reminder_at": "2027-01-11T10:00:00Z",
            })
            appt = stage["appointments"][0]
            serve.H.handle_appointment_action(handler, {
                "id": appt["id"],
                "action": "reschedule",
                "start_time": "2027-01-13T12:00:00Z",
                "note": "Tenant asked for lunchtime",
            })
            serve.H.handle_appointment_action(handler, {
                "id": appt["id"],
                "action": "complete",
                "outcome": "Boiler serviced and certificate requested",
            })
        self.assertEqual(response[0][1], 200)
        self.assertEqual(appt["appointment_type"], "contractor_visit")
        self.assertEqual(appt["case_id"], 10)
        self.assertEqual(appt["job_id"], "job-1")
        self.assertEqual(appt["participant_roles"], ["agent", "tenant", "trades"])
        self.assertEqual(appt["participant_party_ids"], ["party-1"])
        self.assertEqual(stage["cases"][0]["appointment_ids"], [appt["id"]])
        self.assertEqual(stage["jobs"][0]["appointment_ids"], [appt["id"]])
        self.assertEqual(appt["previous_start_time"], "2027-01-12T10:00:00Z")
        self.assertEqual(appt["start_time"], "2027-01-13T12:00:00Z")
        self.assertEqual(appt["status"], "completed")
        self.assertEqual(appt["outcome"], "Boiler serviced and certificate requested")

    def test_task_action_creates_and_completes_related_task(self):
        handler = serve.H.__new__(serve.H)
        handler.user = {"username": "agent", "role": "agent", "display_name": "Agent"}
        response = []
        handler._json = lambda payload, status=200: response.append((payload, status))
        stage = {"tasks": [], "audit_log": []}
        with patch.object(serve, "load_stage", return_value=stage), patch.object(serve, "save_stage"):
            serve.H.handle_task_action(handler, {
                "action": "create",
                "title": "Chase contractor quote",
                "owner": "Repairs desk",
                "priority": "high",
                "due_date": "2027-02-01",
                "reminder_at": "2027-01-31T09:00:00Z",
                "recurrence": "weekly",
                "property_id": "home-1",
                "case_id": 42,
                "job_id": "job-7",
            })
            task = stage["tasks"][0]
            serve.H.handle_task_action(handler, {"id": task["id"], "action": "complete"})
        self.assertEqual(response[0][1], 200)
        self.assertEqual(task["title"], "Chase contractor quote")
        self.assertEqual(task["owner"], "Repairs desk")
        self.assertEqual(task["priority"], "high")
        self.assertEqual(task["reminder_at"], "2027-01-31T09:00:00Z")
        self.assertEqual(task["recurrence"], "weekly")
        self.assertEqual(task["property_id"], "home-1")
        self.assertEqual(task["case_id"], 42)
        self.assertEqual(task["job_id"], "job-7")
        self.assertEqual(task["status"], "completed")
        self.assertTrue(task["completed_at"])

    def test_atomic_write_roundtrips_and_restricts_file_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stage.json"
            expected = {"cases": [{"id": 1}]}
            serve.atomic_json_write(str(path), expected)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), expected)
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["stage.json"])


if __name__ == "__main__":
    unittest.main()
