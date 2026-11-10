"""B02: linked joint ownership and occupants do not expose internal data."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


class ScopedPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.stage = {
            "properties": [
                {
                    "id": "home-one", "title": "Family apartment", "beds": 3,
                    "area": "North", "rent": 1200,
                    "tenant_party_ids": ["resident-one", "resident-two"],
                    "landlord_party_ids": ["owner-one", "owner-two"],
                    "tenant": "Shared household",
                    "bank_iban": "PRIVATE-CLIENT-MONEY-ACCOUNT",
                    "landlord_email": "owner-secret@example.test",
                    "tenant_email": "resident-secret@example.test",
                    "master_key_code": "PRIVATE-ACCESS-CODE",
                    "internal_notes": "PRIVATE-NEGOTIATION",
                },
                {
                    "id": "home-two", "title": "Neighbour",
                    "tenant_party_id": "resident-three",
                    "landlord_party_id": "owner-three",
                    "bank_iban": "OTHER-AGENCY-ACCOUNT",
                },
            ],
            "parties": [
                {
                    "id": p, "account_id": "account-" + p,
                    "status": "active", "roles": [role],
                }
                for p, role in (
                    ("resident-one", "tenant"), ("resident-two", "tenant"),
                    ("resident-three", "tenant"), ("owner-one", "landlord"),
                    ("owner-two", "landlord"), ("owner-three", "landlord"),
                )
            ],
            "cases": [
                {
                    "id": 501, "property_id": "home-one", "tenant_party_id": "resident-one",
                    "message": "Water leak", "status": "reported",
                    "email": "SECRET-CASE-EMAIL", "internal_notes": "SECRET-AGENT-NOTE",
                    "thread": [
                        {"author": "Agent", "to": ["tenant", "landlord"], "text": "Repair scheduled"},
                        {"author": "Agent", "to": ["agent"], "text": "SECRET-OFFICE-THREAD"},
                    ],
                },
                {
                    "id": 502, "property_id": "home-two", "tenant_party_id": "resident-three",
                    "message": "OTHER-TENANT-CASE", "status": "new",
                },
            ],
            "jobs": [
                {
                    "id": "job-one", "case_id": 501, "property_id": "home-one",
                    "status": "in_progress", "assigned_to": "Plumber",
                    "invoice_pence": 5500, "payment_reference": "PRIVATE-BANK-REF",
                    "payments": [{"reference": "PRIVATE-PAYMENT-REF"}],
                    "internal_notes": "PRIVATE-TRADE-NOTES",
                },
                {
                    "id": "job-two", "case_id": 502, "property_id": "home-two",
                    "status": "open", "assigned_to": None,
                },
            ],
            "approvals": [], "property_submissions": [], "authority": {},
        }
        self.handler = serve.H.__new__(serve.H)
        self.responses = []
        self.handler._json = lambda body, code=200: self.responses.append((code, body))
        self.load = patch.object(serve, "load_stage", return_value=self.stage)
        self.load.start()
        self.addCleanup(self.load.stop)

    def view(self, role, party):
        self.handler.session_user = lambda: {
            "role": role, "username": party, "account_id": "account-" + party,
            "display_name": "Same Name",
        }
        before = copy.deepcopy(self.stage)
        self.handler.serve_scoped_stage()
        self.assertEqual(self.stage, before)
        return self.responses[-1][1]

    def test_both_joint_owners_can_see_only_own_property_without_secret_fields(self):
        for owner in ("owner-one", "owner-two"):
            with self.subTest(owner=owner):
                data = self.view("landlord", owner)
                self.assertEqual([p["id"] for p in data["properties"]], ["home-one"])
                self.assertEqual([j["id"] for j in data["jobs"]], ["job-one"])
                self.assertEqual([c["id"] for c in data["cases"]], [501])
                for secret in (
                    "PRIVATE-CLIENT-MONEY-ACCOUNT", "owner-secret@example.test",
                    "PRIVATE-ACCESS-CODE", "PRIVATE-NEGOTIATION",
                    "SECRET-OFFICE-THREAD", "PRIVATE-PAYMENT-REF",
                    "PRIVATE-BANK-REF", "SECRET-CASE-EMAIL",
                ):
                    self.assertNotIn(secret, str(data))

    def test_multiple_occupants_see_home_but_only_own_cases(self):
        first = self.view("tenant", "resident-one")
        self.assertEqual([p["id"] for p in first["properties"]], ["home-one"])
        self.assertEqual([c["id"] for c in first["cases"]], [501])
        self.assertEqual([j["id"] for j in first["jobs"]], ["job-one"])
        self.assertNotIn("SECRET-OFFICE-THREAD", str(first))
        self.assertNotIn("PRIVATE-PAYMENT-REF", str(first))
        self.assertNotIn("PRIVATE-CLIENT-MONEY-ACCOUNT", str(first))
        other = self.view("tenant", "resident-two")
        self.assertEqual([p["id"] for p in other["properties"]], ["home-one"])
        self.assertEqual(other["cases"], [])
        self.assertEqual(other["jobs"], [])

    def test_other_tenant_and_owner_get_neither_first_property_nor_case(self):
        tenant = self.view("tenant", "resident-three")
        self.assertEqual({p["id"] for p in tenant["properties"]}, {"home-two"})
        self.assertNotIn("home-one", str(tenant))
        owner = self.view("landlord", "owner-three")
        self.assertEqual({p["id"] for p in owner["properties"]}, {"home-two"})
        self.assertNotIn("Water leak", str(owner))

    def test_unlinked_account_does_not_inherit_same_display_name(self):
        tenant = self.view("tenant", "unlinked")
        owner = self.view("landlord", "unlinked")
        for projection in (tenant, owner):
            self.assertEqual(projection["properties"], [])
            self.assertEqual(projection["cases"], [])
            self.assertEqual(projection["jobs"], [])

    def test_agent_view_is_intentionally_full_but_requires_agent_authentication(self):
        result = self.view("agent", "office")
        self.assertIn("PRIVATE-BANK-REF", str(result))
        self.assertEqual(result["properties"][0]["bank_iban"], "PRIVATE-CLIENT-MONEY-ACCOUNT")


if __name__ == "__main__":
    unittest.main()
