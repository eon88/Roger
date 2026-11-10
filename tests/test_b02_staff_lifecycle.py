"""B02 staff invitations and suspensions are administrator-only and atomic."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


def password_hash(secret, salt):
    return hashlib.scrypt(secret.encode(), salt=bytes.fromhex(salt),
                          n=2**14, r=8, p=1).hex()


class StaffSecurityTests(unittest.TestCase):
    def setUp(self):
        self.secret = "admin long account passphrase"
        salt = "b" * 32
        self.users = {"users": [{
            "username": "agency-admin", "role": "agent", "account_id": "root-admin",
            "agency_id": "oaklettings", "display_name": "Agency Owner",
            "email": "owner@example.test", "salt": salt,
            "hash": password_hash(self.secret, salt),
        }], "sessions": {}}
        self.stage = {"agency_id": "oaklettings", "properties": [], "parties": [],
                      "invitations": [], "audit_log": []}
        self.h = serve.H.__new__(serve.H)
        self.h.user = self.users["users"][0]
        self.replies = []
        self.h._json = lambda payload, code=200: self.replies.append((code, payload))
        self.h.audit = lambda stage, entry: stage.setdefault("audit_log", []).append(entry)
        self.environment = patch.dict("os.environ", {
            "ROGER_SAAS_MODE": "1", "ROGER_STORAGE_BACKEND": "postgres",
            "ROGER_AGENCY_ID": "oaklettings",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        patches = [
            patch.object(serve, "load_users", return_value=self.users),
            patch.object(serve, "load_stage", return_value=self.stage),
            patch.object(serve, "save_stage"),
            patch.object(serve.H, "persist_invite_registration"),
        ]
        self.mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)

    def invite(self, **changes):
        payload = {
            "current_password": self.secret, "display_name": "New Staff",
            "email": "staff@example.test",
        }
        payload.update(changes)
        self.h.handle_staff_invitation(payload)
        return self.replies[-1]

    def token(self):
        result = self.invite()
        self.assertEqual(result[0], 200, result)
        token = result[1]["invite_url"].split("=", 1)[1]
        return token

    def test_admin_issues_hash_only_short_lived_invitation(self):
        token = self.token()
        invite = self.stage["invitations"][0]
        self.assertTrue(invite["staff_invitation"])
        self.assertEqual(invite["role"], "agent")
        self.assertEqual(invite["status"], "pending")
        self.assertEqual(invite["token_hash"], hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(token, repr(self.stage))
        self.assertLess(
            datetime.fromisoformat(invite["expires_at"]) - datetime.now(timezone.utc),
            timedelta(hours=49))
        self.assertTrue(self.h.validate_invitation_token(token)["valid"])
        self.assertEqual(self.stage["audit_log"][0]["action"], "staff_invitation_created")

    def test_staff_redeems_once_and_is_never_linked_to_another_property(self):
        token = self.token()
        self.h.handle_invite_acceptance({
            "token": token, "username": "newstaff",
            "password": "staff unique passphrase-123",
        })
        self.assertEqual(self.replies[-1][0], 200)
        account = self.users["users"][-1]
        self.assertEqual(account["role"], "agent")
        self.assertEqual(account["agency_id"], "oaklettings")
        self.assertEqual(account["email"], "staff@example.test")
        self.assertNotIn("staff unique passphrase-123", repr(self.users))
        self.assertEqual(self.stage["invitations"][0]["status"], "used")
        self.assertEqual(self.stage["parties"], [])
        self.mocks[3].assert_called_once()
        self.h.handle_invite_acceptance({
            "token": token, "username": "secondstaff",
            "password": "another unique passphrase",
        })
        self.assertEqual(self.replies[-1][0], 400)
        self.assertEqual(len(self.users["users"]), 2)

    def test_wrong_or_nonadmin_agent_cannot_issue_staff_privileges(self):
        original = copy.deepcopy(self.stage)
        self.assertEqual(self.invite(current_password="wrong")[0], 403)
        staff_actor = dict(self.users["users"][0], username="regularagent")
        self.h.user = staff_actor
        self.assertEqual(self.invite()[0], 403)
        self.assertEqual(self.stage, original)
        self.mocks[2].assert_not_called()

    def test_non_agent_cannot_issue_staff_invitation(self):
        self.h.user = {**self.h.user, "role": "tenant"}
        self.assertEqual(self.invite()[0], 403)
        self.assertEqual(self.stage["invitations"], [])

    def test_existing_email_or_pending_invite_not_reissued(self):
        self.token()
        self.assertEqual(self.invite()[0], 409)
        self.assertEqual(len(self.stage["invitations"]), 1)
        self.stage["invitations"].clear()
        self.users["users"].append({
            "username": "existing", "role": "tenant",
            "email": "staff@example.test",
        })
        self.assertEqual(self.invite()[0], 409)

    def test_agent_cannot_revoke_administrator_staff_invitation(self):
        token = self.token()
        self.h.user = {**self.h.user, "username": "regularagent"}
        self.h.handle_invitation_action({"token": token, "action": "revoke"})
        self.assertEqual(self.replies[-1][0], 403)
        self.assertEqual(self.stage["invitations"][0]["status"], "pending")

    def test_admin_suspends_staff_revokes_sessions_but_not_owner(self):
        token = self.token()
        self.h.handle_invite_acceptance({
            "token": token, "username": "newstaff",
            "password": "staff unique passphrase-123",
        })
        self.users["sessions"] = {
            "staff-one": {"username": "newstaff"},
            "staff-two": {"username": "newstaff"},
            "admin-session": {"username": "agency-admin"},
        }
        self.h.handle_staff_suspend({
            "current_password": self.secret, "username": "newstaff",
            "reason": "Employment terminated, access must stop now",
        })
        self.assertEqual(self.replies[-1][0], 200)
        self.assertEqual(self.replies[-1][1]["sessions_revoked"], 2)
        self.assertEqual(set(self.users["sessions"]), {"admin-session"})
        self.assertTrue(self.users["users"][1]["disabled_at"])
        self.assertFalse(self.users["users"][0].get("disabled_at"))
        self.assertEqual(self.stage["audit_log"][-1]["action"], "staff_account_suspended")

    def test_cannot_silently_disable_agency_admin(self):
        original = copy.deepcopy(self.users)
        self.h.handle_staff_suspend({
            "current_password": self.secret, "username": "agency-admin",
            "reason": "Unsafe attempt to remove the administrator",
        })
        self.assertEqual(self.replies[-1][0], 400)
        self.assertEqual(self.users, original)

    def test_expired_staff_invite_not_valid(self):
        token = self.token()
        self.stage["invitations"][0]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self.assertFalse(self.h.validate_invitation_token(token)["valid"])
        self.h.handle_invite_acceptance({
            "token": token, "username": "newstaff",
            "password": "staff unique passphrase-123",
        })
        self.assertEqual(self.replies[-1][0], 400)


if __name__ == "__main__":
    unittest.main()
