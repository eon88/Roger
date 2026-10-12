"""Safe marketing footer and letting-agency demo request regression tests."""
import sys
import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


class HomePageImprovementsTests(unittest.TestCase):
    def setUp(self):
        self.stage = {"cases": [], "registrations": [], "agency_demo_requests": [],
                      "properties": [], "next_case_id": 25, "audit_log": []}
        self.h = serve.H.__new__(serve.H)
        self.h.user = None
        self.responses = []
        self.h._json = lambda obj, status=200: self.responses.append((obj, status))
        self.stage_patch = patch.object(serve, "load_stage", return_value=self.stage)
        self.save_patch = patch.object(serve, "save_stage")
        self.stage_patch.start()
        self.save_patch.start()
        self.addCleanup(self.stage_patch.stop)
        self.addCleanup(self.save_patch.stop)

    def test_valid_agent_demo_does_not_create_tenant_or_trades(self):
        self.h.handle_agent_demo({"name": "Agent Tester", "email": "AGENT@example.test",
                                  "company": "Test Agency", "area": "York",
                                  "message": "Demo of property management", "consent": True})
        self.assertEqual(self.responses[-1][1], 200)
        self.assertEqual(len(self.stage["agency_demo_requests"]), 1)
        lead = self.stage["agency_demo_requests"][0]
        self.assertEqual(lead["source"], "for-agents")
        self.assertEqual(lead["email"], "agent@example.test")
        self.assertEqual(lead["status"], "new")
        self.assertTrue(lead["contact_consent_at"])
        self.assertEqual(self.stage["cases"], [])
        self.assertEqual(self.stage["registrations"], [])

    def test_agent_demo_requires_valid_data_and_consent(self):
        for data in [
            {"name": "A", "email": "agent@example.test", "company": "Company", "consent": True},
            {"name": "Agent", "email": "not-an-email", "company": "Company", "consent": True},
            {"name": "Agent", "email": "agent@example.test", "company": "A", "consent": True},
            {"name": "Agent", "email": "agent@example.test", "company": "Company", "consent": False},
        ]:
            self.h.handle_agent_demo(data)
            self.assertEqual(self.responses[-1][1], 400)
        self.assertEqual(self.stage["agency_demo_requests"], [])

    def test_footer_public_config_is_explicit_and_allowlisted(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "public-site.json"
            config.write_text(json.dumps({"contact_email": "let@example.test",
                 "contact_phone": "+44 1234 567890",
                 "areas_served": ["York", "Surrey"],
                 "privacy_url": "https://roger.example.test/privacy",
                 "secret_admin_token": "never-public"}))
            with patch.object(serve, "ROOT", directory):
                result = self.h.public_site_info()
        self.assertEqual(result["contact_email"], "let@example.test")
        self.assertEqual(result["areas_served"], ["York", "Surrey"])
        self.assertEqual(result["privacy_url"], "https://roger.example.test/privacy")
        self.assertNotIn("secret_admin_token", result)

    def test_footer_rejects_unsafe_links_and_invalid_values(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "public-site.json"
            config.write_text(json.dumps({"contact_email": "bad mail",
                "contact_phone": "hello",
                "areas_served": [42, "", "Leeds"],
                "privacy_url": "javascript:alert(1)"}))
            with patch.object(serve, "ROOT", directory):
                result = self.h.public_site_info()
        self.assertEqual(result["contact_email"], None)
        self.assertEqual(result["contact_phone"], None)
        self.assertEqual(result["areas_served"], ["Leeds"])
        self.assertEqual(result["privacy_url"], None)

    def test_demo_lead_is_agency_tagged_when_stage_is_tagged(self):
        self.stage["agency_id"] = "one-agency"
        self.h.handle_agent_demo({"name": "Agent Tester", "email": "agent@example.test",
                                  "company": "Test Agency", "consent": True})
        self.assertEqual(self.stage["agency_demo_requests"][0]["agency_id"], "one-agency")


if __name__ == "__main__":
    unittest.main()
