"""Synthetic repair pilot: all four roles and the complete approval/payment sequence."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve

TRADE = "R. Doyle Gas & Heat"


class FourRoleRepairPilotTests(unittest.TestCase):
    def setUp(self):
        self.stage = {
            "parties": [
                {"id": "tenant-1", "account_id": "account-tenant", "roles": ["tenant"], "status": "active"},
                {"id": "tenant-2", "account_id": "account-stranger", "roles": ["tenant"], "status": "active"},
                {"id": "owner-1", "account_id": "account-landlord", "roles": ["landlord"],
                 "status": "active", "display_name": "Test Owner"},
                {"id": "trade-1", "account_id": "account-trade", "roles": ["trades"],
                 "status": "active", "display_name": TRADE},
            ],
            "properties": [
                {"id": "home-1", "tenant_party_id": "tenant-1", "landlord_party_id": "owner-1",
                 "landlord": "Test Owner", "title": "Pilot Home", "area": "Leeds"},
                {"id": "home-2", "tenant_party_id": "tenant-2", "title": "Other Home", "area": "York"},
            ],
            "cases": [], "jobs": [], "approvals": [], "documents": [],
            "next_case_id": 51, "audit_log": [],
            "authority": {"standing_limit_pence": 15000},
        }
        self.users = {
            "tenant": {"role": "tenant", "username": "tenant", "display_name": "Resident",
                       "account_id": "account-tenant"},
            "stranger": {"role": "tenant", "username": "stranger", "display_name": "Resident",
                         "account_id": "account-stranger"},
            "landlord": {"role": "landlord", "username": "owner", "display_name": "Test Owner",
                         "account_id": "account-landlord"},
            "trade": {"role": "trades", "username": "trade", "display_name": TRADE,
                      "account_id": "account-trade"},
            "agent": {"role": "agent", "username": "agent", "display_name": "Agent",
                      "account_id": "account-agent"},
        }
        self.handler = serve.H.__new__(serve.H)
        self.handler.user = self.users["tenant"]
        self.handler.session_user = lambda: self.handler.user
        self.handler.triage = lambda msg: {
            "category": "maintenance", "trade": "plumbing", "urgency": 1, "safety": 0
        }
        self.handler.store_case_attachments = lambda *args: []
        self.handler.audit = lambda *args, **kwargs: None
        self.handler.post_msg = lambda *args, **kwargs: None
        self.handler.approved_trades = lambda stage: [
            {"company": TRADE, "trades": ["plumbing"], "gas_safe": False}]
        def sync_case(stage, case_id, status):
            next(c for c in stage["cases"] if c["id"] == case_id)["status"] = status
        self.handler.sync_case = sync_case
        self.responses = []
        self.handler._json = lambda payload, code=200: self.responses.append((payload, code))
        load = patch.object(serve, "load_stage", return_value=self.stage)
        saved = patch.object(serve, "save_stage")
        load.start()
        self.saved = saved.start()
        self.addCleanup(load.stop)
        self.addCleanup(saved.stop)

    def do(self, who, method, **payload):
        self.handler.user = self.users[who]
        getattr(self.handler, method)(payload)
        body, code = self.responses[-1]
        self.assertEqual(code, 200, f"{who}/{method}: {body}")
        return body

    def test_4_role_repair_requires_every_gate(self):
        result = self.do("tenant", "handle_tenant_issue", property_id="home-1",
                         message="Water leak behind kitchen sink")
        case_id = result["case_id"]
        self.assertEqual(self.stage["jobs"], [])
        self.assertEqual(self.stage["cases"][0]["status"], "reported")

        # Unrelated tenant never receives the case or job.
        self.handler.user = self.users["stranger"]
        self.handler.serve_scoped_stage()
        scoped, code = self.responses[-1]
        self.assertEqual(code, 200)
        self.assertEqual(scoped["cases"], [])
        self.assertEqual(scoped["jobs"], [])

        self.do("agent", "handle_case_action", id=case_id,
                action="dispatch_repair", required_trade="plumbing",
                triage_note="Leak needs repair")
        job = self.stage["jobs"][0]
        jid = job["id"]
        self.assertEqual(job["status"], "triaged")
        self.handler.user = self.users["trade"]
        self.handler.serve_scoped_stage()
        self.assertEqual(self.responses[-1][0]["jobs"], [])

        self.do("agent", "handle_job_action", id=jid, action="request_quote",
                tradesperson=TRADE, trades_party_id="trade-1")
        self.do("trade", "handle_job_action", id=jid, action="submit_quote",
                quote_pence=25000, note="Repair pipe and wall")
        self.do("agent", "handle_job_action", id=jid, action="approve_quote")
        self.assertEqual(job["status"], "awaiting_prework_approval")
        self.assertNotIn("work_authorised_at", job)

        self.do("landlord", "handle_landlord_action", id=self.stage["approvals"][0]["id"],
                action="approve")
        self.assertEqual(job["status"], "assigned")
        self.assertTrue(job["work_authorised_at"])
        self.do("trade", "handle_job_action", id=jid, action="start")
        self.assertEqual(job["status"], "in_progress")

        # Completion is not proof of payment; tenants can verify the repair.
        self.do("trade", "handle_job_action", id=jid, action="complete", invoice_pence=25000)
        self.assertEqual(job["status"], "invoice_submitted")
        self.assertEqual(self.stage["cases"][0]["status"], "awaiting_confirmation")
        self.assertNotIn("paid_at", job)
        self.do("tenant", "handle_case_action", id=case_id, action="confirm_resolution")
        self.assertEqual(self.stage["cases"][0]["status"], "closed")

        self.do("agent", "handle_job_action", id=jid, action="approve_invoice")
        self.assertEqual(job["status"], "invoice_approved")
        self.assertNotIn("paid_at", job)
        self.do("agent", "handle_job_action", id=jid, action="record_payment",
                payment_reference="BANK-TEST-001", payment_amount_pence=25000,
                payment_date=datetime.now(timezone.utc).date().isoformat())
        self.assertEqual(job["status"], "paid")
        self.assertEqual(job["payment_reference"], "BANK-TEST-001")

        # Only the real resident sees this report.
        self.handler.user = self.users["tenant"]
        self.handler.serve_scoped_stage()
        result, code = self.responses[-1]
        self.assertEqual(len(result["cases"]), 1)
        self.assertEqual(result["cases"][0]["status"], "closed")
        self.handler.user = self.users["stranger"]
        self.handler.serve_scoped_stage()
        self.assertEqual(self.responses[-1][0]["cases"], [])


if __name__ == "__main__":
    unittest.main()
