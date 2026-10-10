"""Regression tests for case-level account and Party authorisation."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "stage-clone")
)
import serve


class CasePermissionTests(unittest.TestCase):
    def setUp(self):
        self.stage = {
            "parties": [
                {
                    "id": "p-" + name,
                    "account_id": "a-" + name,
                    "roles": [role],
                    "status": "active",
                }
                for name, role in [
                    ("tenant1", "tenant"),
                    ("tenant2", "tenant"),
                    ("landlord1", "landlord"),
                    ("landlord2", "landlord"),
                    ("trade1", "trades"),
                    ("trade2", "trades"),
                ]
            ],
            "properties": [
                {
                    "id": "flat-a",
                    "tenant_party_id": "p-tenant1",
                    "landlord_party_id": "p-landlord1",
                },
                {
                    "id": "flat-b",
                    "tenant_party_id": "p-tenant2",
                    "landlord_party_id": "p-landlord2",
                },
            ],
            "cases": [
                {
                    "id": 101,
                    "property_id": "flat-a",
                    "tenant_party_id": "p-tenant1",
                    "name": "Alex Example",
                    "status": "resolved",
                    "thread": [],
                },
                {
                    "id": 102,
                    "property_id": "flat-b",
                    "tenant_party_id": "p-tenant2",
                    "name": "Alex Example",
                    "status": "resolved",
                    "thread": [],
                },
            ],
            "jobs": [
                {
                    "id": "job-a",
                    "case_id": 101,
                    "assigned_to": "Repair Example",
                    "assigned_to_party_id": "p-trade1",
                },
                {
                    "id": "job-b",
                    "case_id": 102,
                    "assigned_to": "Repair Example",
                    "assigned_to_party_id": "p-trade2",
                },
            ],
            "audit_log": [],
        }

        self.users = {
            "tenant1": self.user("tenant", "tenant1", "Alex Example"),
            "tenant2": self.user("tenant", "tenant2", "Alex Example"),
            "landlord1": self.user("landlord", "landlord1", "Owner Example"),
            "landlord2": self.user("landlord", "landlord2", "Owner Example"),
            "trade1": self.user("trades", "trade1", "Repair Example"),
            "trade2": self.user("trades", "trade2", "Repair Example"),
            "agent": {
                "role": "agent",
                "username": "agent",
                "display_name": "Test Agent",
                "account_id": "a-agent",
            },
        }

        self.handler = serve.H.__new__(serve.H)
        self.handler.user = self.users["tenant1"]
        self.responses = []
        self.handler._json = lambda data, code=200: (
            self.responses.append((data, code))
        )

        load_patch = patch.object(
            serve, "load_stage", return_value=self.stage
        )
        save_patch = patch.object(serve, "save_stage")
        load_patch.start()
        self.saved = save_patch.start()
        self.addCleanup(load_patch.stop)
        self.addCleanup(save_patch.stop)

    @staticmethod
    def user(role, name, display):
        return {
            "role": role,
            "username": name,
            "display_name": display,
            "account_id": "a-" + name,
        }

    def act(self, username, case_id, action="reply", **extra):
        self.handler.user = self.users[username].copy()
        data = {
            "id": case_id,
            "action": action,
            "text": "Test response",
            "to": ["agent"],
            **extra,
        }
        self.handler.handle_case_action(data)
        return self.responses[-1][1]

    def assert_denied_unchanged(self, username, case_id,
                                action="reply", expected=403, **extra):
        before = copy.deepcopy(self.stage)
        status = self.act(username, case_id, action, **extra)
        self.assertEqual(status, expected)
        self.assertEqual(self.stage, before)
        self.saved.assert_not_called()

    def test_tenant_can_reply_to_own_case(self):
        self.assertEqual(self.act("tenant1", 101), 200)
        thread = self.stage["cases"][0]["thread"]
        self.assertEqual(len(thread), 1)
        self.assertEqual(
            thread[0]["author_account_id"], "a-tenant1"
        )
        self.saved.assert_called_once()

    def test_same_name_tenant_cannot_reply_to_other_case(self):
        self.assert_denied_unchanged("tenant2", 101)

    def test_tenant_can_confirm_own_resolved_case(self):
        self.assertEqual(
            self.act("tenant1", 101, "confirm_resolution"), 200
        )
        self.assertEqual(
            self.stage["cases"][0]["status"], "closed"
        )

    def test_tenant_cannot_confirm_other_tenants_case(self):
        self.assert_denied_unchanged(
            "tenant2", 101, "confirm_resolution"
        )

    def test_tenant_cannot_reopen_other_tenants_case(self):
        self.assert_denied_unchanged(
            "tenant2", 101, "reopen_unresolved"
        )

    def test_landlord_can_reply_to_own_property_case(self):
        self.assertEqual(self.act("landlord1", 101), 200)
        self.saved.assert_called_once()

    def test_same_name_landlord_cannot_reply_to_other_case(self):
        self.assert_denied_unchanged("landlord2", 101)

    def test_landlord_cannot_confirm_tenant_resolution(self):
        self.assert_denied_unchanged(
            "landlord1", 101, "confirm_resolution"
        )

    def test_assigned_trade_can_reply(self):
        self.assertEqual(self.act("trade1", 101), 200)
        self.saved.assert_called_once()

    def test_same_name_trade_cannot_reply_to_other_job(self):
        self.assert_denied_unchanged("trade2", 101)

    def test_trade_without_party_assignment_is_denied(self):
        del self.stage["jobs"][0]["assigned_to_party_id"]
        self.assert_denied_unchanged("trade1", 101)

    def test_tenant_cannot_close_case_as_agent(self):
        self.assert_denied_unchanged(
            "tenant1", 101, "close", reason="Unauthorized"
        )

    def test_case_without_identity_link_is_denied(self):
        del self.stage["cases"][0]["tenant_party_id"]
        self.assert_denied_unchanged("tenant1", 101)

    def test_property_and_case_identity_must_both_match(self):
        self.stage["cases"][0]["tenant_party_id"] = "p-tenant2"
        self.assert_denied_unchanged("tenant1", 101)

    def test_unknown_action_is_rejected_without_changes(self):
        self.assert_denied_unchanged(
            "tenant1", 101, "arbitrary_action", expected=400
        )

    def test_invalid_message_audience_is_rejected(self):
        self.assert_denied_unchanged(
            "tenant1", 101, "reply",
            expected=400, to="landlord"
        )

    def test_agent_can_close_case(self):
        self.assertEqual(
            self.act("agent", 101, "close",
                     reason="Repair verified"), 200
        )
        self.assertEqual(
            self.stage["cases"][0]["status"], "closed"
        )
        self.saved.assert_called_once()


if __name__ == "__main__":
    unittest.main()
