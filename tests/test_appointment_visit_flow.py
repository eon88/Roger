"""Focused Task 01: appointed repair visits, role ownership, consent and delays.

Synthetic records only. The real server is not started and no production data is used.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


class RepairAppointmentTests(unittest.TestCase):
    def setUp(self):
        self.stage = {
            "parties": [
                {"id": "tenant-1", "account_id": "account-tenant", "roles": ["tenant"], "status": "active"},
                {"id": "tenant-2", "account_id": "account-stranger", "roles": ["tenant"], "status": "active"},
                {"id": "owner-1", "account_id": "account-owner", "roles": ["landlord"], "status": "active"},
                {"id": "trade-1", "account_id": "account-trade", "roles": ["trades"], "status": "active"},
                {"id": "trade-2", "account_id": "account-other-trade", "roles": ["trades"], "status": "active"},
            ],
            "properties": [
                {"id": "home-1", "tenant_party_id": "tenant-1", "landlord_party_id": "owner-1"},
                {"id": "home-2", "tenant_party_id": "tenant-2"},
            ],
            "cases": [
                {"id": 10, "property_id": "home-1", "thread": []},
                {"id": 11, "property_id": "home-2", "thread": []},
            ],
            "jobs": [
                {"id": "job-10", "case_id": 10, "property_id": "home-1",
                 "assigned_to_party_id": "trade-1", "status": "assigned",
                 "requires_prework_quote": True, "work_authorised_at": "2026-10-01T12:00:00Z"},
                {"id": "job-11", "case_id": 11, "property_id": "home-2",
                 "assigned_to_party_id": "trade-2", "status": "assigned",
                 "requires_prework_quote": True, "work_authorised_at": "2026-10-01T12:00:00Z"},
            ],
            "appointments": [], "audit_log": [],
        }
        self.users = {
            "agent": {"role": "agent", "account_id": "account-agent", "display_name": "Agent"},
            "tenant": {"role": "tenant", "account_id": "account-tenant", "display_name": "Resident"},
            "stranger": {"role": "tenant", "account_id": "account-stranger", "display_name": "Other resident"},
            "owner": {"role": "landlord", "account_id": "account-owner", "display_name": "Owner"},
            "trade": {"role": "trades", "account_id": "account-trade", "display_name": "Contractor"},
            "other_trade": {"role": "trades", "account_id": "account-other-trade", "display_name": "Other contractor"},
        }
        self.handler = serve.H.__new__(serve.H)
        self.responses = []
        self.handler._json = lambda payload, status=200: self.responses.append((payload, status))
        self.handler.post_msg = lambda *a, **kw: None
        self.handler.audit = lambda *a, **kw: None
        mock_load = patch.object(serve, "load_stage", return_value=self.stage)
        mock_save = patch.object(serve, "save_stage")
        mock_load.start()
        self.saved = mock_save.start()
        self.addCleanup(mock_load.stop)
        self.addCleanup(mock_save.stop)

    def act(self, who, method, expected=200, **payload):
        self.handler.user = self.users[who]
        getattr(self.handler, method)(payload)
        response, status = self.responses[-1]
        self.assertEqual(status, expected, f"{who} / {method} / {payload}: {response}")
        return response

    def propose(self, who="trade", **extra):
        payload = {
            "property_id": "home-1",
            "job_id": "job-10",
            "appointment_type": "contractor_visit",
            "start_time": "2099-05-20T09:00:00Z",
            "end_time": "2099-05-20T10:00:00Z",
            **extra,
        }
        return self.act(who, "handle_appointment", **payload)["appointment"]

    def test_trade_proposes_tenant_accepts_and_access_note_is_scoped(self):
        visit = self.propose()
        self.assertEqual(visit["status"], "proposed")
        self.assertEqual(set(visit["participant_party_ids"]), {"trade-1", "tenant-1"})
        self.assertEqual(self.stage["cases"][0]["appointment_ids"], [visit["id"]])
        self.assertEqual(self.stage["jobs"][0]["appointment_ids"], [visit["id"]])
        self.assertEqual(len(self.handler.scoped_appointments(self.users["tenant"])), 1)
        self.assertEqual(len(self.handler.scoped_appointments(self.users["trade"])), 1)
        self.assertEqual(self.handler.scoped_appointments(self.users["stranger"]), [])
        self.assertEqual(self.handler.scoped_appointments(self.users["other_trade"]), [])
        self.assertEqual(self.handler.scoped_appointments(self.users["owner"]), [])
        self.assertNotIn("access_preference", self.handler.scoped_appointments(self.users["trade"])[0])

        self.act("owner", "handle_appointment_action", expected=403, id=visit["id"], action="confirm")
        self.act("trade", "handle_appointment_action", expected=403, id=visit["id"], action="confirm")
        self.act("agent", "handle_appointment_action", expected=403, id=visit["id"], action="confirm")
        self.act("stranger", "handle_appointment_action", expected=403, id=visit["id"], action="confirm")
        self.act("tenant", "handle_appointment_action", id=visit["id"], action="confirm",
                 access_preference="I will be home; please ring bell", contact_consent=True)
        self.assertEqual(self.stage["appointments"][0]["status"], "confirmed")
        trade_view = self.handler.scoped_appointments(self.users["trade"])[0]
        self.assertEqual(trade_view["access_preference"], "I will be home; please ring bell")
        self.assertTrue(trade_view["contact_consent"])
        self.assertNotIn("access_preference", self.handler.scoped_appointments(self.users["owner"])[0]
                         if self.handler.scoped_appointments(self.users["owner"]) else {})
        self.act("tenant", "handle_appointment_action", expected=409, id=visit["id"], action="confirm")

    def test_rejection_reproposal_missed_access_and_parts_delay(self):
        aid = self.propose()["id"]
        self.act("tenant", "handle_appointment_action", id=aid, action="decline",
                 note="Working that morning")
        self.assertEqual(self.stage["appointments"][0]["status"], "change_requested")
        self.act("trade", "handle_appointment_action", expected=409, id=aid, action="no_access", note="No one answered")
        self.act("tenant", "handle_appointment_action", expected=403, id=aid, action="reschedule",
                 start_time="2099-05-21T09:00:00Z")
        self.act("trade", "handle_appointment_action", id=aid, action="reschedule",
                 start_time="2099-05-21T09:00:00Z", note="New visit offered")
        self.assertEqual(self.stage["appointments"][0]["status"], "proposed")
        self.assertEqual(self.stage["appointments"][0]["previous_start_time"], "2099-05-20T09:00:00Z")
        self.act("tenant", "handle_appointment_action", id=aid, action="confirm")
        self.assertEqual(self.stage["appointments"][0]["status"], "confirmed")
        self.act("trade", "handle_appointment_action", expected=400, id=aid, action="no_access")
        self.act("trade", "handle_appointment_action", id=aid, action="no_access",
                 note="No one at home")
        self.assertEqual(self.stage["appointments"][0]["status"], "no_access")
        self.assertNotEqual(self.stage["jobs"][0]["status"], "invoice_submitted")
        self.act("trade", "handle_appointment_action", id=aid, action="reschedule",
                 start_time="2099-05-22T09:00:00Z")
        self.act("tenant", "handle_appointment_action", id=aid, action="confirm",
                 access_preference="Use front door", contact_consent=False)
        self.assertNotIn("access_preference", self.handler.scoped_appointments(self.users["trade"])[0])
        self.act("trade", "handle_appointment_action", id=aid, action="parts_delay",
                 note="Replacement valve arriving tomorrow")
        self.assertEqual(self.stage["appointments"][0]["status"], "parts_delay")
        self.act("trade", "handle_appointment_action", id=aid, action="reschedule",
                 start_time="2099-05-23T09:00:00Z")
        self.act("tenant", "handle_appointment_action", id=aid, action="confirm")
        self.act("trade", "handle_appointment_action", id=aid, action="complete",
                 outcome="Visit completed; tenant must still confirm repair")
        self.assertEqual(self.stage["appointments"][0]["status"], "completed")
        self.assertEqual(self.stage["jobs"][0]["status"], "assigned")
        self.act("trade", "handle_appointment_action", expected=409, id=aid, action="reschedule",
                 start_time="2099-05-24T09:00:00Z")
        self.assertGreaterEqual(len(self.stage["appointments"][0]["history"]), 9)

    def test_bad_property_unapproved_job_wrong_party_or_time_never_creates_visit(self):
        self.act("other_trade", "handle_appointment", expected=403, property_id="home-1",
                 job_id="job-10", appointment_type="contractor_visit",
                 start_time="2099-05-20T09:00:00Z")
        self.act("trade", "handle_appointment", expected=409, property_id="home-2",
                 job_id="job-10", appointment_type="contractor_visit",
                 start_time="2099-05-20T09:00:00Z")
        self.stage["jobs"][0].pop("work_authorised_at")
        self.act("trade", "handle_appointment", expected=409, property_id="home-1",
                 job_id="job-10", appointment_type="contractor_visit",
                 start_time="2099-05-20T09:00:00Z")
        self.stage["jobs"][0]["work_authorised_at"] = "2026-10-01T12:00:00Z"
        self.act("agent", "handle_appointment", expected=403, property_id="home-1",
                 job_id="job-10", appointment_type="contractor_visit",
                 participant_party_ids=["tenant-2"], start_time="2099-05-20T09:00:00Z")
        self.act("agent", "handle_appointment", expected=409, property_id="home-1",
                 case_id=11, appointment_type="viewing", start_time="2099-05-20T09:00:00Z")
        self.act("agent", "handle_appointment", expected=400, property_id="home-1",
                 appointment_type="viewing", start_time="2099-05-20T09:00:00")
        self.act("agent", "handle_appointment", expected=400, property_id="home-1",
                 appointment_type="viewing", start_time="2099-05-20T10:00:00Z",
                 end_time="2099-05-20T09:00:00Z")
        self.assertEqual(self.stage["appointments"], [])

    def test_non_repair_viewing_tenant_can_confirm_and_agent_can_cancel(self):
        visit = self.act("agent", "handle_appointment", property_id="home-1",
                         appointment_type="viewing", start_time="2099-06-01T11:00:00Z")["appointment"]
        self.assertEqual(visit["participant_party_ids"], ["tenant-1"])
        self.act("tenant", "handle_appointment_action", id=visit["id"], action="confirm")
        self.act("tenant", "handle_appointment_action", expected=403, id=visit["id"], action="cancel")
        self.act("agent", "handle_appointment_action", id=visit["id"], action="cancel")
        self.assertEqual(self.stage["appointments"][0]["status"], "cancelled")
        self.act("tenant", "handle_appointment_action", expected=409, id=visit["id"], action="confirm")


if __name__ == "__main__":
    unittest.main()
