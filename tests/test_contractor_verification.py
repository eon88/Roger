"""Task 04: contractor document verification and fail-closed dispatch gates.

Synthetic records. Human "independent check" source/reference attestations are NOT an
automatic lookup against an external insurer or regulated trade register.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


class ContractorVerificationTests(unittest.TestCase):
    def setUp(self):
        self.valid_until = (datetime.now(timezone.utc).date()+timedelta(days=60)).isoformat()
        self.stage = {
            "parties": [
                {"id": "trade-one", "source_registration_id": "reg-one",
                 "account_id": "trade-account-one", "roles": ["trades"], "status": "active",
                 "display_name": "Test Plumbing Ltd"},
                {"id": "trade-two", "source_registration_id": "reg-two",
                 "account_id": "trade-account-two", "roles": ["trades"], "status": "active",
                 "display_name": "Other Firm"},
            ],
            "registrations": [
                {"id": "reg-one", "role": "trades", "status": "approved", "prospect_stage": "available",
                 "name": "Test Plumbing Ltd", "party_id": "trade-one", "gas_safe_number": "CLAIM-ONLY",
                 "trades": ["plumbing", "gas"], "credentials_checked_at": "2026-10-01T10:00:00Z",
                 "insurance_expiry": "2099-12-31"},
                {"id": "reg-two", "role": "trades", "status": "approved", "prospect_stage": "available",
                 "name": "Other Firm", "party_id": "trade-two", "trades": ["plumbing"],
                 "credentials_checked_at": "2026-10-01T10:00:00Z", "insurance_expiry": "2099-12-31"},
            ],
            "properties": [
                {"id": "home-leeds", "area": "Leeds", "postcode": "LS1 1AA"},
                {"id": "home-bristol", "area": "Bristol", "postcode": "BS1 1AA"},
                {"id": "home-ls11", "area": "Other", "postcode": "LS11 2AA"},
            ],
            "documents": [
                {"id": "doc-ins", "party_id": "trade-one", "document_type": "trades_document",
                 "status": "verified", "verified_at": "2026-10-01T10:00:00Z",
                 "storage_key": "synthetic-insurance", "expiry_date": "2099-12-31"},
                {"id": "doc-qual", "party_id": "trade-one", "document_type": "trades_document",
                 "status": "verified", "verified_at": "2026-10-01T10:00:00Z",
                 "storage_key": "synthetic-qualification", "expiry_date": "2099-12-31"},
                {"id": "doc-gas", "party_id": "trade-one", "document_type": "trades_document",
                 "status": "verified", "verified_at": "2026-10-01T10:00:00Z",
                 "storage_key": "synthetic-gas", "expiry_date": "2099-12-31"},
                {"id": "doc-other-ins", "party_id": "trade-two", "document_type": "trades_document",
                 "status": "verified", "verified_at": "2026-10-01T10:00:00Z",
                 "storage_key": "synthetic-other", "expiry_date": "2099-12-31"},
            ],
            "jobs": [], "cases": [], "audit_log": [],
        }
        self.h = serve.H.__new__(serve.H)
        self.h.user = {"role": "agent", "username": "office", "display_name": "Office"}
        self.responses = []
        self.audit_events = []
        self.h._json = lambda payload, status=200: self.responses.append((payload, status))
        self.h.audit = lambda stage, event: self.audit_events.append(event)
        load = patch.object(serve, "load_stage", return_value=self.stage)
        saved = patch.object(serve, "save_stage")
        load.start()
        self.saved = saved.start()
        self.addCleanup(load.stop)
        self.addCleanup(saved.stop)

    def payload(self, **overrides):
        return {
            "registration_id": "reg-one", "action": "verify",
            "insurance_document_id": "doc-ins", "qualification_document_id": "doc-qual",
            "check_source": "test official qualification register",
            "external_check_reference": "TEST-QUAL-001",
            "insurance_check_source": "test insurer callback",
            "insurance_check_reference": "TEST-INS-001",
            "service_areas": ["LEEDS", "LS1"],
            "verified_trades": ["plumbing"], "valid_until": self.valid_until,
            **overrides,
        }

    def update(self, expected=200, **overrides):
        self.h.handle_contractor_verification(self.payload(**overrides))
        result,status=self.responses[-1]
        self.assertEqual(status, expected, result)
        return result

    def eligible(self, trade="plumbing", location="home-leeds"):
        return self.h.verified_contractor_for_new_repair(
            self.stage, "trade-one", trade, location)

    def test_requires_agent_evidence_and_independent_check_attestation(self):
        self.assertFalse(self.eligible())
        self.assertFalse(self.h.verified_contractor_for_new_repair(self.stage, "trade-two", "plumbing"))
        self.update()
        reg=self.stage["registrations"][0]
        v=reg["contractor_verification"]
        self.assertEqual(v["checked_by"], "office")
        self.assertEqual(v["insurance_document_id"], "doc-ins")
        self.assertEqual(v["qualification_document_id"], "doc-qual")
        self.assertTrue(self.eligible())
        self.assertFalse(self.eligible(location="home-bristol"))
        self.assertFalse(self.eligible(trade="electrical"))
        self.assertTrue(any(e["action"]=="contractor_independent_checks_recorded"
                            for e in self.audit_events))
        self.assertEqual(self.h.approved_trades(self.stage)[0]["ready_for_new_repairs"], True)

    def test_wrong_or_pending_documents_and_cross_party_evidence_fail(self):
        self.update(expected=409, insurance_document_id="doc-other-ins")
        self.update(expected=409, qualification_document_id="doc-ins")
        self.stage["documents"][0]["status"]="pending"
        self.update(expected=409)
        self.assertNotIn("contractor_verification", self.stage["registrations"][0])

    def test_invalid_sources_dates_service_areas_or_trades_refuse_without_saving(self):
        self.update(expected=400, check_source="", external_check_reference="")
        self.update(expected=400, insurance_check_reference="")
        self.update(expected=400, service_areas=[])
        self.update(expected=400, verified_trades=["electrician"])
        self.update(expected=409, valid_until="2099-12-31")
        self.update(expected=400, valid_until="2099-02-31")
        self.saved.assert_not_called()

    def test_revoked_and_expired_verifications_block_dispatch(self):
        self.update()
        self.assertTrue(self.eligible())
        self.update(action="revoke", reason="Insurer cancelled policy")
        self.assertFalse(self.eligible())
        self.assertEqual(self.stage["registrations"][0]["contractor_verification"]["status"],"revoked")
        self.update(expected=409, action="revoke", reason="Already revoked")
        self.update()
        self.assertTrue(self.eligible())
        self.stage["registrations"][0]["contractor_verification"]["valid_until"]="2020-01-01"
        self.assertFalse(self.eligible())

    def test_changed_or_superseded_document_invalidates_checks_immediately(self):
        self.update()
        self.stage["documents"][0]["status"]="superseded"
        self.assertFalse(self.eligible())
        self.stage["documents"][0]["status"]="verified"
        self.stage["documents"][0]["verified_at"]="2026-10-02T10:00:00Z"
        self.assertFalse(self.eligible())
        self.stage["documents"][0]["verified_at"]="2026-10-01T10:00:00Z"
        self.stage["documents"][0]["expiry_date"]="2020-01-01"
        self.assertFalse(self.eligible())

    def test_suspension_insurance_expiry_or_changed_trade_blocks_dispatch(self):
        self.update()
        reg=self.stage["registrations"][0]
        reg["prospect_stage"]="suspended"
        self.assertFalse(self.eligible())
        reg["prospect_stage"]="available"
        reg["insurance_expiry"]="2020-01-01"
        self.assertFalse(self.eligible())
        reg["insurance_expiry"]="2099-12-31"
        reg["trades"]=["gas"]
        self.assertFalse(self.eligible())

    def test_claimed_gas_safe_number_is_not_gas_verification(self):
        self.update()
        self.assertFalse(self.eligible(trade="gas"))
        self.update(expected=409, verified_trades=["gas"])
        self.update(verified_trades=["plumbing", "gas"],
                    gas_document_id="doc-gas", gas_register_reference="SYNTH-GAS-REFERENCE")
        self.assertTrue(self.eligible(trade="gas"))
        self.stage["documents"][2]["status"]="rejected"
        self.assertFalse(self.eligible(trade="gas"))
        self.assertTrue(self.eligible(trade="plumbing"))

    def test_exact_outward_postcode_match_does_not_match_longer_prefix(self):
        self.update(service_areas=["LS1"])
        self.assertTrue(self.eligible(location="home-leeds"))
        self.assertFalse(self.eligible(location="home-ls11"))
        self.assertFalse(self.eligible(location="home-bristol"))

    def test_tenant_cannot_authorise_verification_even_by_direct_handler_call(self):
        self.h.user={"role":"tenant","account_id":"tenant-1"}
        self.update(expected=403)
        self.saved.assert_not_called()

    def test_attestation_recheck_has_history_and_new_review_date(self):
        self.update()
        self.update(check_source="second review",external_check_reference="NEXT-QUAL-2")
        reg=self.stage["registrations"][0]
        self.assertEqual(len(reg["verification_history"]),2)
        self.assertEqual(reg["verification_history"][0]["status"],"superseded")
        self.assertEqual(reg["contractor_verification"]["external_check_reference"],"NEXT-QUAL-2")


if __name__ == "__main__":
    unittest.main()
