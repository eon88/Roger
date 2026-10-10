"""Portal UI must use server-authorised records."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "stage-clone"


class PortalPartyUITests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tenant = (ROOT / "tenant.html").read_text()
        cls.landlord = (ROOT / "landlord.html").read_text()

    def test_tenant_no_name_based_property_filter(self):
        self.assertNotIn("p.tenant===ME", self.tenant)

    def test_tenant_no_name_based_case_filter(self):
        self.assertNotIn("c.name===ME", self.tenant)

    def test_tenant_uses_authorised_property(self):
        self.assertEqual(
            self.tenant.count(
                "const prop=(stage.properties||[])[0];"
            ),
            2,
        )

    def test_tenant_uses_authorised_cases(self):
        self.assertIn(
            "const mine=(stage.cases||[]).slice().reverse();",
            self.tenant,
        )

    def test_landlord_no_name_based_property_filter(self):
        self.assertNotIn("p.landlord===ME", self.landlord)

    def test_landlord_no_name_based_approval_filter(self):
        self.assertNotIn("a.landlord===ME", self.landlord)

    def test_landlord_uses_authorised_properties(self):
        self.assertIn(
            "const props=stage.properties||[];",
            self.landlord,
        )

    def test_landlord_uses_authorised_approvals(self):
        self.assertIn(
            "const apps=stage.approvals||[];",
            self.landlord,
        )


if __name__ == "__main__":
    unittest.main()
