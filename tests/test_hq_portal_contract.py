"""Static contract checks for the isolated Roger HQ portal preview."""
import pathlib
import unittest
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parents[1]

class ElementIds(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.add(values["id"])

class AgencyPortalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "stage-clone" / "hq-agency.html").read_text()
        parser = ElementIds()
        parser.feed(cls.html)
        cls.ids = parser.ids

    def test_all_role_forms_and_lists_exist(self):
        expected = {"loginForm","dashboard","properties","cases","jobs",
                    "approvals","appointments","documents","messages",
                    "caseForm","jobForm","approvalRequestForm","approvalForm","appointmentForm","messageForm"}
        self.assertTrue(expected.issubset(self.ids), expected-self.ids)

    def test_browser_uses_agency_endpoints_only(self):
        self.assertIn("/api/agency/whoami", self.html)
        self.assertIn("/api/agency/login", self.html)
        self.assertIn("/api/agency/workflows/", self.html)
        self.assertNotIn("/api/tenant/issue", self.html)
        self.assertNotIn("/api/job-action", self.html)

    def test_untrusted_records_are_rendered_as_text(self):
        self.assertIn("textContent=JSON.stringify(item,null,2)", self.html)
        self.assertNotIn("innerHTML", self.html)
