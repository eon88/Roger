"""Landlord approval and appointment authorisation tests."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "stage-clone")
)
import serve


class ApprovalAppointmentTests(unittest.TestCase):
    def setUp(self):
        people = [
            ("tenant1", "tenant", "Alex Example"),
            ("tenant2", "tenant", "Alex Example"),
            ("landlord1", "landlord", "Owner Example"),
            ("landlord2", "landlord", "Owner Example"),
            ("trade1", "trades", "Repair Example"),
            ("trade2", "trades", "Repair Example"),
        ]

        self.users = {
            name: {
                "username": name,
                "role": role,
                "display_name": display,
                "account_id": "account-" + name,
            }
            for name, role, display in people
        }
        self.users["agent"] = {
            "username": "agent",
            "role": "agent",
            "display_name": "Test Agent",
            "account_id": "account-agent",
        }

        self.stage = {
            "parties": [
                {
                    "id": "party-" + name,
                    "account_id": "account-" + name,
                    "roles": [role],
                    "status": "active",
                }
                for name, role, _ in people
            ],
            "properties": [{
                "id": "flat-a",
                "tenant": "Alex Example",
                "landlord": "Owner Example",
                "tenant_party_id": "party-tenant1",
                "landlord_party_id": "party-landlord1",
            }],
            "jobs": [{
                "id": "job-a",
                "case_id": 900,
                "property_id": "flat-a",
                "status": "awaiting_approval",
                "assigned_to": "Repair Example",
                "assigned_to_party_id": "party-trade1",
            }],
            "approvals": [{
                "id": "approval-a",
                "job_id": "job-a",
                "property_id": "flat-a",
                "landlord": "Owner Example",
                "landlord_party_id": "party-landlord1",
                "amount_pence": 20000,
                "reason": "Synthetic invoice",
                "status": "pending",
            }],
            "appointments": [{
                "id": "appointment-a",
                "property_id": "flat-a",
                "job_id": "job-a",
                "status": "proposed",
                "participant_roles": [
                    "tenant", "landlord", "trades"
                ],
                "participant_party_ids": [
                    "party-tenant1",
                    "party-landlord1",
                    "party-trade1",
                ],
                "start_time": "2026-11-01T10:00",
            }],
            "cases": [],
            "next_case_id": 9001,
            "audit_log": [],
        }

        self.handler = serve.H.__new__(serve.H)
        self.handler.audit = lambda *a, **kw: None
        self.handler.post_msg = lambda *a, **kw: None
        self.handler.sync_case = lambda *a, **kw: None
        self.responses = []
        self.handler._json = lambda data, code=200: (
            self.responses.append((data, code))
        )

        loader = patch.object(
            serve, "load_stage", return_value=self.stage
        )
        saver = patch.object(serve, "save_stage")
        loader.start()
        self.saved = saver.start()
        self.addCleanup(loader.stop)
        self.addCleanup(saver.stop)

    def act(self, username, endpoint, **payload):
        self.handler.user = self.users[username]
        getattr(self.handler, endpoint)(payload)
        return self.responses[-1][1]

    def denied(self, username, endpoint, expected=403, **payload):
        before = copy.deepcopy(self.stage)
        code = self.act(username, endpoint, **payload)
        self.assertEqual(code, expected)
        self.assertEqual(self.stage, before)
        self.saved.assert_not_called()

    def approval(self, username, action="approve", **extra):
        return self.act(
            username, "handle_landlord_action",
            id="approval-a", action=action, **extra
        )

    def appointment(self, username, action="confirm", **extra):
        return self.act(
            username, "handle_appointment_action",
            id="appointment-a", action=action, **extra
        )

    # --- The four previously successful attacks ---

    def test_wrong_landlord_cannot_approve_invoice(self):
        self.denied(
            "landlord2", "handle_landlord_action",
            id="approval-a", action="approve"
        )

    def test_wrong_tenant_cannot_confirm_appointment(self):
        self.denied(
            "tenant2", "handle_appointment_action",
            id="appointment-a", action="confirm"
        )

    def test_wrong_landlord_cannot_confirm_appointment(self):
        self.denied(
            "landlord2", "handle_appointment_action",
            id="appointment-a", action="confirm"
        )

    def test_wrong_contractor_cannot_confirm_appointment(self):
        self.denied(
            "trade2", "handle_appointment_action",
            id="appointment-a", action="confirm"
        )

    # --- Additional forbidden actions ---

    def test_wrong_landlord_cannot_reject_invoice(self):
        self.denied(
            "landlord2", "handle_landlord_action",
            id="approval-a", action="reject",
            reason="Unauthorised"
        )

    def test_tenant_cannot_approve_invoice(self):
        self.denied(
            "tenant1", "handle_landlord_action",
            id="approval-a", action="approve"
        )

    def test_approval_without_party_id_denied(self):
        del self.stage["approvals"][0]["landlord_party_id"]
        self.denied(
            "landlord1", "handle_landlord_action",
            id="approval-a", action="approve"
        )

    def test_mismatched_property_owner_denied(self):
        self.stage["properties"][0]["landlord_party_id"] = (
            "party-landlord2"
        )
        self.denied(
            "landlord1", "handle_landlord_action",
            id="approval-a", action="approve"
        )

    def test_missing_rejection_reason_does_not_mutate(self):
        self.denied(
            "landlord1", "handle_landlord_action",
            expected=400, id="approval-a",
            action="reject"
        )

    def test_appointment_without_participants_denied(self):
        self.stage["appointments"][0]["participant_party_ids"] = []
        self.denied(
            "tenant1", "handle_appointment_action",
            id="appointment-a", action="confirm"
        )

    def test_appointment_with_wrong_property_link_denied(self):
        self.stage["properties"][0]["tenant_party_id"] = (
            "party-tenant2"
        )
        self.denied(
            "tenant1", "handle_appointment_action",
            id="appointment-a", action="confirm"
        )

    def test_contractor_job_mismatch_denied(self):
        self.stage["jobs"][0]["assigned_to_party_id"] = (
            "party-trade2"
        )
        self.denied(
            "trade1", "handle_appointment_action",
            id="appointment-a", action="confirm"
        )

    def test_tenant_cannot_cancel_agency_appointment(self):
        self.denied(
            "tenant1", "handle_appointment_action",
            id="appointment-a", action="cancel"
        )

    # --- Legitimate actions ---

    def test_correct_landlord_can_approve(self):
        self.assertEqual(self.approval("landlord1"), 200)
        self.assertEqual(
            self.stage["approvals"][0]["status"], "approved"
        )
        self.saved.assert_called_once()

    def test_correct_landlord_can_reject_with_reason(self):
        self.assertEqual(
            self.approval(
                "landlord1", "reject",
                reason="Evidence missing"
            ), 200
        )
        self.assertEqual(
            self.stage["approvals"][0]["status"], "rejected"
        )

    def test_correct_tenant_can_confirm(self):
        self.assertEqual(self.appointment("tenant1"), 200)
        self.assertEqual(
            self.stage["appointments"][0]["status"], "confirmed"
        )

    def test_correct_landlord_can_decline(self):
        self.assertEqual(
            self.appointment("landlord1", "decline"), 200
        )
        self.assertEqual(
            self.stage["appointments"][0]["status"], "declined"
        )

    def test_correct_contractor_can_confirm(self):
        self.assertEqual(self.appointment("trade1"), 200)

    def test_agent_can_cancel_appointment(self):
        self.assertEqual(
            self.appointment("agent", "cancel"), 200
        )
        self.assertEqual(
            self.stage["appointments"][0]["status"], "cancelled"
        )

    def test_appointment_read_isolation(self):
        for username, expected in [
            ("tenant1", 1),
            ("tenant2", 0),
            ("landlord1", 1),
            ("landlord2", 0),
            ("trade1", 1),
            ("trade2", 0),
            ("agent", 1),
        ]:
            with self.subTest(username=username):
                visible = self.handler.scoped_appointments(
                    self.users[username]
                )
                self.assertEqual(len(visible), expected)


if __name__ == "__main__":
    unittest.main()
