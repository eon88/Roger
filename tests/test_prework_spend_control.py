"""New tenant repair jobs require quote approval before contractor starts work."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve

COMPANY = "Example Plumbing"


class PreworkCostApprovalTests(unittest.TestCase):
    def setUp(self):
        self.stage = {
            "parties": [
                {"id": "trade-a", "account_id": "account-trade", "source_registration_id": "trade-reg-1", "roles": ["trades"],
                 "display_name": COMPANY, "status": "active"},
                {"id": "owner-a", "account_id": "account-owner", "roles": ["landlord"],
                 "display_name": "Example Owner", "status": "active"},
                {"id": "owner-b", "account_id": "account-owner-b", "roles": ["landlord"],
                 "display_name": "Other Owner", "status": "active"},
            ],
            "properties": [{"id": "home-a", "landlord_party_id": "owner-a", "landlord": "Example Owner"}],
            "cases": [{"id": 10, "type": "issue", "property_id": "home-a", "status": "dispatched"}],
            "jobs": [{"id": "job-1", "case_id": 10, "property_id": "home-a",
                      "message": "Pipe leak", "status": "triaged",
                      "requires_prework_quote": True, "required_trade": None,
                      "assigned_to": None, "invoice_pence": None}],
            "approvals": [],
            "registrations": [{
                "id": "trade-reg-1", "role": "trades", "name": COMPANY,
                "status": "approved", "prospect_stage": "available",
                "party_id": "trade-a", "credentials_checked_at": "2026-10-01T10:00:00Z",
                "trades": ["plumbing"], "insurance_expiry": "2099-12-31",
            }],
            "management_agreements": [{
                "id": "management-a", "agreement_type": "full_management", "landlord_party_id": "owner-a",
                "property_ids": ["home-a"], "status": "active",
                "signed_at": "2026-10-01", "updated_at": "2026-10-01T10:00:00Z",
                "spending_limit_pence": 15000,
            }],
            "authority": {"standing_limit_pence": 15000},
            "audit_log": [],
        }
        self.users = {
            "agent": {"role": "agent", "username": "agent",
                      "display_name": "Agent", "account_id": "account-agent"},
            "trade": {"role": "trades", "username": "trade",
                      "display_name": COMPANY, "account_id": "account-trade"},
            "owner": {"role": "landlord", "username": "owner",
                      "display_name": "Example Owner", "account_id": "account-owner"},
            "other_owner": {"role": "landlord", "username": "other_owner",
                            "display_name": "Other Owner", "account_id": "account-owner-b"},
        }
        self.handler = serve.H.__new__(serve.H)
        self.handler.audit = lambda *args, **kwargs: None
        self.handler.post_msg = lambda *args, **kwargs: None
        self.handler.sync_case = lambda stage, case_id, status: stage["cases"][0].update(status=status)
        self.handler.approved_trades = lambda stage: [{"company": COMPANY}]
        self.responses = []
        self.handler._json = lambda data, code=200: self.responses.append((data, code))
        load = patch.object(serve, "load_stage", return_value=self.stage)
        saved = patch.object(serve, "save_stage")
        load.start()
        self.saved = saved.start()
        self.addCleanup(load.stop)
        self.addCleanup(saved.stop)

    def job_action(self, role, action, **data):
        self.handler.user = self.users[role]
        self.handler.handle_job_action({
            "id": "job-1", "action": action, **data
        })
        return self.responses[-1][1]

    def request_quote(self):
        return self.job_action("agent", "request_quote",
                               tradesperson=COMPANY, trades_party_id="trade-a")

    def submit(self, amount):
        return self.job_action("trade", "submit_quote", quote_pence=amount)

    def approve_quote(self):
        return self.job_action("agent", "approve_quote")

    def landlord_decides(self, who="owner", action="approve", reason=""):
        self.handler.user = self.users[who]
        self.handler.handle_landlord_action({
            "id": self.stage["approvals"][0]["id"], "action": action, "reason": reason
        })
        return self.responses[-1][1]

    def test_contractor_requires_linked_approved_registration(self):
        self.stage["registrations"][0]["party_id"] = None
        before = copy.deepcopy(self.stage)
        self.assertEqual(self.request_quote(), 409)
        self.assertEqual(self.stage, before)

    def test_contractor_requires_current_insurance(self):
        self.stage["registrations"][0]["insurance_expiry"] = "2020-01-01"
        before = copy.deepcopy(self.stage)
        self.assertEqual(self.request_quote(), 409)
        self.assertEqual(self.stage, before)

    def test_contractor_cannot_work_outside_checked_trade(self):
        self.stage["registrations"][0]["trades"] = ["electrical"]
        before = copy.deepcopy(self.stage)
        self.assertEqual(self.request_quote(), 409)
        self.assertEqual(self.stage, before)

    def test_contractor_suspension_blocks_new_job(self):
        self.stage["registrations"][0]["prospect_stage"] = "suspended"
        before = copy.deepcopy(self.stage)
        self.assertEqual(self.request_quote(), 409)
        self.assertEqual(self.stage, before)

    def test_claimed_gas_safe_number_is_not_verified_evidence(self):
        self.stage["jobs"][0]["required_trade"] = "gas"
        self.stage["registrations"][0]["trades"].append("gas")
        self.stage["registrations"][0]["gas_safe_number"] = "CLAIMED-NUMBER"
        before = copy.deepcopy(self.stage)
        self.assertEqual(self.request_quote(), 409)
        self.assertEqual(self.stage, before)

    def test_unpriced_job_cannot_be_claimed_or_directly_assigned(self):
        before = copy.deepcopy(self.stage)
        self.assertEqual(self.job_action("trade", "accept"), 409)
        self.assertEqual(self.job_action("agent", "assign",
                                        tradesperson=COMPANY, trades_party_id="trade-a"), 409)
        self.assertEqual(self.stage, before)

    def test_approved_small_quote_only_assigns_not_starts_work(self):
        self.assertEqual(self.request_quote(), 200)
        self.assertEqual(self.submit(12000), 200)
        self.assertEqual(self.approve_quote(), 200)
        job = self.stage["jobs"][0]
        self.assertEqual(job["status"], "assigned")
        self.assertEqual(job["approved_quote_pence"], 12000)
        self.assertTrue(job["work_authorised_at"])
        self.assertEqual(self.job_action("trade", "start"), 200)
        self.assertEqual(job["status"], "in_progress")

    def test_over_limit_requires_right_landlord_before_start(self):
        self.assertEqual(self.request_quote(), 200)
        self.assertEqual(self.submit(25000), 200)
        self.assertEqual(self.approve_quote(), 200)
        job = self.stage["jobs"][0]
        self.assertEqual(job["status"], "awaiting_prework_approval")
        self.assertEqual(self.stage["approvals"][0]["approval_type"], "prework_quote")
        before = copy.deepcopy(self.stage)
        self.assertEqual(self.job_action("trade", "start"), 409)
        self.assertEqual(self.landlord_decides(who="agent"), 403)
        self.assertEqual(self.landlord_decides(who="other_owner"), 403)
        self.assertEqual(self.stage, before)
        self.assertEqual(self.landlord_decides(), 200)
        self.assertEqual(job["status"], "assigned")
        self.assertNotIn("paid_at", job)
        self.assertEqual(self.landlord_decides(), 409)
        self.assertEqual(self.job_action("trade", "start"), 200)

    def test_landlord_can_decline_and_trade_can_requote(self):
        self.request_quote()
        self.submit(25000)
        self.approve_quote()
        self.assertEqual(self.landlord_decides(action="reject", reason="Too expensive"), 200)
        job = self.stage["jobs"][0]
        self.assertEqual(job["status"], "quote_requested")
        self.assertNotIn("work_authorised_at", job)
        self.assertEqual(self.submit(11000), 200)
        self.assertEqual(self.approve_quote(), 200)
        self.assertEqual(job["status"], "assigned")

    def test_without_signed_explicit_mandate_no_spending_is_authorised(self):
        self.stage["management_agreements"] = []
        self.request_quote()
        self.submit(12000)
        before = copy.deepcopy(self.stage)
        self.assertEqual(self.approve_quote(), 409)
        self.assertEqual(self.stage, before)

    def test_wrong_landlords_agreement_cannot_grant_spending(self):
        self.stage["management_agreements"][0]["landlord_party_id"] = "owner-b"
        self.request_quote()
        self.submit(12000)
        before = copy.deepcopy(self.stage)
        self.assertEqual(self.approve_quote(), 409)
        self.assertEqual(self.stage, before)

    def test_let_only_agreement_is_not_full_management_authority(self):
        self.stage["management_agreements"][0]["agreement_type"] = "let_only"
        self.request_quote()
        self.submit(12000)
        before = copy.deepcopy(self.stage)
        self.assertEqual(self.approve_quote(), 409)
        self.assertEqual(self.stage, before)

    def test_per_property_limit_replaces_global_demo_limit(self):
        self.stage["management_agreements"][0]["spending_limit_pence"] = 5000
        # The stale global £150 figure MUST NOT authorise this £120 job.
        self.request_quote()
        self.submit(12000)
        self.assertEqual(self.approve_quote(), 200)
        self.assertEqual(self.stage["jobs"][0]["status"], "awaiting_prework_approval")
        self.assertEqual(self.stage["approvals"][0]["mandate_snapshot"]["limit_pence"], 5000)

    def test_changed_mandate_voids_pending_owner_approval(self):
        self.request_quote()
        self.submit(25000)
        self.approve_quote()
        self.stage["management_agreements"][0]["spending_limit_pence"] = 30000
        before = copy.deepcopy(self.stage)
        self.assertEqual(self.landlord_decides(), 409)
        self.assertEqual(self.stage, before)
        self.assertNotIn("work_authorised_at", self.stage["jobs"][0])

    def test_invoice_over_approved_quote_does_not_change_data(self):
        self.request_quote()
        self.submit(12000)
        self.approve_quote()
        self.job_action("trade", "start")
        before = copy.deepcopy(self.stage)
        self.assertEqual(self.job_action("trade", "complete", invoice_pence=14000), 409)
        self.assertEqual(self.stage, before)
        self.assertEqual(self.job_action("trade", "complete", invoice_pence=12000), 200)
        job = self.stage["jobs"][0]
        self.assertEqual(job["status"], "invoice_submitted")
        self.assertNotIn("paid_at", job)


if __name__ == "__main__":
    unittest.main()
