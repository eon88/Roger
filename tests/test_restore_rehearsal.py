"""Task 05 disposable restore rehearsal: integrity, missing evidence and source immutability."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rehearse_restore import rehearsal


class RestoreRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        payload = b"synthetic pdf evidence, not a real client file"
        self.key = hashlib.sha256(payload).hexdigest()
        target = self.root / "files" / self.key[:2] / self.key
        target.parent.mkdir(parents=True)
        target.write_bytes(payload)
        self.original = payload
        (self.root / "stage.json").write_text(json.dumps({
            "cases":[{"id":42,"message":"synthetic report"}],
            "documents":[{"id":"doc-1","storage_key":self.key}],
        }))
        (self.root / "users.json").write_text(json.dumps({
            "users":[{"username":"synthetic"}],"sessions":{},
        }))

    def test_disposable_rehearsal_restores_snapshots_and_document_hashes(self):
        result = rehearsal(self.root)
        self.assertTrue(result["ok"])
        self.assertEqual(result["file_count"],3)
        self.assertEqual(result["documents_checked"],1)
        self.assertEqual(result["cases_count"],1)
        self.assertEqual((self.root/"files"/self.key[:2]/self.key).read_bytes(),self.original)

    def test_missing_file_and_checksum_error_are_rejected(self):
        file = self.root/"files"/self.key[:2]/self.key
        file.write_bytes(b"damaged")
        with self.assertRaisesRegex(ValueError,"damaged"):
            rehearsal(self.root)
        file.unlink()
        with self.assertRaisesRegex(ValueError,"missing"):
            rehearsal(self.root)

    def test_missing_user_snapshot_refuses_to_claim_recovery(self):
        (self.root/"users.json").unlink()
        with self.assertRaisesRegex(ValueError,"required file"):
            rehearsal(self.root)


if __name__=="__main__":
    unittest.main()
