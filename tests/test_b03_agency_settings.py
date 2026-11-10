"""B03 agency settings, plan boundary and isolated provisioning tests."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "stage-clone"))
sys.path.insert(0, str(ROOT / "ops" / "saas"))
import agency_admin
import provision_agency
import serve


class ProfileRulesTests(unittest.TestCase):
    def setUp(self):
        self.profile = agency_admin.initial_profile(
            "oaklettings", "Oak Lettings", "oaklettings.agents.example.test")

    def test_initial_profile_does_not_claim_real_office_or_payment(self):
        p = self.profile
        self.assertEqual(p["agency_id"], "oaklettings")
        self.assertEqual(p["operational_status"], "prepared")
        self.assertEqual(p["subscription_status"], "manual-trial-not-active")
        self.assertEqual(p["property_limit"], 0)
        self.assertEqual(p["branches"], [])
        self.assertFalse(p["office_email"])
        self.assertNotIn("password", json.dumps(p).lower())
        self.assertNotIn("subscription_status", agency_admin.public_brand(p))

    def test_valid_update_versions_settings_and_branches(self):
        p = agency_admin.update_settings(self.profile, {
            "expected_version": 1, "display_name": "Oak Home Lettings",
            "office_email": "office@oak.test", "office_phone": "0121 123 4567",
            "brand_colour": "#227744",
            "branches": [{"id": "north", "name": "North Branch",
                          "address": "2 High Street", "phone": "0121 123 4567",
                          "email": "north@oak.test"}],
        })
        self.assertEqual(p["version"], 2)
        self.assertEqual(p["branches"][0]["id"], "north")
        self.assertEqual(self.profile["branches"], [])
        self.assertEqual(p["plan"], "unassigned")
        self.assertEqual(p["operational_status"], "prepared")
        self.assertEqual(agency_admin.public_brand(p)["name"], "Oak Home Lettings")

    def test_stale_and_privilege_escalation_denied(self):
        for changes in (
            {"expected_version": 0, "display_name": "New Display"},
            {"expected_version": 1, "subscription_status": "paid"},
            {"expected_version": 1, "operational_status": "active"},
            {"expected_version": 1, "property_limit": 100000},
            {"expected_version": 1, "agency_id": "birchlettings"},
            {"expected_version": 1, "hostname": "foreign.example"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                agency_admin.update_settings(self.profile, changes)

    def test_email_phone_and_branch_validation_deny_bad_data(self):
        updates = [
            {"office_email": "bad;email"},
            {"office_phone": "abc"},
            {"brand_colour": "expression(alert(1))"},
            {"display_name": "\u0001unsafe"},
            {"branches": [{"id": "north", "name": "North", "address": "",
                            "phone": "", "email": ""},
                          {"id": "north", "name": "Copy", "address": "",
                            "phone": "", "email": ""}]},
            {"branches": [{"id": "../other", "name": "Branch", "address": "",
                            "phone": "", "email": ""}]},
        ]
        for changed in updates:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                agency_admin.update_settings(self.profile, {
                    "expected_version": 1, **changed,
                })

    def test_operator_plan_and_explicit_status_transitions_never_delete_data(self):
        set_plan, event = agency_admin.operator_transition(
            self.profile, "set_plan", reason="Verified manual pilot agreement",
            plan="pilot", property_limit=15, staff_limit=3)
        self.assertEqual(set_plan["property_limit"], 15)
        self.assertEqual(event["action"], "set_plan")
        active, _ = agency_admin.operator_transition(
            set_plan, "activate", reason="Operator approved test onboarding")
        self.assertEqual(active["operational_status"], "active")
        self.assertEqual(active["subscription_status"], "manual-trial")
        suspended, _ = agency_admin.operator_transition(
            active, "suspend", reason="Verified agency access suspension")
        self.assertEqual(suspended["operational_status"], "suspended")
        with self.assertRaises(ValueError):
            agency_admin.operator_transition(suspended, "record_invoice",
                                             reason="Cannot bill suspended customer",
                                             evidence="invoice-00001234")
        active, _ = agency_admin.operator_transition(
            suspended, "reactivate", reason="Agency access review completed")
        recorded, _ = agency_admin.operator_transition(
            active, "record_invoice", reason="Manual invoice recorded and checked",
            evidence="invoice-00001234")
        self.assertEqual(recorded["last_invoice_reference"], "invoice-00001234")
        cancelled, _ = agency_admin.operator_transition(
            recorded, "cancel", reason="Verified lawful cancellation completed")
        self.assertEqual(cancelled["operational_status"], "cancelled")
        with self.assertRaises(ValueError):
            agency_admin.operator_transition(cancelled, "activate",
                                             reason="No automatic resurrection allowed")
        self.assertEqual(self.profile["operational_status"], "prepared")

    def test_operator_rejects_unverified_billing_limits_and_unsafe_events(self):
        for action, extras in (
            ("record_invoice", {"evidence": "none"}),
            ("set_plan", {"plan": "enterprise", "property_limit": 1, "staff_limit": 1}),
            ("set_plan", {"plan": "pilot", "property_limit": -1, "staff_limit": 1}),
            ("set_plan", {"plan": "pilot", "property_limit": 1, "staff_limit": True}),
            ("suspend", {}),
        ):
            with self.subTest(action=action), self.assertRaises(ValueError):
                agency_admin.operator_transition(
                    self.profile, action, reason="Operator reason documented", **extras)


class ProvisionProfileTests(unittest.TestCase):
    def test_each_generated_agency_has_local_only_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            for slug, port in (("oaklettings", 29101), ("birchlettings", 29102)):
                base = Path(tmp) / slug
                provision_agency.provision(
                    slug, "Oak Lettings" if slug.startswith("oak") else "Birch Lettings",
                    "admin@example.test", port, "roger-saas:1234567890ab",
                    "agents.example.test", base)
                sql = (base / "bootstrap.sql").read_text()
                self.assertIn('"agency_profile"', sql)
                self.assertIn('"agency_id":"' + slug + '"', sql)
                self.assertNotIn("manual-paid", sql)
                manifest = json.loads((base / "agency.json").read_text())
                self.assertEqual(manifest["status"], "prepared-not-deployed")
            self.assertNotEqual(
                (Path(tmp) / "oaklettings" / "bootstrap.sql").read_text(),
                (Path(tmp) / "birchlettings" / "bootstrap.sql").read_text())


class ProfileHandlerTests(unittest.TestCase):
    def setUp(self):
        self.profile = agency_admin.initial_profile(
            "oaklettings", "Oak Lettings", "oaklettings.agents.example.test")
        self.stage = {"agency_id": "oaklettings", "agency_profile": self.profile, "audit_log": []}
        self.h = serve.H.__new__(serve.H)
        self.h.user = {"role": "agent", "username": "agency-admin"}
        self.results = []
        self.h._json = lambda payload, status=200: self.results.append((status, payload))
        self.h.audit = lambda stage, event: stage["audit_log"].append(event)
        self.env = patch.dict("os.environ", {"ROGER_SAAS_MODE": "1",
                            "ROGER_STORAGE_BACKEND": "postgres",
                            "ROGER_AGENCY_ID": "oaklettings"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.mocks = []
        for target, replacement in (
                ("load_stage", patch.object(serve, "load_stage", return_value=self.stage)),
                ("save_stage", patch.object(serve, "save_stage"))):
            m = replacement.start()
            self.mocks.append(m)
            self.addCleanup(replacement.stop)

    def invoke(self, data, identity=True):
        with patch.object(serve.H, "staff_admin",
                          return_value=({"users": []}, self.h.user) if identity else (None, None)):
            self.h.handle_agency_profile(data)
        return self.results[-1]

    def test_admin_saves_and_audits_via_authenticated_endpoint(self):
        status, response = self.invoke({"expected_version": 1,
                                        "office_email": "office@oak.test"})
        self.assertEqual(status, 200, response)
        self.assertEqual(response["profile"]["version"], 2)
        self.assertEqual(self.stage["audit_log"][-1]["action"], "agency_profile_updated")
        self.mocks[1].assert_called_once()

    def test_denied_admin_password_or_privilege_change_is_non_mutating(self):
        original = copy.deepcopy(self.stage)
        self.assertEqual(self.invoke({"expected_version": 1,
                                      "display_name": "Bad"}, identity=False)[0], 403)
        self.assertEqual(self.invoke({"expected_version": 1,
                                      "subscription_status": "manual-invoice-recorded"})[0], 400)
        self.assertEqual(self.stage, original)
        self.mocks[1].assert_not_called()

    def test_wrong_agency_profile_fails_closed(self):
        self.stage["agency_profile"]["agency_id"] = "birchlettings"
        with patch.object(serve.H, "staff_admin", return_value=({}, self.h.user)):
            with self.assertRaises(serve.AgencyBoundaryError):
                self.h.handle_agency_profile({
                    "expected_version": 1, "display_name": "Intruder Agency",
                })


if __name__ == "__main__":
    unittest.main()
