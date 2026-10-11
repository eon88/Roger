"""No fake office contacts or misleading emergency response promises in live portals."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "stage-clone"


class ContactSafetyTests(unittest.TestCase):
    def test_tenant_has_no_fake_office_contact_or_seeded_email(self):
        page = (ROOT / "tenant.html").read_text(encoding="utf-8")
        for fake in ("0121 496 0123", "office@stage.example", "daniel.mensah@example.com",
                     "Expect contact within 4 hours", "within one working day"):
            with self.subTest(fake=fake):
                self.assertNotIn(fake, page)
        self.assertIn("not monitored 24/7", page)
        self.assertIn("0800 111 999", page)

    def test_trades_and_landlord_have_no_fake_telephone_number(self):
        for name in ("trades.html", "landlord.html"):
            with self.subTest(page=name):
                self.assertNotIn("0121 496 0123", (ROOT / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
