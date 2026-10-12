"""Public acquisition leads and newsletter consent; synthetic records only."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


class PublicAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.stage={"cases":[],"registrations":[],"newsletter_subscriptions":[],
                    "next_case_id":41,"properties":[],"audit_log":[]}
        self.h=serve.H.__new__(serve.H)
        self.h.user={"role":"agent","username":"pilot-agent","display_name":"Agent"}
        self.sent=[]
        self.h._json=lambda body,status=200:self.sent.append((body,status))
        self.h.triage=lambda msg:{"category":"general","urgency":0}
        self.loader=patch.object(serve,"load_stage",return_value=self.stage)
        self.saver=patch.object(serve,"save_stage")
        self.loader.start()
        self.saver.start()
        self.addCleanup(self.loader.stop)
        self.addCleanup(self.saver.stop)

    def intake(self,kind,**args):
        return self.h.handle_prospect_intake({
            "kind":kind,"name":"Pilot Person","email":"PILOT@EXAMPLE.TEST",
            "area":"Leeds","message":"Please contact me","consent":True,**args
        })

    def test_tenant_goes_to_existing_case_pipeline_with_next_action(self):
        self.intake("tenant",bedrooms="2",max_rent="1200")
        body,status=self.sent[-1]
        self.assertEqual(status,200)
        self.assertEqual(body["reference"],"case-41")
        case=self.stage["cases"][0]
        self.assertEqual(case["role"],"renter")
        self.assertEqual(case["type"],"enquiry")
        self.assertEqual(case["prospect_stage"],"enquiry")
        self.assertEqual(case["next_actor"],"agent")
        self.assertEqual(case["requirements"]["bedrooms"],"2")
        self.assertEqual(case["email"],"pilot@example.test")
        self.assertIsNotNone(case["contact_consent_at"])

    def test_landlord_enters_existing_unapproved_registration_pipeline(self):
        self.intake("landlord",service="management")
        self.assertEqual(self.sent[-1][1],200)
        lead=self.stage["registrations"][0]
        self.assertEqual(lead["status"],"pending")
        self.assertEqual(lead["prospect_stage"],"lead")
        self.assertEqual(lead["requirements"]["service"],"management")
        self.assertNotIn("account_id",lead)
        self.assertNotIn("party_id",lead)

    def test_trade_needs_review_not_auto_approved(self):
        self.intake("trades",trade="electrical")
        lead=self.stage["registrations"][0]
        self.assertEqual(lead["status"],"pending")
        self.assertEqual(lead["prospect_stage"],"applicant")
        self.assertEqual(lead["trades"],["electrical"])
        self.assertTrue(lead["verification_required"])
        self.assertNotIn("credentials_checked_at",lead)

    def test_intake_rejects_malformed_or_nonconsenting_submissions(self):
        for data in (
            {"kind":"tenant","name":"A","email":"ok@example.com","consent":True},
            {"kind":"tenant","name":"Alice","email":"invalid","consent":True},
            {"kind":"unapproved","name":"Alice","email":"ok@example.com","consent":True},
            {"kind":"tenant","name":"Alice","email":"ok@example.com","consent":False},
        ):
            self.h.handle_prospect_intake(data)
            self.assertEqual(self.sent[-1][1],400)
        self.assertEqual(self.stage["cases"],[])
        self.assertEqual(self.stage["registrations"],[])

    def test_newsletter_consent_is_separate_and_pending(self):
        payload={"name":"Alice Smith","email":"Alice@example.test",
                 "audience":"landlord","marketing_consent":True}
        self.h.handle_newsletter_signup(payload)
        self.assertEqual(self.sent[-1][1],200)
        sub=self.stage["newsletter_subscriptions"][0]
        self.assertEqual(sub["status"],"pending_confirmation")
        self.assertEqual(sub["email"],"alice@example.test")
        self.assertEqual(sub["consent_text_version"],"newsletter-v1")
        self.assertIsNone(sub["confirmed_at"])
        self.h.handle_newsletter_signup(dict(payload))
        self.assertEqual(len(self.stage["newsletter_subscriptions"]),1)

    def test_newsletter_categories_and_missing_consent_rejected(self):
        for audience in ("prospective_tenant","tenant","landlord","trades"):
            self.h.handle_newsletter_signup({"name":"Test Person","email":"test@example.test",
                "audience":audience,"marketing_consent":True})
            self.assertEqual(self.sent[-1][1],200)
        self.assertEqual(len(self.stage["newsletter_subscriptions"]),4)
        self.h.handle_newsletter_signup({"name":"Test Person","email":"test@example.test",
            "audience":"unknown","marketing_consent":True})
        self.assertEqual(self.sent[-1][1],400)
        self.h.handle_newsletter_signup({"name":"Test Person","email":"test@example.test",
            "audience":"tenant","marketing_consent":False})
        self.assertEqual(self.sent[-1][1],400)

    def test_agent_can_suppress_newsletter_and_reoptin_requires_confirmation(self):
        self.h.handle_newsletter_signup({"name":"Test Person","email":"test@example.test",
            "audience":"tenant","marketing_consent":True})
        ref=self.stage["newsletter_subscriptions"][0]["id"]
        self.h.handle_newsletter_action({"action":"unsubscribe","id":ref})
        self.assertEqual(self.sent[-1][1],200)
        self.assertEqual(self.stage["newsletter_subscriptions"][0]["status"],"unsubscribed")
        self.h.handle_newsletter_signup({"name":"Test Person","email":"test@example.test",
            "audience":"tenant","marketing_consent":True})
        self.assertEqual(self.stage["newsletter_subscriptions"][0]["status"],"pending_confirmation")
        self.assertEqual(len(self.stage["newsletter_subscriptions"]),1)

    def test_non_agent_cannot_read_newsletter_contact_list(self):
        self.h.path="/api/newsletter-subscriptions"
        self.h.session_user=lambda:{"role":"tenant","username":"tenant"}
        self.h._do_GET_with_agency_boundary()
        self.assertEqual(self.sent[-1][1],403)

    def test_unauthenticated_cannot_read_newsletter_contact_list(self):
        self.h.path="/api/newsletter-subscriptions"
        self.h.session_user=lambda:None
        self.h._do_GET_with_agency_boundary()
        self.assertEqual(self.sent[-1][1],401)

    def test_newsletter_contacts_not_exposed_via_tenant_scoped_stage(self):
        self.h.handle_newsletter_signup({"name":"Test Person","email":"personal@example.test",
            "audience":"landlord","marketing_consent":True})
        self.h.session_user=lambda:{"role":"tenant","display_name":"Tenant",
                                    "account_id":"tenant-account"}
        self.h.serve_scoped_stage()
        data,status=self.sent[-1]
        self.assertEqual(status,200)
        self.assertNotIn("newsletter_subscriptions",data)
        self.assertNotIn("personal@example.test",str(data))

    def test_cannot_manually_mark_unverified_subscriber_confirmed(self):
        self.h.handle_newsletter_action({"action":"confirm","id":"guess"})
        self.assertEqual(self.sent[-1][1],400)


if __name__=="__main__":
    unittest.main()
