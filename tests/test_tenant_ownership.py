"""Tenant maintenance ownership regression tests."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "stage-clone")
)
import serve


class TenantOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.stage = {
            "properties": [
                {
                    "id": "flat-a",
                    "tenant": "Alex Example",
                    "tenant_party_id": "party-one",
                },
                {
                    "id": "flat-b",
                    "tenant": "Alex Example",
                    "tenant_party_id": "party-two",
                },
            ],
            "parties": [
                {
                    "id": "party-one",
                    "account_id": "account-one",
                    "roles": ["tenant"],
                    "status": "active",
                },
                {
                    "id": "party-two",
                    "account_id": "account-two",
                    "roles": ["tenant"],
                    "status": "active",
                },
            ],
            "cases": [],
            "jobs": [],
            "audit_log": [],
            "next_case_id": 9001,
        }

        self.handler = serve.H.__new__(serve.H)
        self.handler.user = {
            "username": "tenant1",
            "role": "tenant",
            "display_name": "Alex Example",
            "account_id": "account-one",
        }
        self.handler.triage = lambda message: {
            "category": "other",
            "trade": "other",
            "urgency": 1,
        }
        self.handler.store_case_attachments = (
            lambda *args: []
        )

        self.responses = []
        self.handler._json = lambda obj, code=200: (
            self.responses.append((obj, code))
        )

        self.loader = patch.object(
            serve, "load_stage", return_value=self.stage
        )
        self.saver = patch.object(serve, "save_stage")
        self.loader.start()
        self.saved = self.saver.start()
        self.addCleanup(self.loader.stop)
        self.addCleanup(self.saver.stop)

    def submit(self, property_id, party_id=None):
        data = {
            "property_id": property_id,
            "message": "Test maintenance request",
        }
        if party_id:
            data["tenant_party_id"] = party_id

        self.handler.handle_tenant_issue(data)
        return self.responses[-1]

    def test_own_property_allowed(self):
        result, code = self.submit("flat-a")
        self.assertEqual(code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(len(self.stage["cases"]), 1)
        self.assertEqual(
            self.stage["cases"][0]["tenant_party_id"],
            "party-one",
        )
        self.assertEqual(
            self.stage["cases"][0]["created_by_account_id"],
            "account-one",
        )
        self.saved.assert_called_once()

    def test_other_tenants_property_denied(self):
        before = copy.deepcopy(self.stage)
        _, code = self.submit("flat-b")
        self.assertEqual(code, 403)
        self.assertEqual(self.stage, before)
        self.saved.assert_not_called()

    def test_party_impersonation_denied(self):
        before = copy.deepcopy(self.stage)
        _, code = self.submit("flat-a", "party-two")
        self.assertEqual(code, 403)
        self.assertEqual(self.stage, before)
        self.saved.assert_not_called()

    def test_unknown_property_denied(self):
        _, code = self.submit("nonexistent")
        self.assertEqual(code, 404)
        self.saved.assert_not_called()

    def test_unlinked_account_denied(self):
        self.handler.user["account_id"] = "unknown-account"
        _, code = self.submit("flat-a")
        self.assertEqual(code, 403)
        self.saved.assert_not_called()


if __name__ == "__main__":
    unittest.main()
