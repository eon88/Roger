"""Tests for staged matched PostgreSQL/document-file backup verification."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops" / "saas" / "backup_and_restore_oak_files.py"
spec = importlib.util.spec_from_file_location("backup_and_restore_oak_files", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StagingFileBackupTests(unittest.TestCase):
    def create_file(self, folder, body=None):
        body = module.DOC_BODY if body is None else body
        key = hashlib.sha256(body).hexdigest()
        p = Path(folder) / key[:2] / key
        p.parent.mkdir(exist_ok=True)
        p.write_bytes(body)
        return p

    def test_valid_content_addressed_fixture(self):
        with tempfile.TemporaryDirectory() as temp:
            file = self.create_file(temp)
            manifest = module.file_manifest(Path(temp))
            self.assertEqual(manifest, {file.relative_to(temp).as_posix(): module.DOC_HASH})

    def test_corrupted_file_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            file = self.create_file(temp)
            file.write_bytes(b"corrupted")
            with self.assertRaisesRegex(ValueError, "corrupted"):
                module.file_manifest(Path(temp))

    def test_symlink_file_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            file = self.create_file(temp)
            (file.parent / ("0" * 64)).symlink_to(file)
            with self.assertRaisesRegex(ValueError, "symlink"):
                module.file_manifest(Path(temp))

    def test_unexpected_file_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / ".env").write_text("do not back up secrets")
            with self.assertRaisesRegex(ValueError, "unexpected storage path"):
                module.file_manifest(Path(temp))

    def test_wrong_agency_refused(self):
        with patch.object(module, "safe_run", return_value=b'{"agency_id":"roger","documents":[]}'):
            with self.assertRaisesRegex(ValueError, "not the Oak"):
                module.synthetic_document_metadata()

    def test_matching_synthetic_document_record(self):
        import json
        stage = {"agency_id": "stg-oak", "documents": [{
            "title": module.DOC_TITLE, "storage_key": module.DOC_HASH,
            "file_size": len(module.DOC_BODY), "id": "doc-1"}]}
        with patch.object(module, "safe_run", return_value=json.dumps(stage).encode()):
            self.assertEqual(module.synthetic_document_metadata()["id"], "doc-1")

    def test_reject_metadata_mismatch(self):
        import json
        stage = {"agency_id": "stg-oak", "documents": [{
            "title": module.DOC_TITLE, "storage_key": "0" * 64,
            "file_size": 5}]}
        with patch.object(module, "safe_run", return_value=json.dumps(stage).encode()):
            with self.assertRaisesRegex(ValueError, "does not match"):
                module.synthetic_document_metadata()

    def test_restored_files_match_independent_manifest(self):
        import json
        with tempfile.TemporaryDirectory() as base:
            backup = Path(base) / "backup-oak-test"
            files = backup / "files"
            files.mkdir(parents=True)
            file = self.create_file(files)
            manifest = module.file_manifest(files)
            with patch.object(module.database_restore, "checked_backup", return_value=backup / "oak-postgres.dump"), \
                 patch.object(module.database_restore, "restore") as restore, \
                 patch.object(module.database_restore, "rows", return_value="stg-oak|hash"), \
                 patch.object(module, "ROOT", Path(base)):
                module.restore_and_compare(backup, manifest)
                restore.assert_called_once()
            self.assertFalse(list(Path(base).glob("roger-stg-files-restore-*")))


if __name__ == "__main__":
    unittest.main()
