"""Tests for Roger's offline backup utility."""
from pathlib import Path
import sys
import tempfile
import tarfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backup_roger_data import create_backup


class BackupTests(unittest.TestCase):
    def test_backup_validates_archives_json_and_restricts_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "live"
            destination = root / "backups"
            source.mkdir()
            (source / "stage.json").write_text('{"properties": []}', encoding="utf-8")
            (source / "users.json").write_text('{"users": []}', encoding="utf-8")
            files = root / "document-files"
            (files / "ab").mkdir(parents=True)
            (files / "ab" / "certificate").write_bytes(b"private file body")
            archive_path, checksum_path = create_backup(source, destination, files_dir=files)
            self.assertTrue(archive_path.is_file())
            self.assertEqual(archive_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(checksum_path.stat().st_mode & 0o777, 0o600)
            with tarfile.open(archive_path, "r:gz") as archive:
                self.assertEqual(set(archive.getnames()), {"stage.json", "users.json", "files", "files/ab", "files/ab/certificate"})
                self.assertEqual(archive.extractfile("files/ab/certificate").read(), b"private file body")
            self.assertEqual(len(checksum_path.read_text(encoding="utf-8").split()[0]), 64)

    def test_backup_rejects_destination_inside_live_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "live"
            source.mkdir()
            (source / "stage.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                create_backup(source, source / "backup")


if __name__ == "__main__":
    unittest.main()
