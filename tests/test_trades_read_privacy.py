"""Contractor stage read-isolation regression tests."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "stage-clone")
)
import serve


class ContractorReadTests(unittest.TestCase):
    def setUp(self):
        self.stage = {
            "parties": [
                {
                    "id": f"party-{n}",
                    "account_id": f"account-{n}",
                    "roles": ["trades"],
                    "status": "active",
                }
                for n in (1, 2)
            ],
            "properties": [{
                "id": "home-a",
                "title": "Private test property",
                "area": "Exampleton",
                "tenant": "Private Tenant",
                "landlord": "Private Landlord",
                "landlord_email": "private@example.test",
            }],
            "cases": [{
                "id": 901,
                "property_id": "home-a",
                "thread": [{
                    "author": "Tenant",
                    "role": "tenant",
                    "text": "Private access arrangement",
                    "to": ["trades"],
                    "at": "2026-10-09",
                }],
            }],
            "jobs": [
                {
                    "id": "job-private",
                    "case_id": 901,
                    "property_id": "home-a",
                    "assigned_to": "Repair Example",
                    "assigned_to_party_id": "party-1",
                    "status": "in_progress",
                    "message": "Private tenant maintenance details",
                },
                {
                    "id": "job-open",
                    "case_id": 902,
                    "property_id": "home-a",
                    "assigned_to": None,
                    "status": "open",
                    "message": "Private information in an open job",
                    "required_trade": "plumbing",
                },
                {
                    "id": "job-legacy",
                    "case_id": 903,
                    "property_id": "home-a",
                    "assigned_to": "Repair Example",
                    "status": "in_progress",
                    "message": "Unverified legacy assignment",
                },
            ],
            "approvals": [{
                "id": "approval-private",
                "job_id": "job-private",
                "evidence": {
                    "tradesperson": "Repair Example"
                },
                "landlord": "Private Landlord",
                "status": "pending",
                "amount_pence": 20000,
            }],
            "authority": {
                "standing_limit_pence": 15000
            },
        }

        self.handler = serve.H.__new__(serve.H)
        self.output = []
        self.handler._json = lambda obj, code=200: (
            self.output.append(obj)
        )

    def view(self, account):
        self.handler.session_user = lambda: {
            "username": account,
            "account_id": "account-" + account,
            "role": "trades",
            "display_name": "Repair Example",
        }
        before = copy.deepcopy(self.stage)
        with patch.object(
            serve, "load_stage", return_value=self.stage
        ):
            self.handler.serve_scoped_stage()
        self.assertEqual(self.stage, before)
        return self.output[-1]

    def test_other_contractor_cannot_see_assigned_job(self):
        result = self.view("2")
        ids = {j["id"] for j in result["jobs"]}
        self.assertNotIn("job-private", ids)

    def test_correct_contractor_sees_own_job(self):
        result = self.view("1")
        self.assertIn(
            "job-private",
            {j["id"] for j in result["jobs"]}
        )

    def test_legacy_name_assignment_does_not_grant_access(self):
        for account in ("1", "2"):
            result = self.view(account)
            self.assertNotIn(
                "job-legacy",
                {j["id"] for j in result["jobs"]}
            )

    def test_open_jobs_remain_available(self):
        for account in ("1", "2"):
            result = self.view(account)
            self.assertIn(
                "job-open",
                {j["id"] for j in result["jobs"]}
            )

    def test_open_jobs_hide_tenant_and_property_details(self):
        result = self.view("2")
        job = next(
            j for j in result["jobs"]
            if j["id"] == "job-open"
        )
        self.assertNotIn("property_id", job)
        self.assertNotIn(
            "Private information in an open job",
            str(job)
        )
        self.assertNotIn(
            "Private Tenant", str(result)
        )

    def test_other_contractor_cannot_see_conversation(self):
        result = self.view("2")
        self.assertNotIn(901, result["threads"])
        self.assertNotIn(
            "Private access arrangement", str(result)
        )

    def test_assigned_contractor_can_see_conversation(self):
        result = self.view("1")
        self.assertIn(901, result["threads"])

    def test_other_contractor_cannot_see_invoice(self):
        result = self.view("2")
        self.assertEqual(result["approvals"], [])

    def test_correct_contractor_sees_relevant_invoice(self):
        result = self.view("1")
        self.assertEqual(
            result["approvals"][0]["job_id"],
            "job-private"
        )
        self.assertNotIn(
            "landlord", result["approvals"][0]
        )

    def test_property_information_minimised(self):
        result = self.view("1")
        prop = result["properties"][0]
        self.assertEqual(
            set(prop), {"id", "title", "area"}
        )

    def test_unlinked_contractor_gets_no_jobs(self):
        result = self.view("unknown")
        self.assertEqual(result["jobs"], [])
        self.assertEqual(result["properties"], [])
        self.assertEqual(result["threads"], {})


if __name__ == "__main__":
    unittest.main()
