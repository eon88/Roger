"""Tests for PostgreSQL migration source validation."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import migrate_json_to_postgres as migration


class PostgresMigrationTests(unittest.TestCase):
    def test_source_validation_preserves_counts_and_warns_on_unlinked_legacy_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "stage.json").write_text(json.dumps({
                "properties": [{"id": "home-1"}],
                "parties": [],
                "tenancies": [{"id": "tenancy-1", "property_id": "missing-property",
                               "tenant_party_ids": ["legacy-person"]}],
            }), encoding="utf-8")
            (root / "users.json").write_text('{"users": []}', encoding="utf-8")
            stage, users, counts, warnings = migration.check_source(root)
            self.assertEqual(counts["properties"], 1)
            self.assertEqual(counts["tenancies"], 1)
            self.assertEqual(users, {"users": []})
            self.assertEqual(len(warnings), 2)

    def test_source_validation_rejects_duplicate_ids(self):
        with self.assertRaisesRegex(ValueError, "duplicate ID"):
            migration.validate_stage({"properties": [{"id": "x"}, {"id": "x"}]})


if __name__ == "__main__":
    unittest.main()
