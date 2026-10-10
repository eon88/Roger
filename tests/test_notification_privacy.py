"""Notification privacy regression tests."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "stage-clone")
)
import serve


class NotificationPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.users = {
            name: {
                "username": name,
                "account_id": "account-" + name,
                "display_name": "Alex Example",
                "role": "tenant",
            }
            for name in ("tenant1", "tenant2")
        }
        self.agent = {
            "username": "agent",
            "role": "agent",
            "display_name": "Agent",
            "account_id": "account-agent",
        }
        self.stage = {
            "parties": [
                {
                    "id": "party-tenant1",
                    "account_id": "account-tenant1",
                    "roles": ["tenant"],
                    "status": "active",
                },
                {
                    "id": "party-tenant2",
                    "account_id": "account-tenant2",
                    "roles": ["tenant"],
                    "status": "active",
                },
                {
                    "id": "party-trade1",
                    "account_id": "account-trade1",
                    "roles": ["trades"],
                    "status": "active",
                },
            ],
            "notifications": [
                {
                    "id": "note-private",
                    "recipient_role": "tenant",
                    "recipient_name": "Alex Example",
                    "recipient_party_id": "party-tenant1",
                    "title": "Private tenant notice",
                    "status": "unread",
                },
                {
                    "id": "note-legacy",
                    "recipient_role": "tenant",
                    "recipient_name": "Alex Example",
                    "title": "Legacy name-only notice",
                    "status": "unread",
                },
                {
                    "id": "note-role-only",
                    "recipient_role": "tenant",
                    "title": "Role-only notice",
                    "status": "unread",
                },
            ],
        }
        self.handler = serve.H.__new__(serve.H)
        self.responses = []
        self.handler.user = self.agent
        self.handler._json = lambda data, code=200: (
            self.responses.append((code, data))
        )
        self.handler.audit = lambda stage, entry: None

        loader = patch.object(
            serve, "load_stage", return_value=self.stage
        )
        saver = patch.object(serve, "save_stage")

        loader.start()
        self.save = saver.start()
        self.addCleanup(loader.stop)
        self.addCleanup(saver.stop)

    def visible(self, username):
        return {
            n["id"]
            for n in self.handler.scoped_notifications(
                self.users[username]
            )
        }

    def act(self, username, action, note_id):
        self.handler.user = self.users[username]
        self.responses.clear()
        self.handler.handle_notification_action({
            "action": action,
            "id": note_id,
        })
        return self.responses[-1][0]

    def create(self, **changes):
        self.handler.user = self.agent
        self.responses.clear()
        payload = {
            "action": "create",
            "recipient_role": "tenant",
            "recipient_party_id": "party-tenant1",
            "title": "Test notification",
            "message": "Synthetic test message",
        }
        payload.update(changes)
        self.handler.handle_notification_action(payload)
        return self.responses[-1][0]

    def test_01_owner_sees_targeted_notification(self):
        self.assertIn("note-private", self.visible("tenant1"))

    def test_02_same_name_tenant_cannot_see_notification(self):
        self.assertNotIn("note-private", self.visible("tenant2"))

    def test_03_legacy_name_only_note_denied(self):
        self.assertNotIn("note-legacy", self.visible("tenant1"))
        self.assertNotIn("note-legacy", self.visible("tenant2"))

    def test_04_role_only_notification_denied(self):
        self.assertNotIn("note-role-only", self.visible("tenant1"))

    def test_05_other_tenant_cannot_mark_read(self):
        self.assertEqual(
            self.act("tenant2", "read", "note-private"),
            403,
        )
        self.assertEqual(
            self.stage["notifications"][0]["status"],
            "unread",
        )
        self.save.assert_not_called()

    def test_06_other_tenant_cannot_mark_unread(self):
        self.stage["notifications"][0]["status"] = "read"
        self.assertEqual(
            self.act("tenant2", "unread", "note-private"),
            403,
        )
        self.assertEqual(
            self.stage["notifications"][0]["status"],
            "read",
        )

    def test_07_owner_can_mark_read(self):
        self.assertEqual(
            self.act("tenant1", "read", "note-private"),
            200,
        )
        self.assertEqual(
            self.stage["notifications"][0]["status"],
            "read",
        )
        self.save.assert_called_once()

    def test_08_unlinked_account_sees_nothing(self):
        self.users["tenant1"]["account_id"] = "unknown"
        self.assertEqual(self.visible("tenant1"), set())

    def test_09_inactive_party_sees_nothing(self):
        self.stage["parties"][0]["status"] = "inactive"
        self.assertEqual(self.visible("tenant1"), set())

    def test_10_create_valid_target(self):
        self.assertEqual(self.create(), 200)
        created = self.stage["notifications"][-1]
        self.assertEqual(
            created["recipient_party_id"],
            "party-tenant1",
        )

    def test_11_create_without_party_rejected(self):
        self.assertEqual(
            self.create(recipient_party_id=None), 400
        )

    def test_12_create_with_name_only_rejected(self):
        self.assertEqual(
            self.create(
                recipient_party_id=None,
                recipient_name="Alex Example",
            ),
            400,
        )

    def test_13_create_wrong_role_party_rejected(self):
        self.assertEqual(
            self.create(recipient_party_id="party-trade1"),
            400,
        )

    def test_14_create_unknown_party_rejected(self):
        self.assertEqual(
            self.create(recipient_party_id="party-unknown"),
            400,
        )

    def test_15_create_inactive_party_rejected(self):
        self.stage["parties"][0]["status"] = "inactive"
        self.assertEqual(self.create(), 400)

    def test_16_create_list_party_id_rejected(self):
        self.assertEqual(
            self.create(recipient_party_id=["party-tenant1"]),
            400,
        )

    def test_17_create_agent_notification(self):
        self.assertEqual(
            self.create(
                recipient_role="agent",
                recipient_party_id=None,
            ),
            200,
        )

    def test_18_agent_sees_legacy_notes(self):
        notes = self.handler.scoped_notifications(self.agent)
        self.assertEqual(len(notes), 3)


if __name__ == "__main__":
    unittest.main()
