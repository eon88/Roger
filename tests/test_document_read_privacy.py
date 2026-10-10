"""Regression tests for document authorisation."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "stage-clone")
)
import serve


class DocumentReadPrivacyTests(unittest.TestCase):
    def setUp(self):
        people = [
            ("tenant1", "tenant", "Alex"),
            ("tenant2", "tenant", "Alex"),
            ("landlord1", "landlord", "Owner"),
            ("landlord2", "landlord", "Owner"),
            ("trade1", "trades", "Repair"),
            ("trade2", "trades", "Repair"),
        ]

        self.users = {
            name: {
                "username": name,
                "account_id": "account-" + name,
                "display_name": display,
                "role": role,
            }
            for name, role, display in people
        }
        self.users["agent"] = {
            "username": "agent",
            "account_id": "account-agent",
            "display_name": "Agent",
            "role": "agent",
        }

        self.stage = {
            "parties": [
                {
                    "id": "party-" + name,
                    "account_id": "account-" + name,
                    "roles": [role],
                    "status": "active",
                }
                for name, role, _ in people
            ],
            "properties": [{
                "id": "home-a",
                "tenant": "Alex",
                "tenant_party_id": "party-tenant1",
                "landlord": "Owner",
                "landlord_party_id": "party-landlord1",
            }],
            "cases": [{
                "id": 900,
                "property_id": "home-a",
                "tenant_party_id": "party-tenant1",
                "name": "Alex",
            }],
            "jobs": [{
                "id": "job-a",
                "case_id": 900,
                "property_id": "home-a",
                "assigned_to": "Repair",
                "assigned_to_party_id": "party-trade1",
                "status": "in_progress",
            }],
            "tenancies": [],
        }

        self.doc = {
            "id": "doc-a",
            "case_id": 900,
            "job_id": "job-a",
            "property_id": "home-a",
            "access_roles": [
                "agent", "tenant", "landlord", "trades"
            ],
        }

        self.handler = serve.H.__new__(serve.H)
        self.mock_load = patch.object(
            serve, "load_stage", return_value=self.stage
        )
        self.mock_load.start()
        self.addCleanup(self.mock_load.stop)

    def allowed(self, username, doc=None):
        return self.handler.can_view_document(
            self.users[username],
            self.doc if doc is None else doc,
        )

    def test_01_correct_tenant(self):
        self.assertTrue(self.allowed("tenant1"))

    def test_02_duplicate_name_tenant_blocked(self):
        self.assertFalse(self.allowed("tenant2"))

    def test_03_correct_landlord(self):
        self.assertTrue(self.allowed("landlord1"))

    def test_04_duplicate_name_landlord_blocked(self):
        self.assertFalse(self.allowed("landlord2"))

    def test_05_assigned_contractor(self):
        self.assertTrue(self.allowed("trade1"))

    def test_06_duplicate_name_contractor_blocked(self):
        self.assertFalse(self.allowed("trade2"))

    def test_07_unclassified_document_blocked(self):
        doc = dict(self.doc)
        doc.pop("access_roles")
        for user in ("tenant1", "landlord1", "trade1"):
            with self.subTest(user=user):
                self.assertFalse(self.allowed(user, doc))

    def test_08_empty_access_roles_blocked(self):
        doc = dict(self.doc, access_roles=[])
        self.assertFalse(self.allowed("tenant1", doc))

    def test_09_role_not_allowed_blocked(self):
        doc = dict(self.doc, access_roles=["agent", "tenant"])
        self.assertFalse(self.allowed("trade1", doc))

    def test_10_unlinked_account_blocked(self):
        self.users["trade1"]["account_id"] = "unknown"
        self.assertFalse(self.allowed("trade1"))

    def test_11_legacy_name_assignment_blocked(self):
        self.stage["jobs"][0].pop("assigned_to_party_id")
        self.assertFalse(self.allowed("trade1"))

    def test_12_wrong_tenant_case_blocked(self):
        self.stage["cases"][0]["tenant_party_id"] = (
            "party-tenant2"
        )
        self.assertFalse(self.allowed("tenant1"))

    def test_13_missing_job_blocked(self):
        doc = dict(self.doc, job_id="unknown-job")
        self.assertFalse(self.allowed("trade1", doc))

    def test_14_case_job_mismatch_blocked(self):
        self.stage["jobs"][0]["case_id"] = 901
        self.assertFalse(self.allowed("trade1"))

    def test_15_conflicting_property_blocked(self):
        doc = dict(self.doc, property_id="different-home")
        self.assertFalse(self.allowed("tenant1", doc))

    def test_16_document_party_restriction(self):
        doc = dict(self.doc, party_id="party-tenant1")
        self.assertTrue(self.allowed("tenant1", doc))
        self.assertFalse(self.allowed("landlord1", doc))

    def test_17_property_only_contractor_blocked(self):
        doc = dict(self.doc)
        doc.pop("job_id")
        doc.pop("case_id")
        self.assertFalse(self.allowed("trade1", doc))

    def test_18_direct_party_document_allowed(self):
        doc = {
            "access_roles": ["tenant"],
            "party_id": "party-tenant1",
        }
        self.assertTrue(self.allowed("tenant1", doc))

    def test_19_direct_party_document_isolated(self):
        doc = {
            "access_roles": ["tenant"],
            "party_id": "party-tenant1",
        }
        self.assertFalse(self.allowed("tenant2", doc))

    def test_20_agent_can_view_unclassified(self):
        doc = dict(self.doc)
        doc.pop("access_roles")
        self.assertTrue(self.allowed("agent", doc))


if __name__ == "__main__":
    unittest.main()
