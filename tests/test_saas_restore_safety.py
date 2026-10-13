"""Safety tests for the one-command disposable Oak backup restore check."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "ops" / "saas" / "verify_oak_restore.py"
spec = importlib.util.spec_from_file_location("verify_oak_restore", FILE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class OakRestoreSafetyTests(unittest.TestCase):
    def create_backup(self, root, text=b"synthetic PG dump"):
        backup = root / "backup-oak-T3st42"
        backup.mkdir()
        dump = backup / "oak-postgres.dump"
        dump.write_bytes(text)
        (backup / "oak-postgres.dump.sha256").write_text(
            hashlib.sha256(text).hexdigest() + "  " + str(dump) + "\n")
        return backup

    def test_valid_backup_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            backup = self.create_backup(root)
            with patch.object(mod, "BACKUP_ROOT", root):
                self.assertEqual(mod.checked_backup(str(backup)),
                                 backup / "oak-postgres.dump")

    def test_corrupt_dump_is_rejected_before_docker(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            backup = self.create_backup(root)
            (backup / "oak-postgres.dump").write_bytes(b"changed")
            with patch.object(mod, "BACKUP_ROOT", root):
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    mod.checked_backup(str(backup))

    def test_backup_outside_staging_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            allowed = root / "allowed"
            allowed.mkdir()
            backup = self.create_backup(root)
            with patch.object(mod, "BACKUP_ROOT", allowed):
                with self.assertRaisesRegex(ValueError, "only an Oak backup"):
                    mod.checked_backup(str(backup))

    def test_below_memory_minimum_never_runs_docker(self):
        with patch.object(mod, "read_available_memory", return_value=int(1.3 * mod.GIB)), \
             patch.object(mod, "call") as docker:
            with self.assertRaisesRegex(ValueError, "RAM"):
                mod.preflight()
            docker.assert_not_called()

    def test_existing_restore_container_blocks_start(self):
        with patch.object(mod, "read_available_memory", return_value=2 * mod.GIB), \
             patch.object(mod.os, "getloadavg", return_value=(0.02, 0.02, 0.02)), \
             patch.object(mod.os, "cpu_count", return_value=1), \
             patch.object(mod, "call", return_value=mod.RESTORE + "\n"):
            with self.assertRaisesRegex(ValueError, "already exists"):
                mod.preflight()


if __name__ == "__main__":
    unittest.main()
