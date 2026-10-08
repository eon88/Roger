"""Tests for atomic JSON snapshot writes."""
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


class AtomicStorageTests(unittest.TestCase):
    def test_atomic_write_roundtrips_and_restricts_file_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stage.json"
            expected = {"cases": [{"id": 1}]}
            serve.atomic_json_write(str(path), expected)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), expected)
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["stage.json"])


if __name__ == "__main__":
    unittest.main()
