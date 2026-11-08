"""Roger v1 single-release stage: structured repair evidence + Agent Desk briefing."""
import copy
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "stage-clone"))
import agent_briefing
import repair_case_dossier
import serve


class RepairDossierTests(unittest.TestCase):
    def test_server_records_unverified_evidence_and_recomputes_risk(self):
        report = repair_case_dossier.normalise_dossier({
            "description": "I smell gas in the kitchen",
            "history": [{"question": "Where is the smell strongest?",
                         "answer": "Near the boiler"}],
        })
        self.assertEqual(report["source"], "tenant_submitted_unverified")
        self.assertTrue(report["needs_agent_review"])
        self.assertIn("Possible gas leak", report["safety_flags"])
        self.assertEqual(report["suggested_trade"], "gas")
        self.assertNotIn("ai_verified", report)

    def test_rejects_forged_model_decisions_and_bad_answers(self):
        invalid = [
            {"description": "Pipe leaking", "history": [], "engine": "verified"},
            {"description": "Pipe leaking", "history": [{"question": "", "answer": "yes"}]},
            {"description": "Pipe leaking", "history": [{"question": "Where?", "answer": "A" * 501}]},
            {"description": "Pipe leaking", "history": "message"},
            {"description": "Pipe leaking", "history": [{}] * 4},
        ]
        for entry in invalid:
            with self.subTest(entry=str(entry)[:45]), self.assertRaises(ValueError):
                repair_case_dossier.normalise_dossier(entry)


class TenantRepairPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.stage = {
            "properties": [{"id": "flat-1", "tenant_party_id": "tenant-1"},
                           {"id": "flat-2", "tenant_party_id": "tenant-2"}],
            "parties": [{"id": "tenant-1", "roles": ["tenant"], "status": "active",
                         "account_id": "account-1"},
                        {"id": "tenant-2", "roles": ["tenant"], "status": "active",
                         "account_id": "account-2"}],
            "cases": [], "jobs": [], "notifications": [], "audit_log": [], "next_case_id": 50,
        }
        self.handler = serve.H.__new__(serve.H)
        self.handler.user = {"role": "tenant", "account_id": "account-1",
                             "display_name": "Synthetic Resident", "username": "tenant"}
        self.handler.triage = lambda message: {
            "category": "maintenance", "trade": "plumbing", "urgency": 0, "safety": 0.01,
        }
        self.replies = []
        self.handler._json = lambda body, code=200: self.replies.append((body, code))
        a = patch.object(serve, "load_stage", return_value=self.stage)
        b = patch.object(serve, "save_stage")
        a.start()
        self.saved = b.start()
        self.addCleanup(a.stop)
        self.addCleanup(b.stop)

    def report(self, diagnostic, message="The kitchen tap is leaking", req="sample123456"):
        self.handler.handle_tenant_issue({
            "property_id": "flat-1", "message": message,
            "email": "synthetic@example.invalid", "request_id": req,
            "diagnostic": diagnostic,
        })
        return self.replies[-1]

    def test_normal_case_preserves_structured_answers_for_agent(self):
        ctx = {"description": "The kitchen tap is leaking",
               "history": [{"question": "Where?", "answer": "Under the sink"}]}
        body, code = self.report(ctx)
        self.assertEqual(code, 200, body)
        self.assertEqual(len(self.stage["cases"]), 1)
        case = self.stage["cases"][0]
        self.assertEqual(case["diagnostic_dossier"]["answers"][0]["answer"], "Under the sink")
        self.assertEqual(case["diagnostic_dossier"]["source"], "tenant_submitted_unverified")
        self.assertEqual(len(self.stage["jobs"]), 0)
        self.assertEqual(case["status"], "reported")
        self.assertEqual(self.stage["audit_log"][-1]["action"], "case_created")

    def test_emergency_in_answers_overrides_low_model_urgency(self):
        ctx = {"description": "There is a problem with the kitchen",
               "history": [{"question": "What have you noticed?", "answer": "I smell gas"}]}
        _, code = self.report(ctx)
        self.assertEqual(code, 200)
        case = self.stage["cases"][0]
        self.assertEqual(case["triage"]["urgency"], 2)
        self.assertIn("Possible gas leak", case["triage"]["safety_flags"])
        self.assertEqual(len(self.stage["notifications"]), 1)
        self.assertEqual(len(self.stage["jobs"]), 0)

    def test_changed_interview_cannot_reuse_same_request_id(self):
        ctx = {"description": "Tap leaking", "history": []}
        self.assertEqual(self.report(ctx)[1], 200)
        self.saved.reset_mock()
        second, code = self.report(ctx)
        self.assertEqual(code, 200)
        self.assertTrue(second["already_received"])
        self.saved.assert_not_called()
        changed = {"description": "Tap leaking", "history": [
            {"question": "When?", "answer": "Yesterday"}
        ]}
        _, code = self.report(changed)
        self.assertEqual(code, 409)
        self.assertEqual(len(self.stage["cases"]), 1)

    def test_invalid_diagnostic_never_creates_case(self):
        _, code = self.report({"description": "Pipe leak", "history": [],
                                "safety_flags": []})
        self.assertEqual(code, 400)
        self.assertEqual(self.stage["cases"], [])
        self.saved.assert_not_called()


class AgentBriefingTests(unittest.TestCase):
    TODAY = date(2026, 11, 8)

    def test_priority_cards_are_evidence_linked_and_read_only(self):
        stage = {
            "cases": [
                {"id": 1, "status": "reported", "triage": {"urgency": 2},
                 "next_actor": "agent", "property_id": "flat-one", "next_due_at": "2026-11-09"},
                {"id": 2, "status": "reported", "triage": {"urgency": 0},
                 "next_actor": "tenant", "next_action": "Send photos",
                 "next_due_at": "2026-11-01"},
                {"id": 3, "status": "closed", "triage": {"urgency": 2}},
            ],
            "tasks": [{"id": "task-1", "status": "open", "title": "Call contractor",
                       "priority": "high", "owner": "Agent", "due_date": "2026-11-06"},
                      {"id": "task-2", "status": "completed", "title": "Done",
                       "due_date": "2026-11-06"}],
            "approvals": [{"id": "approval-1", "status": "pending"}],
            "compliance_records": [
                {"id": "compliance-1", "property_id": "flat-one",
                 "record_status": "recorded", "requirement_type": "gas_safety",
                 "expiry_date": "2026-11-01"},
                {"id": "compliance-2", "record_status": "missing",
                 "requirement_type": "eicr"},
                {"id": "compliance-3", "record_status": "recorded",
                 "requirement_type": "epc", "expiry_date": "2026-01-01",
                 "superseded_by": "compliance-4"},
            ],
            "registrations": [{"id": "reg-1", "role": "trades", "status": "approved",
                               "name": "Synthetic Plumber", "contractor_verification": {
                                   "valid_until": "2026-11-10"}}],
            "tenancies": [{"id": "tenancy-1", "status": "active",
                           "end_date": "2026-11-30", "property_id": "flat-one"}],
        }
        before = copy.deepcopy(stage)
        output = agent_briefing.make_briefing(stage, today=self.TODAY)
        self.assertEqual(output["engine"], "deterministic-rules")
        self.assertTrue(output["read_only"])
        self.assertEqual(output["priority_counts"]["urgent"], 1)
        self.assertEqual(output["cards"][0]["key"], "case:1")
        self.assertEqual(sum(c["key"] == "case:1" for c in output["cards"]), 1)
        self.assertNotIn("case:3", [c["key"] for c in output["cards"]])
        self.assertNotIn("task:task-2", [c["key"] for c in output["cards"]])
        self.assertNotIn("compliance:compliance-3", [c["key"] for c in output["cards"]])
        self.assertIn("trades:reg-1", [c["key"] for c in output["cards"]])
        self.assertIn("tenancy:tenancy-1", [c["key"] for c in output["cards"]])
        self.assertEqual(stage, before)

    def test_unknown_or_empty_data_does_not_claim_everything_is_compliant(self):
        b = agent_briefing.make_briefing({}, today=self.TODAY)
        self.assertEqual(b["total_actions"], 0)
        self.assertIn("Missing records", b["limitations"])
        self.assertEqual(b["cards"], [])

    def test_agent_only_http_route_and_no_mutation(self):
        h = serve.H.__new__(serve.H)
        h.path = "/api/agent/briefing"
        seen = []
        h._json = lambda obj, code=200: seen.append((obj, code))
        permitted = [False]
        def require(roles=None):
            if not permitted[0]:
                h._json({"error": "not your portal"}, 403)
                return None
            self.assertEqual(roles, {"agent"})
            return {"role": "agent"}
        h.require = require
        with patch.object(serve, "load_stage", return_value={"cases": []}) as load, patch.object(serve, "save_stage") as save:
            h._do_GET_with_agency_boundary()
            self.assertEqual(seen[-1][1], 403)
            load.assert_not_called()
            permitted[0] = True
            h._do_GET_with_agency_boundary()
            self.assertEqual(seen[-1][1], 200)
            self.assertEqual(seen[-1][0]["total_actions"], 0)
            load.assert_called_once()
            save.assert_not_called()


class AgentUIJavaScriptTests(unittest.TestCase):
    def test_agent_portal_javascript_compiles(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is not installed on test runner")
        s = (ROOT / "stage-clone" / "agent.html").read_text(encoding="utf-8")
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", s, flags=re.S | re.I)
        self.assertTrue(scripts)
        for source in scripts:
            with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8",
                                             delete=False) as tmp:
                tmp.write(source)
                target = Path(tmp.name)
            try:
                checked = subprocess.run([node, "--check", str(target)], capture_output=True,
                                         text=True, timeout=20)
                self.assertEqual(checked.returncode, 0, checked.stderr[:1500])
            finally:
                target.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
