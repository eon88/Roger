"""Integration checks for Roger's opt-in PostgreSQL adapter."""
import hashlib
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

    def test_trades_jobs_and_landlord_approvals_are_assigned(self):
        users={}
        with psycopg.connect(self.url) as conn:
            for role in ("trades","landlord"):
                uid=uuid.uuid4()
                users[role]=uid
                conn.execute("INSERT INTO app_users(id,username,password_hash) VALUES (%s,%s,'test')",
                             (uid,"assigned-"+uid.hex))
        with pg.agency_transaction(self.url,self.a) as cur:
            for role,uid in users.items():
                cur.execute("INSERT INTO agency_memberships(agency_id,user_id,role) VALUES (%s,%s,%s)",
                            (self.a,uid,role))
            pg.put_record(cur,"properties",self.a,{"id":"assignment-home","title":"Home"})
            pg.put_record(cur,"jobs",self.a,{"id":"assigned-job","property_id":"assignment-home"})
            pg.put_record(cur,"jobs",self.a,{"id":"other-job","property_id":"assignment-home"})
            pg.put_record(cur,"approvals",self.a,{"id":"assigned-approval","job_id":"assigned-job"})
            pg.put_record(cur,"approvals",self.a,{"id":"other-approval","job_id":"other-job"})
            cur.execute("INSERT INTO job_assignments(agency_id,job_id,user_id) VALUES (%s,'assigned-job',%s)",
                        (self.a,users["trades"]))
            cur.execute("INSERT INTO approval_recipients(agency_id,approval_id,user_id) VALUES (%s,'assigned-approval',%s)",
                        (self.a,users["landlord"]))
            for role,kind,expected in (("trades","jobs","assigned-job"),
                                       ("landlord","approvals","assigned-approval")):
                identity={"id":str(users[role]),"agency_id":str(self.a),"role":role}
                self.assertEqual([x["id"] for x in pg.portal_workflow_records(cur,identity,kind)],
                                 [expected])
            with self.assertRaises(PermissionError):
                pg.portal_workflow_records(cur,{"id":str(users["trades"]),"agency_id":str(self.a),"role":"trades"},"approvals")

    def test_maintenance_workflows_are_property_scoped(self):
        user=uuid.uuid4()
        with psycopg.connect(self.url) as conn:
            conn.execute("INSERT INTO app_users(id,username,password_hash) VALUES (%s,%s,'test')",
                         (user,"maintenance-"+user.hex))
        with pg.agency_transaction(self.url,self.a) as cur:
            cur.execute("INSERT INTO agency_memberships(agency_id,user_id,role) VALUES (%s,%s,'tenant')",
                        (self.a,user))
            for pid in ("maintenance-allowed","maintenance-hidden"):
                pg.put_record(cur,"properties",self.a,{"id":pid,"title":pid})
                pg.put_record(cur,"cases",self.a,{"id":"case-"+pid,"property_id":pid})
                pg.put_record(cur,"appointments",self.a,{"id":"appt-"+pid,"property_id":pid})
            cur.execute("""INSERT INTO property_access(agency_id,property_id,user_id,access_role)
                VALUES (%s,'maintenance-allowed',%s,'tenant')""",(self.a,user))
            identity={"id":str(user),"agency_id":str(self.a),"role":"tenant"}
            for kind,prefix in (("cases","case-"),("appointments","appt-")):
                self.assertEqual([x["id"] for x in pg.portal_workflow_records(cur,identity,kind)],
                                 [prefix+"maintenance-allowed"])
            for kind in ("jobs","approvals","documents"):
                with self.assertRaises(PermissionError):
                    pg.portal_workflow_records(cur,identity,kind)

    def test_explicit_property_grants_filter_roles(self):
        people={}
        with psycopg.connect(self.url) as conn:
            with conn.cursor() as cur:
                for role in ("landlord","tenant","trades"):
                    uid=uuid.uuid4()
                    people[role]=uid
                    cur.execute("INSERT INTO app_users(id,username,password_hash) VALUES (%s,%s,'test')",
                                (uid,"role-"+uid.hex))
        with pg.agency_transaction(self.url,self.a) as cur:
            for role,uid in people.items():
                cur.execute("INSERT INTO agency_memberships(agency_id,user_id,role) VALUES (%s,%s,%s)",
                            (self.a,uid,role))
            pg.put_record(cur,"properties",self.a,{"id":"shared","title":"Visible"})
            pg.put_record(cur,"properties",self.a,{"id":"private","title":"Hidden"})
            for role,uid in people.items():
                cur.execute("""INSERT INTO property_access(agency_id,property_id,user_id,access_role)
                    VALUES (%s,'shared',%s,%s)""",(self.a,uid,role))
            for role,uid in people.items():
                identity={"id":str(uid),"agency_id":str(self.a),"role":role}
                self.assertEqual([p["id"] for p in pg.portal_properties(cur,identity)],["shared"])
            agent={"id":str(self.user),"agency_id":str(self.a),"role":"agent"}
            self.assertIn("private",[p["id"] for p in pg.portal_properties(cur,agent)])
        with pg.agency_transaction(self.url,self.b) as cur:
            identity={"id":str(people["tenant"]),"agency_id":str(self.b),"role":"tenant"}
            with self.assertRaises(PermissionError):
                pg.portal_properties(cur,identity)

    def test_session_is_scoped_and_expires(self):
        from datetime import datetime, timedelta, timezone
        identity = {"id":str(self.user),"agency_id":str(self.a)}
        token = "integration-test-session-" + uuid.uuid4().hex
        pg.create_session(self.url, identity, token, datetime.now(timezone.utc)+timedelta(minutes=5))
        found = pg.session_identity(self.url,self.a,token)
        self.assertEqual(found["agency_id"],str(self.a))
        self.assertIsNone(pg.session_identity(self.url,self.b,token))
        self.assertIsNone(pg.session_identity(self.url,self.a,token+"wrong"))
        expired = "expired-" + uuid.uuid4().hex
        pg.create_session(self.url,identity,expired,datetime.now(timezone.utc)-timedelta(seconds=1))
        self.assertIsNone(pg.session_identity(self.url,self.a,expired))

    def test_agency_login_verifies_password_and_membership(self):
        salt = bytes.fromhex("1234567890abcdef1234567890abcdef")
        digest = hashlib.scrypt(b"correct-password", salt=salt, n=2**14, r=8, p=1).hex()
        with psycopg.connect(self.url) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE app_users SET password_hash=%s WHERE id=%s",
                            (salt.hex()+":"+digest,self.user))
                cur.execute("SELECT username FROM app_users WHERE id=%s",(self.user,))
                username = cur.fetchone()[0]
                cur.execute("SELECT slug FROM agencies WHERE id=%s",(self.a,))
                slug = cur.fetchone()[0]
                cur.execute("SELECT slug FROM agencies WHERE id=%s",(self.b,))
                other_slug = cur.fetchone()[0]
        authenticated = pg.authenticate_agency_user(self.url,username,"correct-password",slug)
        self.assertEqual(authenticated["agency_id"],str(self.a))
        self.assertEqual(authenticated["role"],"agent")
        self.assertIsNone(pg.authenticate_agency_user(self.url,username,"wrong",slug))
        self.assertIsNone(pg.authenticate_agency_user(self.url,username,"correct-password",other_slug))
