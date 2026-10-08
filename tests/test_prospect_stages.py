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
        self.handler.find_prop = lambda data, pid: next((p for p in data.get("properties", []) if p.get("id") == pid), None)
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

    def test_property_can_be_advertised_after_description_is_added(self):
        prop = {
            "id": "home-1", "title": "12 Example Road", "area": "Exampleton",
            "beds": 2, "rent": 125000, "lifecycle_status": "ready_to_market",
            "landlord": "Private owner", "tenant": None,
        }
        self.stage["properties"] = [prop]
        serve.H.handle_property_action(self.handler, {
            "property_id": "home-1", "status": "advertised",
            "description": "A two-bedroom home near the station.",
        })
        self.assertEqual(prop["lifecycle_status"], "advertised")
        self.assertEqual(prop["public_listing"]["description"], "A two-bedroom home near the station.")
        self.assertEqual(self.stage["audit_log"][-1]["action"], "property_lifecycle_changed")
        self.saved.assert_called_once_with(self.stage)
        self.assertEqual(self.responses[-1][1], 200)

    def test_invalid_property_transition_is_rejected(self):
        self.stage["properties"] = [{
            "id": "home-1", "lifecycle_status": "occupied",
            "title": "12 Example Road", "area": "Exampleton", "beds": 2, "rent": 125000,
        }]
        serve.H.handle_property_action(self.handler, {
            "property_id": "home-1", "status": "advertised",
            "description": "A home.",
        })
        self.assertEqual(self.responses[-1][1], 409)
        self.saved.assert_not_called()

    def test_public_api_returns_only_advertised_safe_fields(self):
        self.stage["properties"] = [
            {"id": "live", "title": "12 Example Road", "area": "Exampleton",
             "beds": 2, "rent": 125000, "landlord": "Private owner", "tenant": "Private tenant",
             "lifecycle_status": "advertised",
             "public_listing": {"description": "Public copy."}},
            {"id": "draft", "title": "Private draft", "area": "Exampleton",
             "beds": 1, "rent": 90000, "lifecycle_status": "onboarding",
             "public_listing": {"description": "Do not publish."}},
        ]
        response = serve.H.serve_public_listings(self.handler)
        self.assertEqual([p["id"] for p in response["properties"]], ["live"])
        self.assertNotIn("landlord", response["properties"][0])
        self.assertNotIn("tenant", response["properties"][0])
        self.assertFalse(response["demo"])

    def test_trade_cannot_enter_approved_stage_before_registration_approval(self):
        serve.H.handle_prospect_action(self.handler, {
            "kind": "trades", "id": "reg-1", "stage": "approved",
        })
        self.assertEqual(self.responses[-1][1], 409)
        self.assertNotIn("prospect_stage", self.stage["registrations"][0])
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
