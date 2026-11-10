"""B01 canonical financial evidence and immutable audit/attachments."""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "stage-clone"))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))
import canonical_records as cr
from v1_two_agency_data import build


class ImmutableFinancialTests(unittest.TestCase):
    def setUp(self):
        self.stage = build("oaklettings")
        self.job = self.stage["jobs"][0]
        self.job.update(model_version=1, status="invoice_submitted", invoice_pence=10000)

    def test_paid_invoice_requires_real_amount_and_external_payment_proof(self):
        self.job["status"] = "paid"
        with self.assertRaisesRegex(cr.RecordIntegrityError, "settled"):
            cr.validate_for_save(self.stage)
        self.job["payments"] = [{
            "reference": "EXT-100", "amount_pence": 10000,
            "date": "2026-11-10",
        }]
        cr.validate_for_save(self.stage)
        self.job["payments"].append(copy.deepcopy(self.job["payments"][0]))
        with self.assertRaisesRegex(cr.RecordIntegrityError, "duplicate payment"):
            cr.validate_for_save(self.stage)

    def test_invoice_cannot_be_paid_without_payment_only_credit(self):
        self.job.update(status="paid", credit_notes=[{
            "number": "CN-123", "amount_pence": 10000
        }])
        with self.assertRaisesRegex(cr.RecordIntegrityError, "without payment"):
            cr.validate_for_save(self.stage)
        self.job["status"] = "credited"
        cr.validate_for_save(self.stage)

    def test_overpaid_and_contradictory_partial_status_rejected(self):
        self.job.update(status="partially_paid", payments=[{
            "reference": "EXT-1", "amount_pence": 11000,
        }])
        with self.assertRaisesRegex(cr.RecordIntegrityError, "exceed invoice"):
            cr.validate_for_save(self.stage)
        self.job["payments"][0]["amount_pence"] = 10000
        with self.assertRaisesRegex(cr.RecordIntegrityError, "partially paid"):
            cr.validate_for_save(self.stage)
        self.job["payments"][0]["amount_pence"] = 1000
        cr.validate_for_save(self.stage)

    def test_prework_job_cannot_run_without_authorisation(self):
        self.job.update(status="in_progress", requires_prework_quote=True)
        with self.assertRaisesRegex(cr.RecordIntegrityError, "approved work"):
            cr.validate_for_save(self.stage)

    def test_invoice_identity_collision_blocks_even_unversioned_partner(self):
        second = copy.deepcopy(self.job)
        second["id"] = "other-job"
        second["model_version"] = None
        self.stage["jobs"].append(second)
        self.job["assigned_to_party_id"] = "verified-contractor"
        second["assigned_to_party_id"] = "verified-contractor"
        self.job["invoice_number"] = "INV-101"
        second["invoice_number"] = "inv-101"
        with self.assertRaisesRegex(cr.RecordIntegrityError, "duplicate_supplier_invoice"):
            cr.validate_for_save(self.stage)

    def test_invoice_amount_and_payment_evidence_cannot_be_rewritten(self):
        self.job["workflow_history"] = [{
            "from": "in_progress", "to": "invoice_submitted", "at": "2026-11-10", "by": "trade"
        }]
        self.job["payments"] = [{"reference": "EXT-10", "amount_pence": 1000}]
        original = copy.deepcopy(self.stage)
        altered = copy.deepcopy(original)
        altered["jobs"][0]["invoice_pence"] = 12000
        with self.assertRaisesRegex(cr.RecordIntegrityError, "invoice amount"):
            cr.guard_no_silent_deletion(original, altered)
        altered = copy.deepcopy(original)
        altered["jobs"][0]["payments"][0]["amount_pence"] = 500
        with self.assertRaisesRegex(cr.RecordIntegrityError, "payments"):
            cr.guard_no_silent_deletion(original, altered)
        altered = copy.deepcopy(original)
        altered["jobs"][0]["workflow_history"] = []
        with self.assertRaisesRegex(cr.RecordIntegrityError, "workflow_history"):
            cr.guard_no_silent_deletion(original, altered)
        appended = copy.deepcopy(original)
        appended["jobs"][0]["workflow_history"].append({
            "from": "invoice_submitted", "to": "invoice_approved", "by": "office"
        })
        cr.guard_no_silent_deletion(original, appended)

    def test_document_evidence_cannot_be_swapped_or_moved_without_review(self):
        doc = self.stage["documents"][0]
        doc.update(model_version=1, storage_key="original-sha",
                   file_size=100, uploaded_at="2026-11-10T12:00:00Z")
        original = copy.deepcopy(self.stage)
        altered = copy.deepcopy(original)
        altered["documents"][0]["storage_key"] = "replacement-sha"
        with self.assertRaisesRegex(cr.RecordIntegrityError, "document evidence"):
            cr.guard_no_silent_deletion(original, altered)
        altered = copy.deepcopy(original)
        altered["documents"][0]["tenancy_id"] = self.stage["tenancies"][1]["id"]
        with self.assertRaisesRegex(cr.RecordIntegrityError, "audited review"):
            cr.guard_no_silent_deletion(original, altered)

    def test_canonical_approval_needs_actual_decision_date(self):
        self.stage["approvals"] = [{
            "id": "approval-100", "model_version": 1,
            "property_id": self.stage["properties"][0]["id"],
            "job_id": self.job["id"], "status": "approved",
        }]
        with self.assertRaisesRegex(cr.RecordIntegrityError, "decision timestamp"):
            cr.validate_for_save(self.stage)

    def test_audit_log_cannot_be_replaced_in_a_new_snapshot(self):
        self.stage["audit_log"] = [{"action": "approval_created", "target": "appr-1"}]
        original = copy.deepcopy(self.stage)
        altered = copy.deepcopy(original)
        altered["audit_log"] = []
        with self.assertRaisesRegex(cr.RecordIntegrityError, "agency audit"):
            cr.guard_no_silent_deletion(original, altered)
        altered = copy.deepcopy(original)
        altered["audit_log"].append({"action": "invoice_recorded"})
        cr.guard_no_silent_deletion(original, altered)


if __name__ == "__main__":
    unittest.main()
