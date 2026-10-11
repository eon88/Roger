"""Task 02: case next action, retry-safe issue reports and note isolation (synthetic)."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


class CaseControlTests(unittest.TestCase):
    def setUp(self):
        self.stage = {
            "parties": [
                {"id":"tenant-1", "account_id":"account-tenant", "roles":["tenant"], "status":"active"},
                {"id":"tenant-2", "account_id":"account-other", "roles":["tenant"], "status":"active"},
                {"id":"landlord-1", "account_id":"account-landlord", "roles":["landlord"], "status":"active"},
                {"id":"trades-1", "account_id":"account-trade", "roles":["trades"], "status":"active"},
            ],
            "properties": [
                {"id":"home-1","title":"Test home", "tenant_party_id":"tenant-1",
                 "landlord_party_id":"landlord-1", "rent":90000},
                {"id":"home-2","title":"Other home", "tenant_party_id":"tenant-2", "rent":95000},
            ],
            "cases": [], "jobs": [], "documents": [], "audit_log": [],
            "next_case_id":101,
        }
        self.users = {
            "tenant": {"role":"tenant", "username":"tenant", "account_id":"account-tenant", "display_name":"Test resident"},
            "other": {"role":"tenant", "username":"other", "account_id":"account-other", "display_name":"Other resident"},
            "landlord": {"role":"landlord", "username":"landlord", "account_id":"account-landlord", "display_name":"Test owner"},
            "trade": {"role":"trades", "username":"trade", "account_id":"account-trade", "display_name":"Trade"},
            "agent": {"role":"agent", "username":"agent", "account_id":"account-agent", "display_name":"Agent"},
        }
        self.h = serve.H.__new__(serve.H)
        self.h.user = self.users["tenant"]
        self.h.session_user = lambda: self.h.user
        self.h._json = lambda payload, status=200: self.replies.append((payload, status))
        self.h.triage = lambda message: {"category":"maintenance", "trade":"plumbing", "urgency":1, "safety":0}
        self.h.post_msg = lambda *args, **kw: None
        self.h.store_case_attachments = lambda *args: []
        self.replies = []
        load = patch.object(serve,"load_stage",return_value=self.stage)
        save = patch.object(serve,"save_stage")
        load.start()
        self.saved = save.start()
        self.addCleanup(load.stop)
        self.addCleanup(save.stop)

    def call(self, who, method, expected=200, **data):
        self.h.user = self.users[who]
        getattr(self.h, method)(data)
        payload,status = self.replies[-1]
        self.assertEqual(status,expected,f"{who}/{method}: {payload}")
        return payload

    def report(self, who="tenant", request_id="report-20261011-001", message="Leaking kitchen tap", property_id="home-1", expected=200):
        return self.call(who,"handle_tenant_issue",expected,
                         property_id=property_id,message=message,request_id=request_id)

    def test_new_report_starts_with_one_agent_and_internal_due_date(self):
        payload=self.report()
        case=self.stage["cases"][0]
        self.assertEqual(payload["case_id"], case["id"])
        self.assertEqual(case["next_actor"],"agent")
        self.assertIn("Review",case["next_action"])
        due=datetime.strptime(case["next_due_at"],"%Y-%m-%d").date()
        self.assertGreaterEqual(due,datetime.now(timezone.utc).date())
        self.assertEqual(self.stage["jobs"],[])

    def test_same_request_retry_returns_original_without_duplication(self):
        first=self.report()
        self.saved.reset_mock()
        second=self.report()
        self.assertEqual(second["case_id"],first["case_id"])
        self.assertTrue(second["already_received"])
        self.assertEqual(len(self.stage["cases"]),1)
        self.saved.assert_not_called()
        self.report(message="Another issue",expected=409)
        self.assertEqual(len(self.stage["cases"]),1)
        self.report(who="other", property_id="home-2")
        self.assertEqual(len(self.stage["cases"]),2)

    def test_foreign_tenant_cannot_reuse_a_request_to_read_another_case(self):
        self.report()
        self.report(who="other",property_id="home-1",expected=403)
        self.assertEqual(len(self.stage["cases"]),1)

    def test_agent_sets_next_action_with_validation_and_audit(self):
        cid=self.report()["case_id"]
        due=(datetime.now(timezone.utc).date()+timedelta(days=3)).isoformat()
        self.call("tenant","handle_case_action",403,id=cid,action="set_next_action",
                  next_actor="tenant",next_action="Send photographs",next_due_at=due)
        self.call("agent","handle_case_action",400,id=cid,action="set_next_action",
                  next_actor="tenant",next_action="Send photographs",next_due_at="2099-02-31")
        self.call("agent","handle_case_action",409,id=cid,action="set_next_action",
                  next_actor="trades",next_action="Attend",next_due_at=due)
        self.call("agent","handle_case_action",200,id=cid,action="set_next_action",
                  next_actor="tenant",next_action="Send photographs",next_due_at=due)
        case=self.stage["cases"][0]
        self.assertEqual((case["next_actor"],case["next_action"],case["next_due_at"]),
                         ("tenant","Send photographs",due))
        self.assertEqual(self.stage["audit_log"][-1]["action"],"case_next_action_set")
        self.call("agent","handle_case_action",200,id=cid,action="close",reason="Issue dealt with")
        self.assertIsNone(case["next_actor"])
        self.call("agent","handle_case_action",409,id=cid,action="set_next_action",
                  next_actor="agent",next_action="Call",next_due_at=due)
        self.call("agent","handle_case_action",200,id=cid,action="reopen")
        self.assertEqual(case["next_actor"],"agent")

    def test_private_notes_are_not_in_tenant_or_landlord_stage(self):
        cid=self.report()["case_id"]
        self.call("agent","handle_case_action",id=cid,action="note",
                  text="Private landlord dispute: do not disclose")
        for who in ("tenant","landlord"):
            self.h.user=self.users[who]
            self.h.serve_scoped_stage()
            data,status=self.replies[-1]
            self.assertEqual(status,200)
            self.assertEqual(len(data["cases"]),1)
            self.assertNotIn("internal_notes",data["cases"][0])
        self.h.user=self.users["agent"]
        self.h.serve_scoped_stage()
        self.assertEqual(self.replies[-1][0]["cases"][0]["internal_notes"][0]["text"],
                         "Private landlord dispute: do not disclose")

    def test_job_transitions_update_one_authoritative_next_actor(self):
        cid=self.report()["case_id"]
        job={"id":"job-1","case_id":cid,"property_id":"home-1",
             "assigned_to_party_id":"trades-1"}
        self.stage["jobs"].append(job)
        for status,role in [
            ("quote_requested","trades"),("quoted","agent"),
            ("awaiting_prework_approval","landlord"),("assigned","trades"),
            ("in_progress","trades"),("invoice_submitted","agent"),
            ("invoice_approved","agent"),("partially_paid","agent"),("credited","agent")
        ]:
            job["status"]=status
            self.h.update_case_from_job(self.stage,job)
            self.assertEqual(self.stage["cases"][0]["next_actor"],role,status)
            self.assertTrue(self.stage["cases"][0]["next_action"])
            self.assertTrue(self.stage["cases"][0]["next_due_at"])
        self.stage["cases"][0]["status"]="closed"
        self.h.case_next(self.stage["cases"][0],None,None,None)
        job["status"]="quoted"
        self.h.update_case_from_job(self.stage,job)
        self.assertIsNone(self.stage["cases"][0]["next_actor"])

    def test_undone_repair_cannot_be_falsely_reopened_as_completed(self):
        cid=self.report()["case_id"]
        self.call("tenant","handle_case_action",409,id=cid,action="reopen_unresolved",
                  text="Not fixed")
        case=self.stage["cases"][0]
        case["status"]="awaiting_confirmation"
        self.call("tenant","handle_case_action",id=cid,action="reopen_unresolved",
                  text="Still leaking")
        self.assertEqual(case["status"],"reported")
        self.assertEqual(case["next_actor"],"agent")
        self.call("tenant","handle_case_action",409,id=cid,action="reopen_unresolved",
                  text="Still leaking")
        self.assertEqual(self.stage["audit_log"][-1]["action"],"tenant_reopened_unresolved")


if __name__ == "__main__":
    unittest.main()
