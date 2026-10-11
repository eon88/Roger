"""Task 05: real office policy and evidence-backed, retryable notification outbox.

Only a *manual* recorded email delivery: these tests never send actual email.
"""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


class OfficeAndNotificationTests(unittest.TestCase):
    def setUp(self):
        self.stage = {
            "office_settings": None, "notifications": [], "audit_log": [],
            "parties": [
                {"id":"tenant-1","account_id":"account-tenant","roles":["tenant"],
                 "status":"active","email":"tenant@example.test"},
                {"id":"tenant-2","account_id":"account-stranger","roles":["tenant"],
                 "status":"active","email":"stranger@example.test"},
                {"id":"owner-1","account_id":"account-owner","roles":["landlord"],
                 "status":"active","email":"owner@example.test"},
            ],
        }
        self.users = {
            "agent": {"username":"office","role":"agent","display_name":"Office"},
            "tenant": {"username":"tenant","role":"tenant","account_id":"account-tenant"},
            "stranger": {"username":"stranger","role":"tenant","account_id":"account-stranger"},
            "owner": {"username":"owner","role":"landlord","account_id":"account-owner"},
        }
        self.h = serve.H.__new__(serve.H)
        self.h._json = lambda result,status=200: self.answers.append((result,status))
        self.answers = []
        self.h.user=self.users["agent"]
        a=patch.object(serve,"load_stage",return_value=self.stage)
        b=patch.object(serve,"save_stage")
        a.start()
        self.saved=b.start()
        self.addCleanup(a.stop)
        self.addCleanup(b.stop)

    def do(self, who, method, status=200, **kwargs):
        self.h.user=self.users[who]
        getattr(self.h,method)(kwargs)
        result,code=self.answers[-1]
        self.assertEqual(code,status,f"{method}: {result}")
        return result

    def settings(self, action="publish", **overrides):
        return {
            "action":action, "office_name":"Real Offices", "phone":"020 1234 5678",
            "email":"office@example.test", "opening_hours":"Monday to Friday 9am-5pm",
            "out_of_hours_phone":"020 8765 4321",
            "out_of_hours_instructions":"For emergencies call the published emergency office number.",
            "emergency_policy":"Gas and imminent danger: leave property, contact emergency services; Roger is not continuously monitored.",
            "checked_real_contacts":True, "policy_reviewed":True,
            **overrides,
        }

    def notification(self, **overrides):
        return {
            "action":"create", "notification_type":"tenant_appointment",
            "recipient_role":"tenant", "recipient_party_id":"tenant-1",
            "channels":["email","in_app"], "email_to":"tenant@example.test",
            "title":"Confirmed repair visit", "message":"Visit appointment details",
            "request_id":"notify-visit-test-0001",
            **overrides,
        }

    def test_office_must_be_human_checked_before_publishing(self):
        self.assertFalse(self.h.safe_office_settings(self.stage,self.users["tenant"])["published"])
        self.do("tenant","handle_office_settings",403,**self.settings())
        self.do("agent","handle_office_settings",409,
                **self.settings(checked_real_contacts=False))
        self.do("agent","handle_office_settings",400,
                **self.settings(email="fictional email"))
        self.assertEqual(self.stage["office_settings"],None)
        self.do("agent","handle_office_settings",**self.settings(action="save_draft"))
        self.assertFalse(self.h.safe_office_settings(self.stage,self.users["tenant"])["published"])
        self.do("agent","handle_office_settings",**self.settings())
        out=self.h.safe_office_settings(self.stage,self.users["tenant"])
        self.assertTrue(out["published"])
        self.assertEqual(out["phone"],"020 1234 5678")
        self.assertNotIn("reviewed_by",out)
        self.assertEqual(self.h.safe_office_settings(self.stage,self.users["agent"])["reviewed_by"],"office")
        self.assertEqual(self.stage["office_settings"]["version"],2)
        self.do("agent","handle_office_settings",action="unpublish")
        self.assertFalse(self.h.safe_office_settings(self.stage,self.users["tenant"])["published"])
        self.assertTrue(any(x["action"]=="office_policy_unpublish" for x in self.stage["audit_log"]))

    def test_notification_requires_real_party_and_same_email(self):
        self.do("tenant","handle_notification_action",403,**self.notification())
        self.do("agent","handle_notification_action",409,
                **self.notification(email_to="unrelated@example.test"))
        self.do("agent","handle_notification_action",400,
                **self.notification(recipient_party_id="missing"))
        self.do("agent","handle_notification_action",409,
                **self.notification(recipient_role="agent",recipient_party_id=None,
                                    email_to="fake-office@example.test"))
        self.assertEqual(self.stage["notifications"],[])
        self.do("agent","handle_office_settings",**self.settings())
        self.do("agent","handle_notification_action",
                **self.notification(recipient_role="agent",recipient_party_id=None,
                                    email_to="office@example.test"))
        self.assertEqual(self.stage["notifications"][0]["recipient_role"],"agent")

    def test_email_queue_is_not_sent_and_request_replay_is_idempotent(self):
        self.do("agent","handle_notification_action",**self.notification())
        note=self.stage["notifications"][0]
        self.assertEqual(note["email_status"],"queued")
        self.assertEqual(note["email_attempts"],0)
        self.assertIsNone(note["email_delivery_evidence"])
        self.saved.reset_mock()
        same=self.do("agent","handle_notification_action",**self.notification())
        self.assertTrue(same["already_received"])
        self.assertEqual(len(self.stage["notifications"]),1)
        self.saved.assert_not_called()
        self.do("agent","handle_notification_action",409,
                **self.notification(message="different report"))
        self.assertEqual(len(self.stage["notifications"]),1)

    def test_sent_requires_outside_delivery_reference_and_is_one_way(self):
        self.do("agent","handle_notification_action",**self.notification())
        self.do("agent","handle_notification_action",400,id="note-1",action="sent")
        self.do("tenant","handle_notification_action",403,id="note-1",action="sent",
                delivery_reference="FAKE12345",delivery_source="manual")
        self.do("agent","handle_notification_action",id="note-1",action="sent",
                delivery_reference="SMTP-DELIVERY-001",delivery_source="external email log")
        note=self.stage["notifications"][0]
        self.assertEqual(note["email_status"],"sent")
        self.assertEqual(note["email_delivery_evidence"]["reference"],"SMTP-DELIVERY-001")
        self.do("agent","handle_notification_action",409,id="note-1",action="sent",
                delivery_reference="REPLAY-12345",delivery_source="email log")
        self.do("agent","handle_notification_action",409,id="note-1",action="failed",reason="bounced")

    def test_failed_retry_and_exhaustion_no_duplicate_messages(self):
        self.do("agent","handle_notification_action",**self.notification())
        self.do("agent","handle_notification_action",id="note-1",action="failed",reason="mail server down")
        note=self.stage["notifications"][0]
        self.assertEqual(note["email_status"],"failed")
        self.assertEqual(note["email_attempts"],1)
        self.assertTrue(note["email_next_retry_at"])
        self.do("agent","handle_notification_action",409,id="note-1",action="retry")
        note["email_next_retry_at"]=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        self.do("agent","handle_notification_action",id="note-1",action="retry")
        self.assertEqual(note["email_status"],"queued")
        self.do("agent","handle_notification_action",id="note-1",action="failed",reason="bounce")
        note["email_next_retry_at"]=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        self.do("agent","handle_notification_action",id="note-1",action="retry")
        self.do("agent","handle_notification_action",id="note-1",action="failed",reason="reject")
        self.assertEqual(note["email_attempts"],3)
        self.assertEqual(note["email_status"],"exhausted")
        self.assertIsNone(note["email_next_retry_at"])
        self.do("agent","handle_notification_action",409,id="note-1",action="retry")
        self.assertEqual(len(self.stage["notifications"]),1)

    def test_role_scoping_and_revoked_recipient(self):
        self.do("agent","handle_notification_action",**self.notification())
        self.assertEqual(len(self.h.scoped_notifications(self.users["tenant"])),1)
        self.assertEqual(self.h.scoped_notifications(self.users["stranger"]),[])
        self.assertEqual(self.h.scoped_notifications(self.users["owner"]),[])
        self.do("stranger","handle_notification_action",403,id="note-1",action="read")
        self.stage["parties"][0]["status"]="revoked"
        self.assertEqual(self.h.scoped_notifications(self.users["tenant"]),[])
        self.do("tenant","handle_notification_action",403,id="note-1",action="read")

    def test_in_app_only_notification_cannot_be_marked_email_sent(self):
        self.do("agent","handle_notification_action",
                **self.notification(channels=["in_app"],email_to=""))
        self.do("agent","handle_notification_action",409,id="note-1",action="sent",
                delivery_reference="SOMEREF-001",delivery_source="manual")
        self.assertIsNone(self.stage["notifications"][0]["email_status"])


if __name__=="__main__":
    unittest.main()
