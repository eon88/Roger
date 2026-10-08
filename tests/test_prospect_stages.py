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
        serve.H.serve_public_listings(self.handler)
        response = self.responses[-1][0]
        self.assertEqual([p["id"] for p in response["properties"]], ["live"])
        self.assertNotIn("landlord", response["properties"][0])
        self.assertNotIn("tenant", response["properties"][0])
        self.assertFalse(response["demo"])

    def test_party_creation_keeps_identity_separate_from_account(self):
        serve.H.handle_party_action(self.handler, {
            "kind": "person", "display_name": "Alex Example",
            "email": "shared@example.test", "roles": ["tenant"],
        })
        party = self.stage["parties"][0]
        self.assertEqual(party["id"], "party-1")
        self.assertEqual(party["account_id"], None)
        self.assertEqual(party["roles"], ["tenant"])
        self.assertEqual(self.responses[-1][1], 200)
        self.saved.assert_called_once_with(self.stage)

    def test_party_roles_reject_malformed_values(self):
        serve.H.handle_party_action(self.handler, {
            "kind": "person", "display_name": "Bad role", "roles": [{}],
        })
        self.assertEqual(self.responses[-1][1], 400)
        self.saved.assert_not_called()

    def test_signed_agreement_cannot_be_rewritten(self):
        self.stage["tenancies"] = [{
            "id": "tenancy-1", "agreement_status": "signed",
            "agreement_signed_at": "2026-09-25", "history": [],
        }]
        serve.H.handle_tenancy_action(self.handler, {
            "action": "agreement", "id": "tenancy-1",
            "agreement_status": "draft", "signed_at": "",
        })
        self.assertEqual(self.responses[-1][1], 409)
        self.assertEqual(self.stage["tenancies"][0]["agreement_status"], "signed")
        self.saved.assert_not_called()

    def test_tenancy_creation_requires_and_links_party_ids(self):
        self.stage["properties"] = [{"id": "home-1", "title": "Home"}]
        self.stage["cases"] = [{"id": 490, "type": "enquiry", "role": "renter", "name": "Prospect"}]
        self.stage["parties"] = [
            {"id": "party-1", "roles": ["landlord"], "status": "active"},
            {"id": "party-2", "roles": ["tenant"], "status": "active", "account_id": None},
        ]
        serve.H.handle_tenancy_action(self.handler, {
            "action": "create", "property_id": "home-1", "source_prospect_id": "490",
            "landlord_party_ids": ["party-1"], "tenant_party_ids": ["party-2"],
            "start_date": "2026-10-01", "rent_amount_pence": 125000,
            "deposit_amount_pence": 0, "rent_frequency": "monthly",
        })
        tenancy = self.stage["tenancies"][0]
        self.assertEqual(tenancy["tenant_party_ids"], ["party-2"])
        self.assertEqual(tenancy["landlord_party_ids"], ["party-1"])
        self.assertEqual(tenancy["source_prospect_id"], "490")
        self.assertEqual(tenancy["status"], "application")
        self.assertEqual(tenancy["agreement_status"], "draft")
        self.assertIsNone(self.stage["parties"][1]["account_id"])
        self.saved.assert_called_once_with(self.stage)

    def test_active_tenancy_requires_signed_agreement_and_property_let_agreed(self):
        self.stage["properties"] = [{"id": "home-1", "lifecycle_status": "let_agreed"}]
        self.stage["tenancies"] = [{
            "id": "tenancy-1", "property_id": "home-1", "status": "move_in_scheduled",
            "agreement_status": "draft", "start_date": "2026-10-01",
        }]
        serve.H.handle_tenancy_action(self.handler, {
            "action": "transition", "id": "tenancy-1", "status": "active",
        })
        self.assertEqual(self.responses[-1][1], 409)
        self.saved.assert_not_called()

    def test_tenancy_full_occupancy_cycle_moves_property_safely(self):
        prop = {"id": "home-1", "lifecycle_status": "let_agreed"}
        tenancy = {
            "id": "tenancy-1", "property_id": "home-1", "status": "move_in_scheduled",
            "agreement_status": "draft", "start_date": "2026-10-01",
            "history": [], "checkout_date": None,
        }
        self.stage["properties"] = [prop]
        self.stage["tenancies"] = [tenancy]
        serve.H.handle_tenancy_action(self.handler, {
            "action": "agreement", "id": "tenancy-1",
            "agreement_status": "signed", "signed_at": "2026-09-25",
        })
        serve.H.handle_tenancy_action(self.handler, {
            "action": "transition", "id": "tenancy-1", "status": "active",
        })
        self.assertEqual(prop["lifecycle_status"], "occupied")
        self.assertEqual(tenancy["move_in_date"], "2026-10-01")
        serve.H.handle_tenancy_action(self.handler, {
            "action": "transition", "id": "tenancy-1", "status": "notice_given",
            "effective_date": "2026-12-01",
        })
        self.assertEqual(prop["lifecycle_status"], "notice_given")
        serve.H.handle_tenancy_action(self.handler, {
            "action": "transition", "id": "tenancy-1", "status": "checkout",
            "effective_date": "2027-01-01",
        })
        serve.H.handle_tenancy_action(self.handler, {
            "action": "transition", "id": "tenancy-1", "status": "deposit_resolution",
        })
        serve.H.handle_tenancy_action(self.handler, {
            "action": "transition", "id": "tenancy-1", "status": "former_tenant",
        })
        self.assertEqual(tenancy["end_date"], "2027-01-01")
        self.assertEqual(prop["lifecycle_status"], "void")
        self.assertEqual(self.responses[-1][1], 200)

    def test_active_tenancy_moves_property_out_of_public_inventory(self):
        prop = {
            "id": "home-1", "title": "12 Example Road", "area": "Exampleton",
            "beds": 2, "rent": 125000, "lifecycle_status": "advertised",
            "public_listing": {"description": "Public copy."},
        }
        self.stage["properties"] = [prop]
        self.stage["tenancies"] = [{
            "id": "tenancy-1", "property_id": "home-1", "status": "active",
        }]
        serve.H.serve_public_listings(self.handler)
        response = self.responses[-1][0]
        self.assertEqual(response["properties"], [])
        self.assertTrue(response["demo"])

    def test_trade_cannot_enter_approved_stage_before_registration_approval(self):
        serve.H.handle_prospect_action(self.handler, {
            "kind": "trades", "id": "reg-1", "stage": "approved",
        })
        self.assertEqual(self.responses[-1][1], 409)
        self.assertNotIn("prospect_stage", self.stage["registrations"][0])
        self.saved.assert_not_called()

    def test_rent_receipt_snapshots_management_fee(self):
        self.stage["management_agreements"] = [{
            "id": "management-1", "landlord_party_id": "party-1",
            "property_ids": ["home-1"], "agreement_type": "full_management",
            "management_fee_bps": 1000, "status": "active",
        }]
        self.stage["rent_ledger_entries"] = [{
            "id": "rent-1", "property_id": "home-1", "due_date": "2099-01-01",
            "amount_due_pence": 10000, "payments": [], "adjustments": [],
        }]
        serve.H.handle_rent_ledger_action(self.handler, {
            "action": "receipt", "entry_id": "rent-1", "amount_pence": 5000,
            "received_date": "2026-10-01",
        })
        payment = self.stage["rent_ledger_entries"][0]["payments"][0]
        self.assertEqual(payment["agency_fee_pence"], 500)
        self.assertEqual(payment["management_fee_bps"], 1000)
        self.assertEqual(payment["management_agreement_id"], "management-1")

    def test_landlord_statement_snapshots_rent_fees_and_paid_maintenance(self):
        self.stage["parties"] = [{
            "id": "party-1", "display_name": "Landlord", "roles": ["landlord"], "status": "active",
        }]
        self.stage["management_agreements"] = [{
            "id": "management-1", "landlord_party_id": "party-1",
            "property_ids": ["home-1"], "status": "active",
        }]
        self.stage["rent_ledger_entries"] = [{
            "id": "rent-1", "tenancy_id": "tenancy-1", "property_id": "home-1",
            "payments": [{"received_date": "2026-10-05", "amount_pence": 100000,
                          "agency_fee_pence": 10000, "landlord_party_id": "party-1"}],
        }]
        self.stage["jobs"] = [{
            "id": "job-1", "property_id": "home-1", "status": "paid",
            "invoice_pence": 15000, "paid_at": "2026-10-06T10:00:00Z",
        }]
        serve.H.handle_landlord_statement_action(self.handler, {
            "landlord_party_id": "party-1", "period_start": "2026-10-01",
            "period_end": "2026-10-31",
        })
        statement = self.stage["landlord_statements"][0]
        self.assertEqual(statement["rent_received_pence"], 100000)
        self.assertEqual(statement["agency_fee_pence"], 10000)
        self.assertEqual(statement["maintenance_pence"], 15000)
        self.assertEqual(statement["net_payout_pence"], 75000)
        self.assertEqual(len(statement["rent_lines"]), 1)
        self.assertEqual(len(statement["maintenance_lines"]), 1)
        self.saved.assert_called_once_with(self.stage)

    def test_rent_schedule_is_built_from_signed_tenancy_and_is_idempotent(self):
        self.stage["tenancies"] = [{
            "id": "tenancy-1", "property_id": "home-1", "status": "active",
            "agreement_status": "signed", "rent_amount_pence": 125000,
            "rent_frequency": "monthly",
        }]
        serve.H.handle_rent_ledger_action(self.handler, {
            "action": "generate", "tenancy_id": "tenancy-1",
            "first_due_date": "2027-01-31", "periods": 3,
        })
        self.assertEqual([x["due_date"] for x in self.stage["rent_ledger_entries"]],
                         ["2027-01-31", "2027-02-28", "2027-03-31"])
        self.assertEqual(self.responses[-1][0]["skipped_duplicates"], 0)
        serve.H.handle_rent_ledger_action(self.handler, {
            "action": "generate", "tenancy_id": "tenancy-1",
            "first_due_date": "2027-01-31", "periods": 3,
        })
        self.assertEqual(len(self.stage["rent_ledger_entries"]), 3)
        self.assertEqual(self.responses[-1][0]["skipped_duplicates"], 3)

    def test_rent_receipts_track_partial_and_full_balances(self):
        self.stage["rent_ledger_entries"] = [{
            "id": "rent-1", "tenancy_id": "tenancy-1", "due_date": "2099-01-01",
            "amount_due_pence": 125000, "payments": [], "adjustments": [],
        }]
        serve.H.handle_rent_ledger_action(self.handler, {
            "action": "receipt", "entry_id": "rent-1", "amount_pence": 50000,
            "received_date": "2026-10-01",
        })
        self.assertEqual(self.responses[-1][0]["entry"]["balance_pence"], 75000)
        self.assertEqual(self.responses[-1][0]["entry"]["status"], "partial")
        serve.H.handle_rent_ledger_action(self.handler, {
            "action": "receipt", "entry_id": "rent-1", "amount_pence": 75000,
            "received_date": "2026-10-02",
        })
        self.assertEqual(self.responses[-1][0]["entry"]["balance_pence"], 0)
        self.assertEqual(self.responses[-1][0]["entry"]["status"], "paid")

    def test_rent_receipt_cannot_exceed_balance_and_adjustment_keeps_a_reason(self):
        self.stage["rent_ledger_entries"] = [{
            "id": "rent-1", "due_date": "2099-01-01",
            "amount_due_pence": 10000, "payments": [], "adjustments": [],
        }]
        serve.H.handle_rent_ledger_action(self.handler, {
            "action": "receipt", "entry_id": "rent-1", "amount_pence": 10001,
            "received_date": "2026-10-01",
        })
        self.assertEqual(self.responses[-1][1], 400)
        serve.H.handle_rent_ledger_action(self.handler, {
            "action": "adjustment", "entry_id": "rent-1",
            "amount_pence": -1000, "reason": "",
        })
        self.assertEqual(self.responses[-1][1], 400)
        self.saved.assert_not_called()

    def test_rent_schedule_requires_signed_agreement(self):
        self.stage["tenancies"] = [{
            "id": "tenancy-1", "status": "active", "agreement_status": "draft",
            "rent_amount_pence": 10000, "rent_frequency": "monthly",
        }]
        serve.H.handle_rent_ledger_action(self.handler, {
            "action": "generate", "tenancy_id": "tenancy-1",
            "first_due_date": "2026-11-01", "periods": 1,
        })
        self.assertEqual(self.responses[-1][1], 409)
        self.assertNotIn("rent_ledger_entries", self.stage)

    def test_trade_cannot_be_approved_before_checked_credentials(self):
        self.stage["registrations"] = [{
            "id": "trade-2", "role": "trades", "status": "pending",
            "prospect_stage": "credentials_submitted",
        }]
        serve.H.handle_registration_action(self.handler, {"id": "trade-2", "action": "approve"})
        self.assertEqual(self.responses[-1][1], 409)
        self.assertEqual(self.stage["registrations"][0]["status"], "pending")
        self.saved.assert_not_called()

    def test_trade_credentials_check_enables_registration_approval_and_availability(self):
        self.stage["registrations"] = [{
            "id": "trade-2", "role": "trades", "status": "pending",
            "name": "Trade Two", "trades": ["plumbing"], "prospect_stage": "credentials_submitted",
        }]
        serve.H.handle_prospect_action(self.handler, {
            "kind": "trades", "id": "trade-2", "stage": "checked",
        })
        reg = self.stage["registrations"][0]
        self.assertTrue(reg.get("credentials_checked_at"))
        self.assertEqual(reg["credentials_checked_by"], "agent")
        serve.H.handle_registration_action(self.handler, {"id": "trade-2", "action": "approve"})
        self.assertEqual(reg["status"], "approved")
        serve.H.handle_prospect_action(self.handler, {
            "kind": "trades", "id": "trade-2", "stage": "approved",
        })
        serve.H.handle_prospect_action(self.handler, {
            "kind": "trades", "id": "trade-2", "stage": "available",
        })
        self.assertEqual(reg["prospect_stage"], "available")
        self.assertEqual(self.responses[-1][1], 200)

    def test_suspended_trade_is_removed_from_job_assignment_pool(self):
        self.stage["registrations"] = [{
            "id": "trade-2", "role": "trades", "status": "approved",
            "name": "Trade Two", "trades": ["plumbing"], "prospect_stage": "suspended",
        }]
        results = serve.H.approved_trades(self.handler, self.stage)
        self.assertNotIn("Trade Two", [x["company"] for x in results])

    def test_trade_registration_can_enter_credentials_stage(self):
        serve.H.handle_prospect_action(self.handler, {
            "kind": "trades", "id": "reg-1", "stage": "credentials_submitted",
        })
        record = self.stage["registrations"][0]
        self.assertEqual(record["status"], "pending")
        self.assertEqual(record["prospect_stage"], "credentials_submitted")
        self.saved.assert_called_once_with(self.stage)



    def test_email_sync_fails_closed_without_imap_configuration(self):
        with patch.dict("os.environ", {"ROGER_IMAP_HOST": "", "ROGER_IMAP_USER": "", "ROGER_IMAP_PASSWORD": ""}):
            serve.H.handle_email_sync(self.handler, {})
        self.assertEqual(self.responses[-1][1], 503)
        self.saved.assert_not_called()

    def test_email_sync_matches_contact_and_creates_unmatched_email_case(self):
        self.stage["cases"][0]["email"] = "tenant@example.test"
        raw_messages = {
            b"42": b"From: Tenant Example <tenant@example.test>\\r\\nSubject: Re: Repair\\r\\nContent-Type: text/plain; charset=utf-8\\r\\n\\r\\nAny update?\\r\\n",
            b"43": b"From: New Person <new@example.test>\\r\\nSubject: Viewing request\\r\\nContent-Type: text/plain; charset=utf-8\\r\\n\\r\\nCan I view tomorrow?\\r\\n",
        }
        class FakeMailbox:
            def __init__(self, *args, **kwargs): self.marked=[]
            def login(self, *args): return "OK", []
            def select(self, *args): return "OK", []
            def uid(self, action, *args):
                if action == "search": return "OK", [b"42 43"]
                if action == "fetch": return "OK", [(b"RFC822", raw_messages[args[0]])]
                if action == "store": self.marked.append(args[0]); return "OK", []
                raise AssertionError(action)
            def logout(self): return "BYE", []
        with patch.dict("os.environ", {
            "ROGER_IMAP_HOST": "imap.example.test", "ROGER_IMAP_USER": "agent",
            "ROGER_IMAP_PASSWORD": "secret", "ROGER_IMAP_FOLDER": "INBOX",
        }):
            with patch.object(serve.imaplib, "IMAP4_SSL", FakeMailbox):
                serve.H.handle_email_sync(self.handler, {})
        self.assertEqual(self.responses[-1][1], 200)
        self.assertEqual(self.responses[-1][0]["count"], 2)
        self.assertEqual(self.stage["cases"][0]["thread"][-1]["email_from"], "tenant@example.test")
        created = self.stage["cases"][-1]
        self.assertEqual(created["type"], "email")
        self.assertEqual(created["email"], "new@example.test")
        self.assertEqual(self.stage["audit_log"][-1]["action"], "email_case_created")
        self.assertEqual(self.stage["imported_email_uids"], ["imap.example.test:INBOX:42", "imap.example.test:INBOX:43"])
        self.saved.assert_called_once_with(self.stage)

    def test_email_reply_fails_closed_when_smtp_is_not_configured(self):
        self.stage["cases"][0]["email"] = "tenant@example.test"
        with patch.dict("os.environ", {"ROGER_SMTP_HOST": "", "ROGER_FROM_EMAIL": ""}):
            serve.H.handle_email_reply(self.handler, {"id": 490, "text": "Hello"})
        self.assertEqual(self.responses[-1][1], 503)
        self.assertNotIn("thread", self.stage["cases"][0])
        self.saved.assert_not_called()

    def test_email_reply_sends_only_to_case_contact_and_records_timeline(self):
        self.stage["cases"][0]["email"] = "tenant@example.test"
        with patch.dict("os.environ", {
            "ROGER_SMTP_HOST": "smtp.example.test", "ROGER_SMTP_PORT": "587",
            "ROGER_FROM_EMAIL": "agent@example.test", "ROGER_SMTP_USER": "agent",
            "ROGER_SMTP_PASSWORD": "secret",
        }):
            with patch.object(serve.smtplib, "SMTP") as smtp:
                serve.H.handle_email_reply(self.handler, {"id": 490, "text": "Hello from Roger"})
        smtp.return_value.__enter__.return_value.send_message.assert_called_once()
        sent = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
        self.assertEqual(sent["To"], "tenant@example.test")
        self.assertEqual(sent["From"], "Roger <agent@example.test>")
        msg = self.stage["cases"][0]["thread"][0]
        self.assertEqual(msg["channel"], "email")
        self.assertEqual(msg["email_to"], "tenant@example.test")
        self.assertEqual(self.stage["audit_log"][-1]["action"], "case_email_sent")
        self.saved.assert_called_once_with(self.stage)
        self.assertEqual(self.responses[-1][1], 200)

    def test_approved_landlord_registration_links_to_party_without_merging(self):
        self.stage["registrations"] = [{"id": "land-1", "role": "landlord", "status": "approved"}]
        serve.H.handle_party_action(self.handler, {
            "kind": "person", "display_name": "Landlord Example",
            "roles": ["landlord"], "registration_id": "land-1",
        })
        party = self.stage["parties"][0]
        self.assertEqual(party["source_registration_id"], "land-1")
        self.assertEqual(self.stage["registrations"][0]["party_id"], party["id"])
        self.assertIsNone(party["account_id"])
        self.assertEqual(self.responses[-1][1], 200)
        self.saved.assert_called_once_with(self.stage)

    def test_party_cannot_link_unapproved_landlord_registration(self):
        self.stage["registrations"] = [{"id": "land-1", "role": "landlord", "status": "pending"}]
        serve.H.handle_party_action(self.handler, {
            "kind": "person", "display_name": "Landlord Example",
            "roles": ["landlord"], "registration_id": "land-1",
        })
        self.assertEqual(self.responses[-1][1], 409)
        self.assertNotIn("parties", self.stage)
        self.saved.assert_not_called()

    def test_management_agreement_must_be_signed_before_activation(self):
        self.stage["parties"] = [{"id": "party-1", "status": "active", "roles": ["landlord"]}]
        self.stage["properties"] = [{"id": "home-1"}]
        serve.H.handle_management_agreement_action(self.handler, {
            "action": "create", "landlord_party_id": "party-1",
            "property_ids": ["home-1"], "agreement_type": "full_management",
            "management_fee_bps": 1000,
        })
        agreement = self.stage["management_agreements"][0]
        self.assertEqual(agreement["status"], "draft")
        self.assertEqual(self.responses[-1][1], 200)
        serve.H.handle_management_agreement_action(self.handler, {
            "action": "transition", "id": agreement["id"], "status": "active",
        })
        self.assertEqual(self.responses[-1][1], 409)
        self.assertEqual(agreement["status"], "draft")

    def test_management_agreement_records_signed_and_active_history(self):
        self.stage["parties"] = [{"id": "party-1", "status": "active", "roles": ["landlord"]}]
        self.stage["properties"] = [{"id": "home-1"}]
        serve.H.handle_management_agreement_action(self.handler, {
            "action": "create", "landlord_party_id": "party-1",
            "property_ids": ["home-1"], "agreement_type": "let_only",
            "management_fee_bps": 0,
        })
        agreement = self.stage["management_agreements"][0]
        serve.H.handle_management_agreement_action(self.handler, {
            "action": "transition", "id": agreement["id"], "status": "sent",
        })
        serve.H.handle_management_agreement_action(self.handler, {
            "action": "transition", "id": agreement["id"], "status": "signed",
            "signed_at": serve.datetime.now(serve.timezone.utc).date().isoformat(),
            "evidence_note": "Signed copy verified in file store",
        })
        serve.H.handle_management_agreement_action(self.handler, {
            "action": "transition", "id": agreement["id"], "status": "active",
        })
        self.assertEqual(agreement["status"], "active")
        self.assertIsNotNone(agreement["signed_at"])
        self.assertEqual(agreement["evidence_note"], "Signed copy verified in file store")
        self.assertEqual(len(agreement["history"]), 4)
        self.assertEqual(self.stage["audit_log"][-1]["action"], "management_agreement_status_changed")

    def test_management_agreement_end_date_cannot_precede_signature(self):
        self.stage["management_agreements"] = [{
            "id": "management-1", "landlord_party_id": "party-1",
            "property_ids": ["home-1"], "status": "signed", "signed_at": "2026-10-01",
        }]
        serve.H.handle_management_agreement_action(self.handler, {
            "action": "transition", "id": "management-1", "status": "ended",
            "ended_at": "2026-09-30",
        })
        self.assertEqual(self.responses[-1][1], 400)
        self.assertEqual(self.stage["management_agreements"][0]["status"], "signed")
        self.saved.assert_not_called()

    def test_landlord_pipeline_requires_approved_linked_party_and_active_agreement(self):
        self.stage["registrations"] = [{
            "id": "land-1", "role": "landlord", "status": "approved",
            "party_id": "party-1", "prospect_stage": "proposal",
        }]
        self.stage["parties"] = [{"id": "party-1", "status": "active", "roles": ["landlord"]}]
        self.stage["management_agreements"] = [{
            "id": "management-1", "landlord_party_id": "party-1",
            "property_ids": ["home-1"], "status": "signed",
        }]
        serve.H.handle_prospect_action(self.handler, {
            "kind": "landlord", "id": "land-1", "stage": "onboarding",
        })
        self.assertEqual(self.responses[-1][1], 409)
        self.stage["management_agreements"][0]["status"] = "active"
        serve.H.handle_prospect_action(self.handler, {
            "kind": "landlord", "id": "land-1", "stage": "onboarding",
        })
        self.assertEqual(self.responses[-1][1], 200)
        self.assertEqual(self.stage["registrations"][0]["prospect_stage"], "onboarding")

    def test_landlord_signed_stage_allows_signed_or_active_agreement(self):
        self.stage["registrations"] = [{
            "id": "land-1", "role": "landlord", "status": "approved",
            "party_id": "party-1",
        }]
        self.stage["management_agreements"] = [{
            "id": "management-1", "landlord_party_id": "party-1",
            "status": "signed",
        }]
        serve.H.handle_prospect_action(self.handler, {
            "kind": "landlord", "id": "land-1", "stage": "signed",
        })
        self.assertEqual(self.responses[-1][1], 200)

if __name__ == "__main__":
    unittest.main()
