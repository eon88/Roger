"""Contractor job ownership and workflow regression tests."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "stage-clone")
)
import serve

COMPANY = "R. Doyle Gas & Heat"


class JobPermissionTests(unittest.TestCase):
    def setUp(self):
        self.stage = {
            "parties": [
                {
                    "id": f"party-{n}",
                    "account_id": f"account-{n}",
                    "display_name": COMPANY,
                    "roles": ["trades"],
                    "status": "active",
                }
                for n in (1, 2)
            ],
            "properties": [
                {"id": "flat-a", "landlord": "Test Owner"}
            ],
            "cases": [],
            "jobs": [{
                "id": "job-1",
                "case_id": 101,
                "property_id": "flat-a",
                "message": "Synthetic repair",
                "status": "in_progress",
                "assigned_to": COMPANY,
                "assigned_to_party_id": "party-1",
                "required_trade": None,
            }],
            "approvals": [],
            "audit_log": [],
            "authority": {"standing_limit_pence": 15000},
        }

        self.handler = serve.H.__new__(serve.H)
        self.handler.post_msg = lambda *a, **kw: None
        self.handler.sync_case = lambda *a, **kw: None
        self.handler.audit = lambda *a, **kw: None

        self.responses = []
        self.handler._json = lambda obj, code=200: (
            self.responses.append((obj, code))
        )

        loader = patch.object(
            serve, "load_stage", return_value=self.stage
        )
        saver = patch.object(serve, "save_stage")

        loader.start()
        self.saved = saver.start()
        self.addCleanup(loader.stop)
        self.addCleanup(saver.stop)

    @property
    def job(self):
        return self.stage["jobs"][0]

    def act(self, user="trade1", action="complete", **extra):
        number = 1 if user == "trade1" else 2
        self.handler.user = (
            {
                "role": "agent",
                "username": "agent",
                "display_name": "Test Agent",
                "account_id": "account-agent",
            }
            if user == "agent"
            else {
                "role": "trades",
                "username": user,
                "display_name": COMPANY,
                "account_id": f"account-{number}",
            }
        )
        self.handler.handle_job_action({
            "id": "job-1",
            "action": action,
            "invoice_pence": 1000,
            **extra,
        })
        return self.responses[-1][1]

    def denied(self, expected=403, **kwargs):
        before = copy.deepcopy(self.stage)
        status = self.act(**kwargs)
        self.assertEqual(status, expected)
        self.assertEqual(self.stage, before)
        self.saved.assert_not_called()

    def test_other_contractors_cannot_complete(self):
        self.denied(user="trade2", action="complete")

    def test_other_contractors_cannot_release(self):
        self.denied(user="trade2", action="release")

    def test_other_contractors_cannot_start(self):
        self.job["status"] = "assigned"
        self.denied(user="trade2", action="start")

    def test_other_contractors_cannot_submit_quotes(self):
        self.job["status"] = "quote_requested"
        self.denied(user="trade2", action="submit_quote")

    def test_in_progress_job_cannot_be_taken_over(self):
        self.denied(
            expected=409, user="trade2", action="accept"
        )

    def test_legacy_open_job_with_name_cannot_be_taken(self):
        self.job["status"] = "open"
        self.job.pop("assigned_to_party_id")
        self.denied(
            expected=409, user="trade2", action="accept"
        )

    def test_explicit_party_impersonation_rejected(self):
        self.job["status"] = "open"
        self.job["assigned_to"] = None
        self.job.pop("assigned_to_party_id")
        self.denied(
            user="trade2", action="accept",
            trades_party_id="party-1"
        )

    def test_unlinked_contractor_denied(self):
        self.stage["parties"][0]["account_id"] = None
        self.denied(user="trade1", action="complete")

    def test_own_completion_allowed(self):
        self.assertEqual(
            self.act(user="trade1", action="complete"), 200
        )
        self.assertEqual(self.job["status"], "paid")
        self.saved.assert_called_once()

    def test_own_job_release_allowed(self):
        self.assertEqual(
            self.act(user="trade1", action="release"), 200
        )
        self.assertEqual(self.job["status"], "open")
        self.assertIsNone(self.job["assigned_to"])
        self.assertNotIn("assigned_to_party_id", self.job)

    def test_own_assigned_job_can_start(self):
        self.job["status"] = "assigned"
        self.assertEqual(
            self.act(user="trade1", action="start"), 200
        )
        self.assertEqual(self.job["status"], "in_progress")

    def test_own_open_job_can_be_accepted(self):
        self.job["status"] = "open"
        self.job["assigned_to"] = None
        self.job.pop("assigned_to_party_id")
        self.assertEqual(
            self.act(user="trade1", action="accept"), 200
        )
        self.assertEqual(self.job["assigned_to_party_id"], "party-1")

    def test_own_quote_allowed(self):
        self.job["status"] = "quote_requested"
        self.assertEqual(
            self.act(
                user="trade1", action="submit_quote",
                quote_pence=10000,
            ), 200
        )
        self.assertEqual(self.job["status"], "quoted")
        self.assertEqual(self.job["quotes"][0]["pence"], 10000)

    def test_agent_assignment_with_party_allowed(self):
        self.job["status"] = "open"
        self.job["assigned_to"] = None
        self.job.pop("assigned_to_party_id")
        self.assertEqual(
            self.act(
                user="agent", action="assign",
                tradesperson=COMPANY,
                trades_party_id="party-2",
            ), 200
        )
        self.assertEqual(self.job["assigned_to_party_id"], "party-2")

    def test_agent_assignment_without_party_denied(self):
        self.job["status"] = "open"
        self.denied(
            expected=409, user="agent",
            action="assign", tradesperson=COMPANY
        )

    def test_agent_approval_requires_verified_party(self):
        self.job["status"] = "pending_verification"
        self.job["requested_by"] = COMPANY
        self.job.pop("assigned_to_party_id")
        self.denied(
            expected=409, user="agent",
            action="verify_approve"
        )

    def test_agent_can_approve_verified_request(self):
        self.job["status"] = "pending_verification"
        self.job["requested_by"] = COMPANY
        self.job["requested_by_party_id"] = "party-1"
        self.assertEqual(
            self.act(user="agent", action="verify_approve"), 200
        )
        self.assertEqual(self.job["assigned_to_party_id"], "party-1")
        self.assertEqual(self.job["status"], "in_progress")


if __name__ == "__main__":
    unittest.main()
