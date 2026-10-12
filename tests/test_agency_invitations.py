"""Agency-specific invitation acceptance must not grant arbitrary property access."""
import copy
import hashlib
import os
from pathlib import Path
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


class AgencyInvitationTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "ROGER_SAAS_MODE": "1", "ROGER_AGENCY_ID": "oaklettings",
            "ROGER_AGENCY_NAME": "Oak Lettings", "ROGER_STORAGE_BACKEND": "postgres",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.stage = {
            "agency_id": "oaklettings",
            "properties": [
                {"id": "home-1", "tenant_party_id": "party-1",
                 "landlord_party_id": "party-2", "agency_id": "oaklettings"},
                {"id": "home-2", "tenant_party_id": "party-3",
                 "agency_id": "oaklettings"}
            ],
            "parties": [
                {"id": "party-1", "status": "active", "display_name": "Tenant One",
                 "roles": ["tenant"], "email": "tenant1@example.test",
                 "account_id": None, "agency_id": "oaklettings"},
                {"id": "party-2", "status": "active", "display_name": "Landlord",
                 "roles": ["landlord"], "email": "owner@example.test",
                 "account_id": None, "agency_id": "oaklettings"},
                {"id": "party-3", "status": "active", "display_name": "Tenant Two",
                 "roles": ["tenant"], "email": "tenant2@example.test",
                 "account_id": "account-existing", "agency_id": "oaklettings"}
            ],
            "invitations": [], "registrations": [], "audit_log": []
        }
        self.users = {"users": [{"username": "agency-admin", "role": "agent",
                                 "email": "admin@example.test"}], "sessions": {}}
        self.h = serve.H.__new__(serve.H)
        self.h.user = {"role": "agent", "username": "agency-admin"}
        self.calls = []
        self.h._json = lambda obj, code=200: self.calls.append((code, obj))
        self.h.audit = lambda stage, record: stage["audit_log"].append(record)
        self.loads = [
            patch.object(serve, "load_stage", return_value=self.stage),
            patch.object(serve, "load_users", return_value=self.users),
            patch.object(serve, "save_stage"),
            patch.object(serve.H, "persist_invite_registration")
        ]
        self.mocks = [p.start() for p in self.loads]
        for p in self.loads:
            self.addCleanup(p.stop)

    def issue(self, **overrides):
        data = {"role": "tenant", "party_id": "party-1", "property_id": "home-1",
                "email": "tenant1@example.test"}
        data.update(overrides)
        self.h.handle_invitation(data)
        return self.calls[-1]

    def test_agent_issued_invitation_is_hashed_in_storage(self):
        code, result = self.issue()
        self.assertEqual(code, 200)
        link = result["invite_url"]
        self.assertTrue(link.startswith("/invite#token="))
        token = link.split("=", 1)[1]
        self.assertEqual(self.stage["invitations"][0]["token_hash"],
                         hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(token, repr(self.stage))
        self.assertTrue(self.h.validate_invitation_token(token)["valid"])
        self.assertEqual(self.stage["invitations"][0]["role"], "tenant")

    def test_redeem_creates_one_user_linked_to_existing_party_not_new_property(self):
        _, result = self.issue()
        token = result["invite_url"].split("=", 1)[1]
        self.calls.clear()
        self.h.handle_invite_acceptance({
            "token": token, "username": "tenantone",
            "password": "long-passphrase-at-least-14"})
        code, reply = self.calls[-1]
        self.assertEqual(code, 200, reply)
        self.assertTrue(reply["success"])
        user = self.users["users"][-1]
        self.assertEqual(user["role"], "tenant")
        self.assertEqual(user["email"], "tenant1@example.test")
        self.assertEqual(self.stage["parties"][0]["account_id"], user["account_id"])
        self.assertEqual(self.stage["properties"][1]["tenant_party_id"], "party-3")
        self.assertEqual(self.stage["invitations"][0]["status"], "used")
        self.mocks[3].assert_called_once()
        self.assertNotIn("long-passphrase-at-least-14", repr(self.users))
        party_ids = self.h.account_party_ids(self.stage, user, "tenant")
        self.assertEqual(party_ids, {"party-1"})
        self.assertTrue(self.h.has_party_link(self.stage["properties"][0], "tenant", party_ids))
        self.assertFalse(self.h.has_party_link(self.stage["properties"][1], "tenant", party_ids))
        self.h.handle_invite_acceptance({"token": token, "username": "seconduser",
                                         "password": "another-good-passphrase"})
        self.assertEqual(self.calls[-1][0], 400)

    def test_incorrect_property_role_email_or_already_linked_party_rejected(self):
        variants = [
            {"property_id": "home-2"},
            {"role": "landlord"},
            {"email": "other@example.test"},
            {"party_id": "party-3", "property_id": "home-2",
             "email": "tenant2@example.test"}
        ]
        for changes in variants:
            with self.subTest(changes=changes):
                self.stage["invitations"].clear()
                self.calls.clear()
                self.assertEqual(self.issue(**changes)[0], 409)
                self.assertFalse(self.stage["invitations"])

    def test_no_duplicate_pending_invites(self):
        self.assertEqual(self.issue()[0], 200)
        self.assertEqual(self.issue()[0], 409)
        self.assertEqual(len(self.stage["invitations"]), 1)

    def test_expired_and_revoked_invitations_never_redeem(self):
        _, payload = self.issue()
        token = payload["invite_url"].split("=", 1)[1]
        record = self.stage["invitations"][0]
        record["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self.assertFalse(self.h.validate_invitation_token(token)["valid"])
        self.h.handle_invite_acceptance({"token":token,"username":"tenantone",
                                         "password":"long-passphrase-at-least-14"})
        self.assertEqual(self.calls[-1][0], 400)
        record["expires_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        self.h.handle_invitation_action({"token": token, "action": "revoke"})
        self.assertEqual(self.calls[-1][0], 200)
        self.assertFalse(self.h.validate_invitation_token(token)["valid"])

    def test_manual_use_endpoint_cannot_mark_invitation_redeemed(self):
        _, payload = self.issue()
        token = payload["invite_url"].split("=", 1)[1]
        self.h.handle_invitation_action({"token":token,"action":"use"})
        self.assertEqual(self.calls[-1][0], 400)
        self.assertEqual(self.stage["invitations"][0]["status"], "pending")

    def test_weak_password_username_and_existing_email_fail_closed(self):
        _, payload = self.issue()
        token = payload["invite_url"].split("=", 1)[1]
        for username,password in [
            ("admin", "very-long-password-abcdef"),
            ("tenantone", "short"),
            ("tenantone", "tenantone-included-in-secret")
        ]:
            self.h.handle_invite_acceptance({"token":token,"username":username,"password":password})
            self.assertEqual(self.calls[-1][0], 400)
        self.users["users"].append({"username":"existing", "email":"tenant1@example.test"})
        self.h.handle_invite_acceptance({"token":token,"username":"tenantone",
                                         "password":"long-passphrase-at-least-14"})
        self.assertEqual(self.calls[-1][0], 409)
        self.mocks[3].assert_not_called()

    def test_non_saas_install_cannot_issue_or_redeem(self):
        with patch.dict(os.environ, {"ROGER_SAAS_MODE":"0"}):
            self.assertEqual(self.issue()[0], 409)
            self.h.handle_invite_acceptance({"token":"bad"})
            self.assertEqual(self.calls[-1][0], 409)

    def test_no_public_access_to_account_or_stage_routes(self):
        self.assertTrue(self.h.is_public("/invite"))
        self.assertTrue(self.h.is_public("/invite.js"))
        self.assertFalse(self.h.is_public("/api/stage"))
        self.assertFalse(self.h.is_public("/api/invitation"))
        self.assertNotIn("/api/invitation", serve.H.PUBLIC_POST)


class InvitationUiTests(unittest.TestCase):
    def test_uses_fragment_token_and_no_demo_credentials(self):
        source = (Path(__file__).resolve().parents[1] / "stage-clone" / "invite.js").read_text()
        self.assertIn('history.replaceState(null, "", "/invite")', source)
        self.assertIn("/api/invite/accept", source)
        self.assertNotIn("innerHTML", source)
        signin = (Path(__file__).resolve().parents[1] / "stage-clone" / "signin.html").read_text()
        for old in ("?u=tenant", "?u=landlord", "?u=trades", "account: dev", "Stage portal"):
            self.assertNotIn(old, signin)


if __name__ == "__main__":
    unittest.main()
