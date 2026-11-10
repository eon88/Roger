"""B01 reconciliation never merges identities or makes unreviewed link edits."""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "stage-clone"))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))
import canonical_records as cr
import legacy_reconciliation as review
from v1_two_agency_data import build


class ReviewedCanonicalTests(unittest.TestCase):
    def setUp(self):
        self.stage = build("oaklettings")
        self.p1, self.p2 = (p["id"] for p in self.stage["properties"])
        self.job = self.stage["jobs"][0]
        self.at = "2026-11-10T08:00:00Z"

    def reconcile(self, **kw):
        return review.propose_reviewed_link(
            self.stage, collection="jobs", record_id=self.job["id"],
            field="property_id", target_id=self.p1, actor="office-reviewer",
            at=self.at, reason="Cross-checked the original signed work order",
            **kw)

    def test_clean_two_agency_fixture_has_one_authoritative_source_map(self):
        original = copy.deepcopy(self.stage)
        result = review.reconciliation_report(self.stage)
        self.assertTrue(result["ready_for_canonical_linking"])
        self.assertEqual(result["authoritative"]["supplier_invoice"], "jobs")
        self.assertEqual(result["authoritative"]["person"], "parties")
        self.assertEqual(self.stage, original)

    def test_legacy_cross_property_job_requires_explicit_review(self):
        self.job["property_id"] = self.p2
        original = copy.deepcopy(self.stage)
        self.assertFalse(review.reconciliation_report(self.stage)["ready_for_canonical_linking"])
        proposal, event = self.reconcile()
        self.assertEqual(self.stage, original)
        self.assertEqual(event["from"], self.p2)
        self.assertEqual(proposal["jobs"][0]["property_id"], self.p1)
        self.assertEqual(proposal["jobs"][0]["reconciliation_history"][-1]["actor"], "office-reviewer")
        self.assertEqual(proposal["audit_log"][-1]["action"], "reviewed_link_reconciled")
        self.assertTrue(review.reconciliation_report(proposal)["ready_for_canonical_linking"])

    def test_reconciliation_rejects_foreign_agency_parent(self):
        self.job["property_id"] = self.p2
        self.stage["properties"][0]["agency_id"] = "birchlettings"
        original = copy.deepcopy(self.stage)
        with self.assertRaisesRegex(cr.RecordIntegrityError, "crosses agency"):
            self.reconcile()
        self.assertEqual(self.stage, original)

    def test_reconciliation_cannot_introduce_new_wrong_property(self):
        original = copy.deepcopy(self.stage)
        with self.assertRaises(cr.RecordIntegrityError):
            review.propose_reviewed_link(
                self.stage, collection="jobs", record_id=self.job["id"],
                field="case_id", target_id="absent", actor="office",
                at=self.at, reason="Checked original repair contract")
        self.assertEqual(self.stage, original)

    def test_review_must_have_actor_reason_time_and_real_target(self):
        self.job["property_id"] = self.p2
        with self.assertRaisesRegex(cr.RecordIntegrityError, "named reviewer"):
            review.propose_reviewed_link(
                self.stage, collection="jobs", record_id=self.job["id"],
                field="property_id", target_id=self.p1, actor="",
                at=self.at, reason="meaningful reason from records")
        with self.assertRaisesRegex(cr.RecordIntegrityError, "timestamp"):
            review.propose_reviewed_link(
                self.stage, collection="jobs", record_id=self.job["id"],
                field="property_id", target_id=self.p1, actor="office",
                at="2026-11-10", reason="Signed mandate checked and reviewed")

    def test_duplicate_supplier_invoice_detected_without_moving_money(self):
        second = copy.deepcopy(self.job)
        second["id"] = "job-other"
        self.job["assigned_to_party_id"] = second["assigned_to_party_id"] = "contractor-1"
        self.job["invoice_number"] = second["invoice_number"] = "INV-123"
        self.stage["jobs"].append(second)
        original = copy.deepcopy(self.stage)
        issues = review.reconciliation_report(self.stage)["issues"]
        collisions = [i for i in issues if i["issue"] == "duplicate_supplier_invoice"]
        self.assertEqual({i["id"] for i in collisions}, {self.job["id"], second["id"]})
        self.assertEqual(self.stage, original)

    def test_shadow_invoice_conflict_and_orphan_doc_pointer_are_visible(self):
        self.job["invoice_pence"] = 500
        self.job["document_ids"] = ["missing-attachment", "missing-attachment"]
        issues = review.reconciliation_report(self.stage)["issues"]
        types = {i["issue"] for i in issues}
        self.assertIn("shadow_invoice_amount_conflict", types)
        self.assertIn("orphan_document_pointer", types)
        self.assertIn("duplicate_document_pointer", types)

    def test_reviewed_document_property_repair_preserves_versions_and_audit(self):
        doc = self.stage["documents"][0]
        doc.update(model_version=1, property_id=self.p2,
                   storage_key="original-evidence-sha")
        original = copy.deepcopy(self.stage)
        proposal, event = review.propose_reviewed_link(
            original, collection="documents", record_id=doc["id"],
            field="property_id", target_id=self.p1, actor="office-reviewer",
            at=self.at, reason="Matched original tenancy document and property ID")
        self.assertEqual(event["from"], self.p2)
        self.assertEqual(proposal["documents"][0]["storage_key"], "original-evidence-sha")
        self.assertEqual(proposal["documents"][0]["property_id"], self.p1)
        self.assertTrue(review.reconciliation_report(proposal)["ready_for_canonical_linking"])
        cr.guard_no_silent_deletion(original, proposal)
        self.assertEqual(self.stage, original)

    def test_no_reconciliation_using_matching_email(self):
        self.stage["parties"][0]["email"] = self.stage["parties"][1]["email"]
        self.assertTrue(review.reconciliation_report(self.stage)["ready_for_canonical_linking"])


if __name__ == "__main__":
    unittest.main()
