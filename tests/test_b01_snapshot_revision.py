"""B01 stale-write and compare-and-swap snapshot regression tests."""
from pathlib import Path
import copy
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"stage-clone"))
import serve


class SnapshotRevisionTests(unittest.TestCase):
    def test_two_stale_file_writers_cannot_silently_replace_each_other(self):
        with tempfile.TemporaryDirectory() as root:
            file=Path(root)/"stage.json"
            file.write_text(json.dumps({"counter":0,"properties":[]}))
            with patch.object(serve,"STAGE_FILE",str(file)),\
                 patch.dict(os.environ,{"ROGER_STORAGE_BACKEND":"file",
                                        "ROGER_SAAS_MODE":"0"}):
                first=serve.load_stage()
                stale=serve.load_stage()
                first["counter"]=1
                with serve.storage_write_lock():
                    serve.save_stage(first)
                self.assertEqual(first["_stage_revision"],1)
                stale["counter"]=999
                with serve.storage_write_lock():
                    with self.assertRaisesRegex(serve.StaleStageWrite,"stale"):
                        serve.save_stage(stale)
                latest=serve.load_stage()
                self.assertEqual(latest["counter"],1)
                self.assertEqual(latest["_stage_revision"],1)
                latest["counter"]=2
                with serve.storage_write_lock():
                    serve.save_stage(latest)
                self.assertEqual(serve.load_stage()["_stage_revision"],2)
                self.assertEqual(serve.load_stage()["counter"],2)

    def test_duplicate_records_rejected_without_increment_or_file_mutation(self):
        with tempfile.TemporaryDirectory() as root:
            file=Path(root)/"stage.json"
            original={"properties":[{"id":"home-1"}]}
            file.write_text(json.dumps(original))
            with patch.object(serve,"STAGE_FILE",str(file)),\
                 patch.dict(os.environ,{"ROGER_STORAGE_BACKEND":"file",
                                        "ROGER_SAAS_MODE":"0"}):
                invalid=copy.deepcopy(original)
                invalid["properties"].append({"id":"home-1"})
                with self.assertRaises(serve.RecordIntegrityError):
                    serve.save_stage(invalid)
            self.assertEqual(json.loads(file.read_text()),original)

    def test_invalid_revision_refused_without_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            file=Path(root)/"stage.json"
            file.write_text(json.dumps({"properties":[]}))
            with patch.object(serve,"STAGE_FILE",str(file)),\
                 patch.dict(os.environ,{"ROGER_STORAGE_BACKEND":"file"}):
                for revision in (-1,True,"1"):
                    with self.subTest(revision=revision),self.assertRaises(serve.RecordIntegrityError):
                        serve.save_stage({"properties":[],"_stage_revision":revision})
            self.assertEqual(json.loads(file.read_text()),{"properties":[]})


if __name__=="__main__":
    unittest.main()
