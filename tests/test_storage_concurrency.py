"""Task 06: cooperative multi-process write locking and fail-closed agency boundaries.

Never contacts the deployed Hostinger server or a live PostgreSQL instance.
"""
import contextlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


def _locked_file_writer(directory, times):
    """Separate *OS process*, not merely a thread."""
    serve.DATA_DIR = directory
    serve.STAGE_FILE = os.path.join(directory, "stage.json")
    for _ in range(times):
        with serve.storage_write_lock():
            stage = serve.load_stage()
            old = stage["counter"]
            time.sleep(0.002)  # make a load/write race probable without the lock
            stage["counter"] = old + 1
            serve.save_stage(stage)


class TransactionAndAgencyTests(unittest.TestCase):
    def test_two_distinct_processes_cannot_overwrite_each_others_edits(self):
        if os.name != "posix":
            self.skipTest("Linux/Unix cross-process lock integration test")
        with tempfile.TemporaryDirectory() as root:
            (Path(root)/"stage.json").write_text(json.dumps({"counter":0}))
            ctx = multiprocessing.get_context("fork")
            workers = [ctx.Process(target=_locked_file_writer, args=(root,25))
                       for _ in range(4)]
            with patch.dict(os.environ, {"ROGER_STORAGE_BACKEND":"file"}):
                for worker in workers:
                    worker.start()
                for worker in workers:
                    worker.join(timeout=15)
                for worker in workers:
                    if worker.is_alive():
                        worker.terminate()
                        worker.join()
                    self.assertEqual(worker.exitcode,0,"writer process failed or deadlocked")
            stage=json.loads((Path(root)/"stage.json").read_text())
            self.assertEqual(stage["counter"],100)
            self.assertTrue((Path(root)/".roger-write.lock").is_file())

    def test_postgres_advisory_lock_covers_full_mutating_operation(self):
        queries=[]
        class Conn:
            def execute(self, sql, params):
                queries.append((sql, params))
            def __enter__(self):
                queries.append(("enter",None))
                return self
            def __exit__(self,*args):
                queries.append(("exit",None))
        with patch.dict(os.environ, {"ROGER_STORAGE_BACKEND":"postgres"}), \
             patch.object(serve,"postgres_connection",return_value=Conn()):
            with serve.storage_write_lock():
                self.assertTrue(any("pg_advisory_xact_lock" in q[0] for q in queries))
                self.assertNotIn(("exit",None),queries)
            self.assertEqual(queries[-1],("exit",None))

    def test_bogus_backend_refuses_unlocked_write(self):
        with patch.dict(os.environ, {"ROGER_STORAGE_BACKEND":"invalid"}):
            with self.assertRaisesRegex(RuntimeError,"unsupported"):
                with serve.storage_write_lock():
                    self.fail("unsafe mutation was allowed")

    def test_expired_get_session_rejected_without_mutating_user_store(self):
        h=serve.H.__new__(serve.H)
        h.parse_cookies=lambda:{"stage_session":"expired"}
        users={"users":[{"username":"tenant","role":"tenant"}],
               "sessions":{"expired":{"username":"tenant","exp":"2020-01-01T00:00:00+00:00"}}}
        with patch.object(serve,"load_users",return_value=users), \
             patch.object(serve,"save_users") as write:
            self.assertIsNone(h.session_user())
            write.assert_not_called()
            self.assertIn("expired",users["sessions"])

    def test_single_agency_snapshot_rejects_mixed_or_untagged_records(self):
        tagged={"agency_id":"agency-one","properties":[{"id":"property-1","agency_id":"agency-one"}],
                "cases":[{"id":"case-1","agency_id":"agency-one"}]}
        self.assertIs(serve.require_single_agency(tagged),tagged)
        with self.assertRaises(serve.AgencyBoundaryError):
            serve.require_single_agency({
                **tagged,"cases":[{"id":"case-2","agency_id":"agency-two"}]})
        with self.assertRaises(serve.AgencyBoundaryError):
            serve.require_single_agency({
                **tagged,"properties":[{"id":"property-1"}]})
        with self.assertRaises(serve.AgencyBoundaryError):
            serve.require_single_agency({
                "properties":[{"id":"property-1","agency_id":"agency-two"}]})
        with patch.dict(os.environ,{"ROGER_AGENCY_ID":"agency-two"}):
            with self.assertRaises(serve.AgencyBoundaryError):
                serve.require_single_agency(tagged)

    def test_explicitly_mixed_agency_read_returns_error_instead_of_agent_data(self):
        h=serve.H.__new__(serve.H)
        h.path="/api/stage"
        h.session_user=lambda:{"username":"agent","role":"agent","display_name":"Agent"}
        h.require=lambda roles=None:h.session_user()
        answers=[]
        h._json=lambda data,status=200:answers.append((data,status))
        mixed={"agency_id":"agency-one",
               "cases":[{"id":"foreign-case","agency_id":"agency-two","message":"private"}]}
        with patch.object(serve,"load_stage",side_effect=lambda:serve.require_single_agency(mixed)):
            h.do_GET()
        self.assertEqual(answers[-1][1],409)
        self.assertNotIn("private",json.dumps(answers))


class TwoTenancyIsolationTests(unittest.TestCase):
    def setUp(self):
        self.stage={
            "properties":[
                {"id":"home-A","tenant_party_id":"party-A","landlord_party_id":"owner-A","title":"A"},
                {"id":"home-B","tenant_party_id":"party-B","landlord_party_id":"owner-B","title":"B"},
            ],
            "parties":[
                {"id":"party-A","roles":["tenant"],"account_id":"account-A","status":"active"},
                {"id":"party-B","roles":["tenant"],"account_id":"account-B","status":"active"},
                {"id":"owner-A","roles":["landlord"],"account_id":"landlord-A","status":"active"},
                {"id":"owner-B","roles":["landlord"],"account_id":"landlord-B","status":"active"},
            ],
            "cases":[
                {"id":1,"tenant_party_id":"party-A","property_id":"home-A","message":"Only A",
                 "internal_notes":[{"text":"office private A"}],"thread":[]},
                {"id":2,"tenant_party_id":"party-B","property_id":"home-B","message":"Only B",
                 "internal_notes":[{"text":"office private B"}],"thread":[]},
            ],
            "jobs":[
                {"id":"job-A","case_id":1,"property_id":"home-A","status":"in_progress"},
                {"id":"job-B","case_id":2,"property_id":"home-B","status":"in_progress"},
            ],
            "documents":[
                {"id":"doc-A","case_id":1,"property_id":"home-A","access_roles":["tenant","landlord"],
                 "document_type":"maintenance_evidence"},
                {"id":"doc-B","case_id":2,"property_id":"home-B","access_roles":["tenant","landlord"],
                 "document_type":"maintenance_evidence"},
            ]
        }
        self.users={
            "A":{"role":"tenant","account_id":"account-A","display_name":"Tenant A"},
            "B":{"role":"tenant","account_id":"account-B","display_name":"Tenant B"},
            "owner-A":{"role":"landlord","account_id":"landlord-A","display_name":"Owner A"},
            "owner-B":{"role":"landlord","account_id":"landlord-B","display_name":"Owner B"},
        }
        self.h=serve.H.__new__(serve.H)
        self.responses=[]
        self.h._json=lambda data,status=200:self.responses.append((data,status))
        self.current=self.users["A"]
        self.h.session_user=lambda:self.current
        self.h.require=lambda roles=None:self.current
        self.load=patch.object(serve,"load_stage",return_value=self.stage)
        self.load.start()
        self.addCleanup(self.load.stop)

    def test_each_tenant_and_landlord_sees_only_own_home_case_and_job(self):
        for label in ("A","B","owner-A","owner-B"):
            self.current=self.users[label]
            self.h.serve_scoped_stage()
            payload,status=self.responses[-1]
            self.assertEqual(status,200)
            owner="A" if label.endswith("A") else "B"
            foreign="B" if owner=="A" else "A"
            data=json.dumps(payload)
            self.assertIn("home-"+owner,data)
            self.assertNotIn("home-"+foreign,data)
            self.assertNotIn("job-"+foreign,data)
            self.assertNotIn("office private",data)

    def test_cross_home_document_read_denied_even_when_forged_with_another_doc_id(self):
        for label in ("A","B","owner-A","owner-B"):
            self.current=self.users[label]
            owned="A" if label.endswith("A") else "B"
            foreign="B" if owned=="A" else "A"
            docs=self.h.scoped_documents(self.current)
            self.assertEqual({d["id"] for d in docs},{"doc-"+owned})
            self.assertFalse(self.h.can_view_document(self.current,
                next(d for d in self.stage["documents"] if d["id"]=="doc-"+foreign)))
            self.h.path="/api/document/doc-"+foreign+"/file"
            sent=[]
            self.h.serve_document_file=lambda doc:sent.append(doc["id"])
            self.h.do_GET()
            self.assertEqual(self.responses[-1][1],403)
            self.assertEqual(sent,[])

    def test_relinked_tenant_loses_access_to_old_case_and_document(self):
        self.current=self.users["A"]
        self.stage["parties"][0]["status"]="revoked"
        self.h.serve_scoped_stage()
        result,status=self.responses[-1]
        self.assertEqual(status,200)
        self.assertEqual(result["properties"],[])
        self.assertEqual(result["cases"],[])
        self.assertEqual(self.h.scoped_documents(self.current),[])


if __name__=="__main__":
    unittest.main()
