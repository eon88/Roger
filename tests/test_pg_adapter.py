"""Integration checks for Roger's opt-in PostgreSQL adapter."""
import importlib.util
import os
import pathlib
import unittest
import uuid

try:
    import psycopg
except ImportError:
    psycopg = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("roger_pg", ROOT / "stage-clone" / "roger_pg.py")
pg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pg)

class StorageConfigurationTests(unittest.TestCase):
    def test_json_remains_default(self):
        from unittest.mock import patch
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(pg.enabled())
    def test_bad_collection_rejected(self):
        with self.assertRaises(ValueError):
            pg.list_records(None, "app_users")
    def test_invalid_agency_rejected_before_connect(self):
        with self.assertRaises(ValueError):
            with pg.agency_transaction("not-a-url", "not-a-uuid"):
                pass

@unittest.skipUnless(psycopg and os.environ.get("TEST_DATABASE_URL"), "Requires disposable PostgreSQL")
class PostgresAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["TEST_DATABASE_URL"]
        cls.a, cls.b = uuid.uuid4(), uuid.uuid4()
        cls.user = uuid.uuid4()
        with psycopg.connect(cls.url) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO agencies(id,name,slug) VALUES (%s,'Adapter A',%s),(%s,'Adapter B',%s)",
                            (cls.a, "adapter-a-" + cls.a.hex[:8], cls.b, "adapter-b-" + cls.b.hex[:8]))
                cur.execute("INSERT INTO app_users(id,username,password_hash) VALUES (%s,%s,'test-only')",
                            (cls.user, "test-" + cls.user.hex))
        with pg.agency_transaction(cls.url, cls.a) as cur:
            cur.execute("INSERT INTO agency_memberships(agency_id,user_id,role) VALUES (%s,%s,'agent')",
                        (cls.a, cls.user))
    def test_agency_read_write_isolation(self):
        with pg.agency_transaction(self.url, self.a) as cur:
            self.assertEqual(pg.assert_membership(cur, self.user, self.a), "agent")
            pg.put_record(cur, "properties", self.a, {"id":"same-id", "title":"Agency A", "tenant":"Alice"})
            self.assertTrue(any(x["title"] == "Agency A" for x in pg.list_records(cur,"properties")))
        with pg.agency_transaction(self.url, self.b) as cur:
            self.assertEqual(pg.list_records(cur, "properties"), [])
            with self.assertRaises(PermissionError):
                pg.assert_membership(cur, self.user, self.b)
            pg.put_record(cur, "properties", self.b, {"id":"same-id", "title":"Agency B"})
        with pg.agency_transaction(self.url, self.a) as cur:
            records = pg.list_records(cur,"properties")
            self.assertEqual([r["title"] for r in records], ["Agency A"])
    def test_cross_agency_write_rejected(self):
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with pg.agency_transaction(self.url, self.a) as cur:
                pg.put_record(cur,"properties",self.b,{"id":"intrusion","title":"No"})
    def test_workflow_records_roundtrip(self):
        with pg.agency_transaction(self.url, self.a) as cur:
            pg.put_record(cur,"properties",self.a,{"id":"p1","title":"Flat"})
            pg.put_record(cur,"cases",self.a,{"id":12,"property_id":"p1","message":"Leak"})
            pg.put_record(cur,"jobs",self.a,{"id":"j1","case_id":12,"property_id":"p1"})
            pg.put_record(cur,"approvals",self.a,{"id":"a1","job_id":"j1"})
            pg.put_record(cur,"documents",self.a,{"id":"d1","property_id":"p1"})
            pg.put_record(cur,"appointments",self.a,{"id":"t1","property_id":"p1"})
            pg.put_record(cur,"registrations",self.a,{"id":"r1","status":"pending"})
            pg.put_record(cur,"invitations",self.a,{"id":"i1","status":"sent"})
            for table in pg.TABLES:
                self.assertGreaterEqual(len(pg.list_records(cur,table)),1,table)
