"""B01 canonical schema migration: preview, apply, checksum and rollback."""
from pathlib import Path
import importlib.util
import json
import os
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tests"/"fixtures"))
from v1_two_agency_data import build
spec=importlib.util.spec_from_file_location("upgrade_canonical_v1",
                                        ROOT/"ops"/"migration"/"upgrade_canonical_v1.py")
migration=importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class OfflineSchemaUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.work=tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.directory=Path(self.work.name)
        self.file=self.directory/"stage.json"
        self.before=json.dumps(build("oaklettings"),separators=(",",":")).encode()
        self.file.write_bytes(self.before)

    def test_dry_run_and_preview_never_mutate_snapshot(self):
        result=migration.run(self.directory)
        self.assertFalse(result["changed"])
        self.assertEqual(result["action"],"upgrade_preview")
        self.assertEqual(result["legacy_link_warnings"],[])
        self.assertEqual(self.file.read_bytes(),self.before)
        self.assertFalse((self.directory/"backups").exists())

    def test_explicit_offline_apply_and_restore_exact_original_bytes(self):
        with self.assertRaisesRegex(ValueError,"OFFLINE-SCHEMA"):
            migration.run(self.directory,apply=True)
        result=migration.run(self.directory,apply=True,confirm="OFFLINE-SCHEMA",
                             offline=True,environment="security-lab")
        backed_up=Path(result["backup"])
        self.assertEqual(backed_up.read_bytes(),self.before)
        current=json.loads(self.file.read_text())
        self.assertEqual(current["model_metadata"]["version"],1)
        self.assertEqual(current["properties"],json.loads(self.before)["properties"])
        self.assertEqual(current["tenancies"],json.loads(self.before)["tenancies"])
        self.assertEqual(current["ownership_interests"],[])
        rolled=migration.run(self.directory,rollback=backed_up,confirm="OFFLINE-SCHEMA",
                             offline=True,environment="security-lab")
        self.assertTrue(rolled["changed"])
        self.assertEqual(self.file.read_bytes(),self.before)
        self.assertTrue(Path(rolled["emergency_backup"]).exists())

    def test_cross_directory_backup_rollback_refused(self):
        with tempfile.TemporaryDirectory() as other:
            replacement=Path(other)/"before-canonical-v1-unsafe.json"
            replacement.write_bytes(self.before)
            with self.assertRaisesRegex(ValueError,"backup inside"):
                migration.run(self.directory,rollback=replacement,
                              confirm="OFFLINE-SCHEMA",offline=True)
        self.assertEqual(self.file.read_bytes(),self.before)

    def test_live_environment_refused_for_apply_and_rollback(self):
        backup_dir=self.directory/"backups"
        backup_dir.mkdir()
        backup=backup_dir/"before-canonical-v1-protected.json"
        backup.write_bytes(self.before)
        for env in ("production","staging"):
            with self.subTest(env=env):
                with self.assertRaises(ValueError):
                    migration.run(self.directory,apply=True,confirm="OFFLINE-SCHEMA",
                                  offline=True,environment=env)
                with self.assertRaises(ValueError):
                    migration.run(self.directory,rollback=backup,confirm="OFFLINE-SCHEMA",
                                  offline=True,environment=env)
                self.assertEqual(self.file.read_bytes(),self.before)

    def test_unresolved_legacy_reference_blocks_migration_apply(self):
        corrupted=json.loads(self.before)
        corrupted["documents"][0]["property_id"]="not-a-real-property"
        self.file.write_text(json.dumps(corrupted))
        result=migration.run(self.directory)
        self.assertEqual(result["legacy_link_warnings"][0]["collection"],"documents")
        with self.assertRaisesRegex(ValueError,"Unresolved legacy links"):
            migration.run(self.directory,apply=True,confirm="OFFLINE-SCHEMA",
                          offline=True,environment="test")
        self.assertFalse((self.directory/"backups").exists())

    def test_bad_record_id_prevents_even_preview(self):
        contaminated=json.loads(self.before)
        contaminated["properties"].append(contaminated["properties"][0].copy())
        self.file.write_text(json.dumps(contaminated))
        with self.assertRaisesRegex(ValueError,"duplicate ID"):
            migration.run(self.directory)
        self.assertEqual(json.loads(self.file.read_text()),contaminated)


if __name__=="__main__":
    unittest.main()
