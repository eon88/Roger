"""B01: report historical link conflicts without guessing or merging records."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "stage-clone"))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))
import canonical_records as cr
from v1_two_agency_data import build


class HistoricalLinkTests(unittest.TestCase):
    def setUp(self):
        self.stage = build("oaklettings")
        self.original = copy.deepcopy(self.stage)
        self.p1, self.p2 = (p["id"] for p in self.stage["properties"])

    def test_legacy_parent_property_conflicts_are_reported_not_rewritten(self):
        self.stage["jobs"][0]["property_id"] = self.p2
        self.stage["documents"][0]["property_id"] = self.p2
        self.stage["deposit_records"][0]["property_id"] = self.p2
        self.stage["rent_ledger_entries"][0]["property_id"] = self.p2
        report = cr.inspect(self.stage)
        affected = {(w["collection"], w["field"], w["issue"])
                    for w in report["warnings"]}
        for expected in (
            ("jobs", "case_id", "property_mismatch"),
            ("documents", "tenancy_id", "property_mismatch"),
            ("deposit_records", "tenancy_id", "property_mismatch"),
            ("rent_ledger_entries", "tenancy_id", "property_mismatch"),
        ):
            self.assertIn(expected, affected)
        upgraded, _ = cr.propose_upgrade(self.stage)
        self.assertEqual(upgraded["jobs"], self.stage["jobs"])
        self.assertEqual(upgraded["documents"], self.stage["documents"])
        self.assertEqual(upgraded["deposit_records"], self.stage["deposit_records"])
        self.assertEqual(upgraded["rent_ledger_entries"], self.stage["rent_ledger_entries"])
        self.assertEqual(self.original["properties"], self.stage["properties"])

    def test_new_job_cannot_link_another_property_case(self):
        self.stage["jobs"][0]["property_id"] = self.p2
        self.stage["jobs"][0]["model_version"] = 1
        with self.assertRaisesRegex(cr.RecordIntegrityError, "property_mismatch"):
            cr.validate_for_save(self.stage)

    def test_document_job_and_case_relationship_must_agree(self):
        other_case = copy.deepcopy(self.stage["cases"][0])
        other_case["id"] = "other-repair"
        self.stage["cases"].append(other_case)
        document = self.stage["documents"][0]
        document["job_id"] = self.stage["jobs"][0]["id"]
        document["case_id"] = other_case["id"]
        self.assertTrue(any(w["issue"] == "job_case_mismatch"
                            for w in cr.inspect(self.stage)["warnings"]))
        document["model_version"] = 1
        with self.assertRaisesRegex(cr.RecordIntegrityError, "job_case_mismatch"):
            cr.validate_for_save(self.stage)

    def test_foreign_parent_agency_warns_legacy_and_blocks_new(self):
        self.stage["cases"][0]["agency_id"] = "birchlettings"
        warning_types = {w["issue"] for w in cr.inspect(self.stage)["warnings"]}
        self.assertIn("foreign_agency_reference", warning_types)
        self.stage["jobs"][0]["model_version"] = 1
        with self.assertRaisesRegex(cr.RecordIntegrityError, "foreign_agency_reference"):
            cr.validate_for_save(self.stage)

    def test_source_id_collision_requires_review_not_name_matching(self):
        for row in self.stage["parties"][:2]:
            row["source_system"] = "external-crm"
            row["source_id"] = "source-row-101"
        report = cr.inspect(self.stage)
        self.assertTrue(any(w["issue"] == "duplicate_external_identity"
                            for w in report["warnings"]))
        self.stage["parties"][1]["model_version"] = 1
        with self.assertRaisesRegex(cr.RecordIntegrityError, "duplicate_external_identity"):
            cr.validate_for_save(self.stage)

    def test_no_false_deduplication_by_shared_names_or_contact_details(self):
        for row in self.stage["parties"][:2]:
            row["display_name"] = "Alex"
            row["email"] = "same@example.invalid"
        self.assertEqual(cr.inspect(self.stage)["warnings"], [])


    def test_older_duplicate_of_canonical_external_identity_also_blocks(self):
        first, second = self.stage["parties"][:2]
        first["model_version"] = 1
        first["source_system"] = second["source_system"] = "legacy-import"
        first["source_id"] = second["source_id"] = "same-verified-source"
        with self.assertRaisesRegex(cr.RecordIntegrityError, "duplicate_external_identity"):
            cr.validate_for_save(self.stage)

    def test_orphan_approval_and_document_supersession_are_reported(self):
        self.stage["approvals"] = [{
            "id": "approval-old", "property_id": self.p1,
            "job_id": "missing-job"
        }]
        self.stage["documents"][0]["supersedes_id"] = "missing-original"
        warnings = cr.inspect(self.stage)["warnings"]
        self.assertTrue(any(w["collection"] == "approvals"
                            and w["issue"] == "missing_related_jobs" for w in warnings))
        self.assertTrue(any(w["collection"] == "documents"
                            and w["issue"] == "missing_related_documents" for w in warnings))
        self.stage["approvals"][0]["model_version"] = 1
        with self.assertRaisesRegex(cr.RecordIntegrityError, "missing jobs"):
            cr.validate_for_save(self.stage)

    def test_appointment_with_foreign_property_case_is_blocked_when_versioned(self):
        self.stage["appointments"] = [{
            "id": "visit-1", "property_id": self.p2,
            "case_id": self.stage["cases"][0]["id"],
            "model_version": 1
        }]
        with self.assertRaisesRegex(cr.RecordIntegrityError, "property_mismatch"):
            cr.validate_for_save(self.stage)


if __name__ == "__main__":
    unittest.main()
