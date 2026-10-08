"""Regression tests for the agent-managed acquisition pipeline."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


class ProspectStageTests(unittest.TestCase):
    def setUp(self):
        self.handler = serve.H.__new__(serve.H)
        self.handler.user = {"username": "agent", "display_name": "Agent"}
        self.responses = []
        self.handler._json = lambda payload, status=200: self.responses.append((payload, status))
        self.stage = {
            "cases": [{
                "id": 490, "type": "enquiry", "role": "renter", "status": "new",
                "name": "Prospect", "message": "Interested in viewing",
            }],
            "registrations": [{
                "id": "reg-1", "role": "trades", "status": "pending", "name": "Trade Ltd",
            }],
            "audit_log": [],
        }
        self.load_patch = patch.object(serve, "load_stage", return_value=self.stage)
        self.save_patch = patch.object(serve, "save_stage")
        self.load_patch.start()
        self.saved = self.save_patch.start()
        self.addCleanup(self.load_patch.stop)
        self.addCleanup(self.save_patch.stop)

    def test_tenant_enquiry_stage_is_saved_and_audited_without_changing_case_status(self):
        serve.H.handle_prospect_action(self.handler, {
            "kind": "tenant", "id": "490", "stage": "viewing",
        })
        record = self.stage["cases"][0]
        self.assertEqual(record["status"], "new")
        self.assertEqual(record["prospect_stage"], "viewing")
        self.assertEqual(record["prospect_history"][0]["from"], "enquiry")
        self.assertEqual(record["prospect_history"][0]["to"], "viewing")
        self.assertEqual(self.stage["audit_log"][-1]["action"], "prospect_stage_changed")
        self.saved.assert_called_once_with(self.stage)
        self.assertEqual(self.responses[-1][1], 200)

    def test_invalid_stage_is_rejected_without_writing(self):
        serve.H.handle_prospect_action(self.handler, {
            "kind": "tenant", "id": "490", "stage": "available",
        })
        self.assertEqual(self.responses[-1][1], 400)
        self.saved.assert_not_called()

    def test_case_must_be_a_tenant_enquiry(self):
        self.stage["cases"][0]["type"] = "issue"
        serve.H.handle_prospect_action(self.handler, {
            "kind": "tenant", "id": "490", "stage": "application",
        })
        self.assertEqual(self.responses[-1][1], 404)
        self.saved.assert_not_called()

    def test_trade_registration_can_enter_credentials_stage(self):
        serve.H.handle_prospect_action(self.handler, {
            "kind": "trades", "id": "reg-1", "stage": "credentials_submitted",
        })
        record = self.stage["registrations"][0]
        self.assertEqual(record["status"], "pending")
        self.assertEqual(record["prospect_stage"], "credentials_submitted")
        self.saved.assert_called_once_with(self.stage)


if __name__ == "__main__":
    unittest.main()
