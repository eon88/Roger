"""B01: safe replay of job actions, invoice requests and owner approvals."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "stage-clone"))
import serve
import workflow_engine as w


class ActionReplayContractTests(unittest.TestCase):
    def test_payload_bound_replay_and_conflicting_actor(self):
        row = {"id": "job-1", "status": "partially_paid"}
        payload = {"id": "job-1", "action": "record_payment",
                   "payment_pence": 2500, "request_id": "payment-key-100"}
        self.assertFalse(w.check_action_replay(
            row, request_id=payload["request_id"], action="record_payment",
            actor="office-1", payload=payload))
        self.assertTrue(w.remember_action_request(
            row, request_id=payload["request_id"], action="record_payment",
            actor="office-1", role="agent", at="2026-11-10T12:00:00Z", payload=payload))
        self.assertTrue(w.check_action_replay(
            row, request_id=payload["request_id"], action="record_payment",
            actor="office-1", payload=copy.deepcopy(payload)))
        with self.assertRaises(w.RequestReplayConflict):
            w.check_action_replay(
                row, request_id=payload["request_id"], action="record_payment",
                actor="office-1", payload={**payload, "payment_pence": 2600})
        with self.assertRaises(w.RequestReplayConflict):
            w.check_action_replay(
                row, request_id=payload["request_id"], action="record_payment",
                actor="someone-else", payload=payload)
        with self.assertRaises(w.RequestReplayConflict):
            w.remember_action_request(
                row, request_id=payload["request_id"], action="record_payment",
                actor="office-1", role="agent", at="2026-11-10T12:00:01Z",
                payload=payload)
        self.assertEqual(len(row["workflow_requests"]), 1)

    def test_bad_token_does_not_write_history(self):
        row = {}
        with self.assertRaises(w.InvalidTransition):
            w.remember_action_request(
                row, request_id="short", action="approve", actor="office",
                role="agent", at="2026-11-10", payload={"action": "approve"})
        self.assertEqual(row, {})


class HandlerReplayTests(unittest.TestCase):
    def setUp(self):
        self.stage = {
            "properties": [{
                "id": "home-1", "landlord_party_id": "owner-1",
                "landlord": "Example owner"
            }],
            "parties": [{
                "id": "owner-1", "account_id": "owner-login", "roles": ["landlord"],
                "status": "active"
            }],
            "cases": [{"id": 10, "property_id": "home-1",
                       "status": "dispatched", "type": "issue"}],
            "jobs": [{"id": "job-1", "property_id": "home-1", "case_id": 10,
                      "status": "invoice_submitted", "invoice_pence": 12500,
                      "message": "Completed repair"}],
            "approvals": [],
            "audit_log": [],
        }
        self.handler = serve.H.__new__(serve.H)
        self.responses = []
        self.handler._json = lambda payload, status=200: self.responses.append((payload, status))
        self.handler.user = {
            "role": "agent", "username": "office",
            "display_name": "Office manager", "account_id": "office-login"
        }
        load = patch.object(serve, "load_stage", return_value=self.stage)
        saved = patch.object(serve, "save_stage")
        load.start()
        self.addCleanup(load.stop)
        self.saved = saved.start()
        self.addCleanup(saved.stop)

    def run_job(self, **fields):
        self.handler.user = {
            "role": "agent", "username": "office",
            "display_name": "Office manager", "account_id": "office-login"
        }
        self.handler.handle_job_action({
            "id": "job-1", "action": "send_to_landlord", "request_id": "job-request-100",
            **fields,
        })
        return self.responses[-1]

    def run_owner(self, **fields):
        self.handler.user = {
            "role": "landlord", "username": "owner-login",
            "display_name": "Example owner", "account_id": "owner-login"
        }
        self.handler.handle_landlord_action({
            "id": self.stage["approvals"][0]["id"],
            "action": "approve", "request_id": "approval-request-100",
            **fields,
        })
        return self.responses[-1]

    def test_repeat_invoice_handoff_is_one_approval_and_one_message(self):
        payload, status = self.run_job()
        self.assertEqual(status, 200, payload)
        self.assertEqual(len(self.stage["approvals"]), 1)
        self.assertEqual(len(self.stage["cases"][0]["thread"]), 1)
        payload, status = self.run_job()
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload["already_processed"])
        self.assertEqual(len(self.stage["approvals"]), 1)
        self.assertEqual(len(self.stage["cases"][0]["thread"]), 1)
        self.assertEqual(len(self.stage["jobs"][0]["workflow_requests"]), 1)

    def test_one_landlord_approval_survives_retry_without_second_effect(self):
        self.run_job()
        payload, status = self.run_owner()
        self.assertEqual(status, 200, payload)
        first_thread_count = len(self.stage["cases"][0]["thread"])
        payload, status = self.run_owner()
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload["already_processed"])
        self.assertEqual(len(self.stage["cases"][0]["thread"]), first_thread_count)
        self.assertEqual(self.stage["approvals"][0]["status"], "approved")
        self.assertEqual(len(self.stage["approvals"][0]["workflow_requests"]), 1)

    def test_changed_replayed_approval_is_rejected(self):
        self.run_job()
        self.run_owner()
        _, status = self.run_owner(reason="A changed replay")
        self.assertEqual(status, 409)
        self.assertEqual(len(self.stage["approvals"][0]["workflow_requests"]), 1)

    def test_agent_cannot_impersonate_landlord_on_invoice_approval(self):
        self.run_job()
        before = copy.deepcopy(self.stage)
        self.handler.user = {
            "role": "agent", "username": "office",
            "display_name": "Office manager", "account_id": "office-login"
        }
        self.handler.handle_landlord_action({
            "id": self.stage["approvals"][0]["id"],
            "action": "approve", "request_id": "owner-decision-123"
        })
        self.assertEqual(self.responses[-1][1], 403)
        self.assertEqual(self.stage, before)

    def test_foreign_landlord_cannot_replay_approval(self):
        self.run_job()
        self.run_owner()
        self.handler.user = {
            "role": "landlord", "username": "not-owner",
            "account_id": "other-owner", "display_name": "Stranger"
        }
        self.handler.handle_landlord_action({
            "id": self.stage["approvals"][0]["id"], "action": "approve",
            "request_id": "approval-request-100",
        })
        self.assertEqual(self.responses[-1][1], 403)


    def test_replayed_case_reply_creates_exactly_one_message(self):
        self.handler.user = {
            "role": "agent", "username": "office",
            "display_name": "Office manager", "account_id": "office-login"
        }
        request = {
            "id": 10, "action": "reply", "text": "The repair is scheduled.",
            "to": ["tenant"], "request_id": "case-reply-100"
        }
        self.handler.handle_case_action(request)
        self.assertEqual(self.responses[-1][1], 200)
        count = len(self.stage["cases"][0]["thread"])
        self.handler.handle_case_action(request)
        self.assertEqual(self.responses[-1][1], 200)
        self.assertTrue(self.responses[-1][0]["already_processed"])
        self.assertEqual(len(self.stage["cases"][0]["thread"]), count)
        self.handler.handle_case_action({**request, "text": "A changed message"})
        self.assertEqual(self.responses[-1][1], 409)
        self.assertEqual(len(self.stage["cases"][0]["thread"]), count)

    def test_unrelated_tenant_cannot_replay_case_action_to_read_it(self):
        self.handler.user = {
            "role": "agent", "username": "office", "display_name": "Office manager"
        }
        request = {
            "id": 10, "action": "reply", "text": "Private repair message",
            "request_id": "case-reply-101"
        }
        self.handler.handle_case_action(request)
        self.assertEqual(self.responses[-1][1], 200)
        self.handler.user = {
            "role": "tenant", "username": "stranger",
            "account_id": "unlinked-account", "display_name": "Stranger"
        }
        self.handler.handle_case_action(request)
        self.assertEqual(self.responses[-1][1], 403)


if __name__ == "__main__":
    unittest.main()
