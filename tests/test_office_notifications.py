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


class AccountRevocationTests(unittest.TestCase):
    def setUp(self):
        self.accounts={"users":[
            {"username":"real-tenant","role":"tenant","account_id":"acc-tenant"},
            {"username":"real-agent","role":"agent","account_id":"acc-agent"},
        ],"sessions":{
            "tenant-session":{"username":"real-tenant","exp":"2099-01-01T00:00:00+00:00"},
            "agent-session":{"username":"real-agent","exp":"2099-01-01T00:00:00+00:00"},
        }}
        self.stage={"parties":[
            {"id":"tenant-party","roles":["tenant"],"status":"active","account_id":"acc-tenant"},
            {"id":"landlord-other-role","roles":["landlord"],"status":"active","account_id":"acc-tenant"},
            {"id":"agent-party","roles":["agent"],"status":"active","account_id":"acc-agent"},
        ],"audit_log":[],"cases":[{"id":1,"tenant_party_id":"tenant-party","message":"Saved history"}]}
        self.h=serve.H.__new__(serve.H)
        self.h.user={"role":"agent","username":"real-agent","display_name":"Office"}
        self.out=[]
        self.h._json=lambda data,status=200:self.out.append((data,status))
        self.h.parse_cookies=lambda:{"stage_session":"tenant-session"}
        a=patch.object(serve,"load_stage",return_value=self.stage)
        b=patch.object(serve,"save_stage")
        c=patch.object(serve,"load_users",return_value=self.accounts)
        d=patch.object(serve,"save_users")
        a.start();b.start();c.start();d.start()
        self.addCleanup(a.stop);self.addCleanup(b.stop)
        self.addCleanup(c.stop);self.addCleanup(d.stop)

    def test_revocation_disables_all_account_roles_and_sessions_but_keeps_case_history(self):
        self.h.handle_access_revoke({"action":"revoke","party_id":"tenant-party","reason":"Account is compromised"})
        result,status=self.out[-1]
        self.assertEqual(status,200,result)
        self.assertEqual(result["sessions_closed"],1)
        self.assertEqual(result["revoked_party_ids"],["tenant-party","landlord-other-role"])
        self.assertEqual(self.stage["parties"][0]["status"],"revoked")
        self.assertEqual(self.stage["parties"][1]["status"],"revoked")
        self.assertNotIn("tenant-session",self.accounts["sessions"])
        self.assertIn("agent-session",self.accounts["sessions"])
        self.assertTrue(self.accounts["users"][0]["disabled_at"])
        self.assertIsNone(self.h.session_user())
        self.assertEqual(self.stage["cases"][0]["message"],"Saved history")
        self.assertEqual(self.stage["audit_log"][-1]["action"],"portal_account_revoked")

    def test_cannot_revoke_agent_or_repeat_or_act_as_tenant(self):
        self.h.handle_access_revoke({"action":"revoke","party_id":"agent-party","reason":"No"})
        self.assertEqual(self.out[-1][1],403)
        self.h.user={"role":"tenant","account_id":"acc-tenant"}
        self.h.handle_access_revoke({"action":"revoke","party_id":"tenant-party","reason":"No"})
        self.assertEqual(self.out[-1][1],403)
        self.h.user={"role":"agent","username":"real-agent"}
        self.h.handle_access_revoke({"action":"revoke","party_id":"tenant-party","reason":" "})
        self.assertEqual(self.out[-1][1],400)
        self.h.handle_access_revoke({"action":"revoke","party_id":"tenant-party","reason":"Compromised"})
        self.assertEqual(self.out[-1][1],200)
        self.h.handle_access_revoke({"action":"revoke","party_id":"tenant-party","reason":"repeat"})
        self.assertEqual(self.out[-1][1],409)


if __name__=="__main__":
    unittest.main()
