"""B03 operator controls, suspended-tenant denial and plan-limit tests."""
import contextlib
import copy
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import agency_admin
import agency_operator
import serve


def args(action, **changes):
    fields = {"agency": "oaklettings", "action": action,
              "reviewed": True, "reason": "Verified operator review and approval",
              "export_reference": None, "invoice_reference": None,
              "plan": None, "property_limit": None, "staff_limit": None}
    fields.update(changes)
    return SimpleNamespace(**fields)


class OperatorSafetyTests(unittest.TestCase):
    def setUp(self):
        p = agency_admin.initial_profile("oaklettings", "Oak Lettings",
                                         "oaklettings.agents.example.test")
        p.update({"legal_name": "Oak Lettings Ltd", "office_email": "oak@example.test",
                  "office_phone": "0121 123 4567", "office_address": "1 High Street"})
        self.stage = {"agency_id": "oaklettings", "agency_profile": p,
                      "agency_events": [], "audit_log": []}
        self.users = {"users": [{"username": "agency-admin"}],
                      "sessions": {"live-staff": {"username": "agency-admin"}}}
        self.saved = []
        self.saved_users = []
        env = patch.dict("os.environ", {"ROGER_SAAS_MODE": "1",
                        "ROGER_STORAGE_BACKEND": "postgres",
                        "ROGER_AGENCY_ID": "oaklettings"})
        env.start();self.addCleanup(env.stop)
        mocks = [
            patch.object(serve, "storage_write_lock", return_value=contextlib.nullcontext()),
            patch.object(serve, "load_stage", side_effect=lambda: self.stage),
            patch.object(serve, "save_stage", side_effect=lambda x: self.saved.append(copy.deepcopy(x))),
            patch.object(serve, "load_users", return_value=self.users),
            patch.object(serve, "save_users", side_effect=lambda x: self.saved_users.append(copy.deepcopy(x))),
        ]
        for mock in mocks:
            mock.start()
            self.addCleanup(mock.stop)

    def test_operator_is_never_allowed_to_use_foreign_stack(self):
        for a in (args("activate", agency="birchlettings"),
                  args("activate", reviewed=False)):
            with self.assertRaises(ValueError):
                agency_operator.execute(a)
        self.assertEqual(self.saved, [])
        self.assertEqual(self.users["sessions"], {"live-staff": {"username": "agency-admin"}})

    def test_activation_requires_real_settings_and_operator_plan(self):
        with self.assertRaises(ValueError):
            agency_operator.execute(args("activate"))
        agency_operator.execute(args("set_plan", plan="pilot",
                                     property_limit=15, staff_limit=3))
        result = agency_operator.execute(args("activate"))
        self.assertEqual(result["status"], "active")
        self.assertEqual(result["subscription_status"], "manual-trial")

    def test_suspend_revokes_all_sessions_and_does_not_remove_data(self):
        agency_operator.execute(args("set_plan", plan="pilot",
                                     property_limit=10, staff_limit=3))
        agency_operator.execute(args("activate"))
        self.stage["properties"] = [{"id": "owned-home"}]
        result = agency_operator.execute(args("suspend"))
        self.assertEqual(result["status"], "suspended")
        self.assertEqual(self.users["sessions"], {})
        self.assertEqual(self.stage["properties"], [{"id": "owned-home"}])
        self.assertTrue(self.stage["agency_events"])
        self.assertEqual(self.saved_users[-1]["sessions"], {})

    def test_cancel_requires_export_retention_review_and_does_not_delete(self):
        with self.assertRaises(ValueError):
            agency_operator.execute(args("cancel"))
        result = agency_operator.execute(args(
            "cancel", export_reference="verified-backup-export-001"))
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(self.stage["agency_events"][-1]["export_retention_reference"],
                         "verified-backup-export-001")

    def test_no_automatic_invoice_or_charge(self):
        agency_operator.execute(args("set_plan", plan="pilot",
                                     property_limit=5, staff_limit=2))
        agency_operator.execute(args("activate"))
        with self.assertRaises(ValueError):
            agency_operator.execute(args("record_invoice", invoice_reference="x"))
        result = agency_operator.execute(args(
            "record_invoice", invoice_reference="manual-invoice-00123"))
        self.assertEqual(result["subscription_status"], "manual-invoice-recorded")
        self.assertIn("no payment", result["notice"])


class RuntimeLimitTests(unittest.TestCase):
    def setUp(self):
        self.stage = {
            "agency_id": "oaklettings", "audit_log": [], "invitations": [],
            "properties": [{"id": "home-1"}],
            "property_submissions": [{
                "id": "sub-1", "status": "pending", "landlord_party_id": "owner-1",
                "address": "2 High Street", "area": "Birmingham",
                "postcode": "B1 1AA", "beds": 2, "rent_pence": 180000,
            }],
            "parties": [{"id": "owner-1", "status": "active", "roles": ["landlord"],
                         "display_name": "Oak Owner"}],
            "agency_profile": {
                "agency_id": "oaklettings", "plan": "pilot", "property_limit": 1,
                "staff_limit": 1, "operational_status": "active",
            },
        }
        self.users = {"users": [{"username": "agency-admin", "role": "agent"}],
                      "sessions": {}}
        self.h = serve.H.__new__(serve.H)
        self.h.user = self.users["users"][0]
        self.answers = []
        self.h._json = lambda obj, status=200: self.answers.append((status,obj))
        self.h.audit = lambda stage, event: stage["audit_log"].append(event)
        env=patch.dict("os.environ",{"ROGER_SAAS_MODE":"1",
                       "ROGER_STORAGE_BACKEND":"postgres",
                       "ROGER_AGENCY_ID":"oaklettings"})
        env.start();self.addCleanup(env.stop)
        p=patch.object(serve,"load_stage",return_value=self.stage)
        p.start();self.addCleanup(p.stop)
        p=patch.object(serve,"save_stage")
        self.save=p.start();self.addCleanup(p.stop)

    def test_exceed_property_limit_rejects_approval_before_any_changes(self):
        before=copy.deepcopy(self.stage)
        self.h.handle_agent_property_submission({"submission_id":"sub-1",
                                                  "action":"approve","note":""})
        self.assertEqual(self.answers[-1][0],409)
        self.assertEqual(self.stage,before)
        self.save.assert_not_called()

    def test_exceed_staff_seats_rejects_invite_before_minting_token(self):
        with patch.object(serve.H,"staff_admin",
                          return_value=(self.users,self.h.user)):
            self.h.handle_staff_invitation({
                "current_password": "not stored",
                "email": "staff@example.test",
                "display_name": "New Staff",
            })
        self.assertEqual(self.answers[-1][0],409)
        self.assertEqual(self.stage["invitations"],[])
        self.save.assert_not_called()

    def test_suspended_agency_pauses_all_auth_and_public_traffic(self):
        self.assertFalse(self.h.agency_paused())
        self.stage["agency_profile"]["operational_status"] = "suspended"
        self.assertTrue(self.h.agency_paused())
        self.stage["agency_profile"]["operational_status"] = "cancelled"
        self.assertTrue(self.h.agency_paused())


if __name__ == "__main__":
    unittest.main()
