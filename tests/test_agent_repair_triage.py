"""A tenant report must be reviewed by the agent before dispatch."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


class RepairTriageTests(unittest.TestCase):
    def setUp(self):
        self.stage = {
            "properties": [{"id": "home-a", "tenant_party_id": "tenant-a"}],
            "parties": [{"id": "tenant-a", "account_id": "account-tenant",
                         "roles": ["tenant"], "status": "active"}],
            "cases": [], "jobs": [], "next_case_id": 100, "audit_log": [],
        }
        self.handler = serve.H.__new__(serve.H)
        self.handler.user = {"role": "tenant", "display_name": "Resident",
                             "account_id": "account-tenant", "username": "tenant"}
        self.handler.triage = lambda message: {
            "category": "maintenance", "trade": "plumbing", "urgency": 1
        }
        self.handler.store_case_attachments = lambda *args: []
        self.handler.post_msg = lambda *a, **kw: None
        self.handler.audit = lambda *a, **kw: None
        self.responses = []
        self.handler._json = lambda body, code=200: self.responses.append((body, code))
        load = patch.object(serve, "load_stage", return_value=self.stage)
        saved = patch.object(serve, "save_stage")
        load.start()
        self.save = saved.start()
        self.addCleanup(load.stop)
        self.addCleanup(saved.stop)

    def report(self):
        self.handler.user["role"] = "tenant"
        self.handler.handle_tenant_issue({
            "property_id": "home-a", "message": "Water pipe is leaking"
        })
        return self.responses[-1]

    def dispatch(self, role="agent", **extra):
        self.handler.user = {"role": role, "display_name": "Agent" if role == "agent" else "Resident",
                             "account_id": "account-agent" if role == "agent" else "account-tenant",
                             "username": role}
        self.handler.handle_case_action({
            "id": 100, "action": "dispatch_repair",
            "triage_note": "Leaking supply pipe, inspected report",
            "required_trade": "plumbing", **extra,
        })
        return self.responses[-1]

    def test_maintenance_report_stays_awaiting_triage(self):
        response, code = self.report()
        self.assertEqual(code, 200)
        self.assertIsNone(response["job_id"])
        self.assertEqual(self.stage["cases"][0]["status"], "reported")
        self.assertEqual(self.stage["jobs"], [])

    def test_agent_review_opens_exactly_one_job(self):
        self.report()
        result, status = self.dispatch()
        self.assertEqual(status, 200)
        self.assertEqual(self.stage["cases"][0]["status"], "dispatched")
        self.assertEqual(len(self.stage["jobs"]), 1)
        job = self.stage["jobs"][0]
        self.assertEqual(job["case_id"], 100)
        self.assertEqual(job["property_id"], "home-a")
        self.assertEqual(job["required_trade"], "plumbing")
        self.assertEqual(job["triaged_by"], "agent")
        self.assertEqual(job["triage_note"], "Leaking supply pipe, inspected report")

    def test_double_dispatch_rejected_without_duplicate_job(self):
        self.report()
        self.dispatch()
        state = copy.deepcopy(self.stage)
        result, status = self.dispatch()
        self.assertEqual(status, 409)
        self.assertEqual(self.stage, state)
        self.assertEqual(len(self.stage["jobs"]), 1)

    def test_tenant_cannot_dispatch_own_report(self):
        self.report()
        before = copy.deepcopy(self.stage)
        result, code = self.dispatch(role="tenant")
        self.assertEqual(code, 403)
        self.assertEqual(self.stage, before)

    def test_dispatch_without_review_reason_rejected(self):
        self.report()
        before = copy.deepcopy(self.stage)
        result, code = self.dispatch(triage_note="")
        self.assertEqual(code, 400)
        self.assertEqual(self.stage, before)

    def test_non_issue_case_cannot_be_dispatched(self):
        self.report()
        self.stage["cases"][0]["type"] = "enquiry"
        before = copy.deepcopy(self.stage)
        result, code = self.dispatch()
        self.assertEqual(code, 409)
        self.assertEqual(self.stage, before)


if __name__ == "__main__":
    unittest.main()
