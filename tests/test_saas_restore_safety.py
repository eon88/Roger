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

    def test_restore_diagnostic_excludes_sql_and_passwords(self):
        from subprocess import CalledProcessError
        stderr = (
            b"pg_restore: error: could not execute query: ERROR: relation xyz exists\\n"
            b"Command was: INSERT INTO users VALUES ('sensitive-token');\\n"
            b"DETAIL: private@example.com\\n"
        )
        err = CalledProcessError(1, ["docker", "exec", "-e", "POSTGRES_PASSWORD=SECRET"], stderr=stderr)
        diagnostic = mod.safe_restore_failure(err)
        self.assertIn("pg_restore: error:", diagnostic)
        self.assertNotIn("sensitive-token", diagnostic)
        self.assertNotIn("private@example.com", diagnostic)
        self.assertNotIn("SECRET", diagnostic)

    def test_database_readiness_checks_the_actual_roger_database(self):
        from subprocess import CompletedProcess
        not_ready = CompletedProcess(args=[], returncode=2, stdout="")
        ready = CompletedProcess(args=[], returncode=0, stdout="1\n")
        with patch.object(mod.subprocess, "run", side_effect=[not_ready, ready]) as run:
            self.assertFalse(mod.restored_database_ready())
            self.assertTrue(mod.restored_database_ready())
        self.assertEqual(run.call_count, 2)
        argv = run.call_args.args[0]
        self.assertEqual(argv[:4], ["docker", "exec", mod.RESTORE, "psql"])
        self.assertIn("roger", argv)
        self.assertEqual(argv[-2:], ["-c", "SELECT 1"])
        self.assertNotIn("pg_isready", argv)

    def test_pg_isready_alone_is_never_treated_as_database_ready(self):
        from subprocess import CompletedProcess
        result = CompletedProcess(args=[], returncode=0, stdout="")
        with patch.object(mod.subprocess, "run", return_value=result):
            self.assertFalse(mod.restored_database_ready())

    def test_existing_restore_container_blocks_start(self):
        with patch.object(mod, "read_available_memory", return_value=2 * mod.GIB), \
             patch.object(mod.os, "getloadavg", return_value=(0.02, 0.02, 0.02)), \
             patch.object(mod.os, "cpu_count", return_value=1), \
             patch.object(mod, "call", return_value=mod.RESTORE + "\n"):
            with self.assertRaisesRegex(ValueError, "already exists"):
                mod.preflight()


if __name__ == "__main__":
    unittest.main()
