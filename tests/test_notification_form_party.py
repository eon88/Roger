"""Static regression checks for notification recipient UI."""
import unittest
from pathlib import Path

UI = (
    Path(__file__).resolve().parents[1]
    / "stage-clone" / "agent.html"
)

class NotificationFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = UI.read_text()

    def test_party_selector_exists(self):
        self.assertIn('id="note-party"', self.html)

    def test_old_name_input_removed(self):
        self.assertNotIn('id="note-name"', self.html)

    def test_role_changes_refresh_selector(self):
        self.assertIn(
            'onchange="refreshNotificationPartyOptions()"',
            self.html
        )

    def test_only_active_linked_parties_offered(self):
        self.assertIn("p.status==='active'", self.html)
        self.assertIn("!!p.account_id", self.html)
        self.assertIn("p.roles.includes(role)", self.html)

    def test_post_contains_party_id(self):
        self.assertIn(
            "recipient_party_id:partyId", self.html
        )

    def test_missing_recipient_blocked_in_ui(self):
        self.assertIn(
            "if(role!=='agent'&&!partyId)", self.html
        )

    def test_agent_role_needs_no_party(self):
        self.assertIn(
            "partyEl.disabled=true", self.html
        )

if __name__ == "__main__":
    unittest.main()
