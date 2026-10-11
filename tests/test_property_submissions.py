"""Focused cross-role property onboarding tests for Roger MVP."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


class PropertySubmissionTests(unittest.TestCase):
    def setUp(self):
        self.stage = {
            "parties": [
                {"id": "owner-1", "account_id": "account-1", "roles": ["landlord"],
                 "status": "active", "display_name": "Landlord One"},
                {"id": "owner-2", "account_id": "account-2", "roles": ["landlord"],
                 "status": "active", "display_name": "Landlord Two"},
            ],
            "properties": [], "cases": [], "jobs": [], "approvals": [],
            "audit_log": [], "property_submissions": [],
        }
        self.h = serve.H.__new__(serve.H)
        self.responses = []
        self.h._json = lambda data, code=200: self.responses.append((data, code))
        self.h.user = self.landlord("account-1")
        self.load_patch = patch.object(serve, "load_stage", return_value=self.stage)
        self.save_patch = patch.object(serve, "save_stage")
        self.load_patch.start()
        self.saved = self.save_patch.start()
        self.addCleanup(self.load_patch.stop)
        self.addCleanup(self.save_patch.stop)

    @staticmethod
    def landlord(account_id):
        return {"username": account_id, "display_name": "Same display name",
                "account_id": account_id, "role": "landlord"}

    def details(self, **kwargs):
        return {
            "address": "12 Example Road", "postcode": "TW9 1AA", "area": "Richmond",
            "property_type": "Flat", "description": "Two-bedroom flat",
            "beds": 2, "rent_pence": 225000, **kwargs,
        }

    def submit(self, **kwargs):
        self.h.handle_landlord_property_submission(self.details(**kwargs))
        return self.responses[-1]

    def decide(self, action, note=""):
        self.h.user = {"username": "agent", "display_name": "Agent",
                       "account_id": "account-agent", "role": "agent"}
        sid = self.stage["property_submissions"][0]["id"]
        self.h.handle_agent_property_submission({"submission_id": sid,
                                                  "action": action, "note": note})
        return self.responses[-1]

    def test_submission_does_not_create_public_property(self):
        reply, code = self.submit()
        self.assertEqual(code, 200)
        self.assertEqual(reply["status"], "pending")
        self.assertEqual(self.stage["properties"], [])
        self.assertEqual(self.stage["property_submissions"][0]["landlord_party_id"], "owner-1")
        self.assertEqual(self.stage["property_submissions"][0]["created_by_account_id"], "account-1")

    def test_unlinked_landlord_cannot_submit(self):
        self.h.user = self.landlord("unlinked")
        data, code = self.submit()
        self.assertEqual(code, 403)
        self.assertEqual(len(self.stage["property_submissions"]), 0)
        self.saved.assert_not_called()

    def test_landlord_cannot_resubmit_another_account_submission(self):
        data, code = self.submit()
        self.assertEqual(code, 200)
        self.assertEqual(self.decide("request_changes", "Please specify access")[1], 200)
        before = copy.deepcopy(self.stage)
        self.h.user = self.landlord("account-2")
        data, code = self.submit(submission_id=before["property_submissions"][0]["id"])
        self.assertEqual(code, 403)
        self.assertEqual(before, self.stage)

    def test_changes_then_approval_create_private_onboarding_property(self):
        self.assertEqual(self.submit()[1], 200)
        self.assertEqual(self.decide("request_changes", "Please confirm rent")[1], 200)
        self.h.user = self.landlord("account-1")
        data, code = self.submit(submission_id="submission-1", rent_pence=235000)
        self.assertEqual(code, 200)
        self.assertEqual(data["status"], "pending")
        data, code = self.decide("approve")
        self.assertEqual(code, 200)
        self.assertEqual(data["status"], "approved")
        prop = self.stage["properties"][0]
        self.assertEqual(prop["landlord_party_id"], "owner-1")
        self.assertEqual(prop["rent"], 235000)
        self.assertEqual(prop["lifecycle_status"], "onboarding")
        self.assertEqual(prop["public_listing"], {})
        self.assertEqual(self.decide("approve")[1], 409)

        self.h.serve_public_listings()
        listings, code = self.responses[-1]
        self.assertEqual(code, 200)
        self.assertEqual(listings["properties"], [])

    def test_decline_requires_note_and_is_final(self):
        self.submit()
        self.assertEqual(self.decide("decline")[1], 400)
        self.assertEqual(self.decide("decline", "Outside our area")[1], 200)
        self.h.user = self.landlord("account-1")
        self.assertEqual(self.submit(submission_id="submission-1")[1], 409)

    def test_landlord_stage_excludes_other_landlords_submissions(self):
        self.submit()
        self.h.user = self.landlord("account-2")
        self.h.session_user = lambda: self.h.user
        self.h.serve_scoped_stage()
        result, code = self.responses[-1]
        self.assertEqual(code, 200)
        self.assertEqual(result["property_submissions"], [])
        self.assertEqual(result["properties"], [])

    def test_bad_property_values_do_not_save(self):
        self.assertEqual(self.submit(rent_pence=-1)[1], 400)
        self.assertEqual(self.submit(address="")[1], 400)
        self.assertEqual(self.submit(beds=100)[1], 400)
        self.assertEqual(self.stage["property_submissions"], [])

    def test_api_role_boundaries(self):
        self.assertEqual(serve.H.ROLE_API["/api/landlord/property-submission"], {"landlord"})
        self.assertEqual(serve.H.ROLE_API["/api/agent/property-submission"], {"agent"})


if __name__ == "__main__":
    unittest.main()
