"""Small, targeted access tests for the landlord's rent dashboard."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


class LandlordRentPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.stage = {
            "parties": [
                {"id": "owner-one", "account_id": "account-one", "status": "active", "roles": ["landlord"]},
                {"id": "owner-two", "account_id": "account-two", "status": "active", "roles": ["landlord"]},
            ],
            "properties": [
                {"id": "home-one", "landlord_party_id": "owner-one", "title": "One"},
                {"id": "home-two", "landlord_party_id": "owner-two", "title": "Two"},
            ],
            "rent_ledger_entries": [
                {"id": "rent-one", "property_id": "home-one", "tenancy_id": "t-one",
                 "due_date": "2026-01-01", "amount_due_pence": 180000,
                 "payments": [{"received_date": "2026-01-03", "amount_pence": 180000,
                               "note": "internal private note", "agency_fee_pence": 20000}],
                 "adjustments": []},
                {"id": "rent-two", "property_id": "home-two", "tenancy_id": "t-two",
                 "due_date": "2026-01-01", "amount_due_pence": 250000,
                 "payments": [], "adjustments": []},
            ],
        }

    def read_as(self, account_id, role="landlord"):
        h = serve.H.__new__(serve.H)
        h.path = "/api/landlord/rent-ledger"
        user = {"role": role, "display_name": "Same name", "account_id": account_id}
        h.require = lambda roles: user if role in roles else None
        replies = []
        h._json = lambda body, code=200: replies.append((body, code))
        with patch.object(serve, "load_stage", return_value=self.stage):
            h.do_GET()
        return replies

    def test_receipts_visible_only_for_own_property_without_internal_notes(self):
        data, code = self.read_as("account-one")[0]
        self.assertEqual(code, 200)
        self.assertEqual([x["id"] for x in data["entries"]], ["rent-one"])
        record = data["entries"][0]
        self.assertEqual(record["status"], "paid")
        self.assertEqual(record["amount_received_pence"], 180000)
        self.assertEqual(record["payments"], [
            {"received_date": "2026-01-03", "amount_pence": 180000}])
        self.assertNotIn("note", str(record))
        self.assertNotIn("agency_fee_pence", str(record))

    def test_same_display_name_does_not_expose_other_landlord(self):
        data, code = self.read_as("account-two")[0]
        self.assertEqual(code, 200)
        self.assertEqual([x["id"] for x in data["entries"]], ["rent-two"])
        self.assertEqual(data["entries"][0]["status"], "overdue")

    def test_unlinked_account_fails_closed(self):
        data, code = self.read_as("unknown-account")[0]
        self.assertEqual(code, 200)
        self.assertEqual(data["entries"], [])

    def test_other_roles_cannot_use_landlord_endpoint(self):
        self.assertEqual(self.read_as("account-one", "tenant"), [])


if __name__ == "__main__":
    unittest.main()
