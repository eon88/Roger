"""PostgreSQL agency isolation integration tests.
Requires TEST_DATABASE_URL pointing to a disposable PostgreSQL database,
psycopg and a role without BYPASSRLS. Never use a production database.
Run: python -m unittest discover -s tests -p 'test_agency_isolation.py'
"""
import os
import pathlib
import unittest

try:
    import psycopg
except ImportError:
    psycopg = None

SCHEMA = pathlib.Path(__file__).resolve().parents[1] / "db" / "001_multi_agency.sql"

@unittest.skipUnless(psycopg and os.getenv("TEST_DATABASE_URL"), "Requires psycopg and TEST_DATABASE_URL")
class AgencyIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True)
        with cls.db.cursor() as cur:
            cur.execute(SCHEMA.read_text())
            cur.execute("INSERT INTO agencies(name,slug) VALUES ('Agency A','agency-a'),('Agency B','agency-b')")
            cur.execute("SELECT id,slug FROM agencies ORDER BY slug")
            cls.a, cls.b = [r[0] for r in cur.fetchall()]
            # A non-owner/non-BYPASSRLS runtime role must be used for isolation checks.
            cur.execute("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname=current_user")
            bypass, superuser = cur.fetchone()
            if bypass or superuser:
                raise RuntimeError("TEST_DATABASE_URL must not use superuser/BYPASSRLS role")
    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_properties_hidden_and_cross_tenant_write_rejected(self):
        with self.db.transaction():
            with self.db.cursor() as cur:
                cur.execute("SELECT set_config('roger.agency_id',%s,true)",(str(self.a),))
                cur.execute("INSERT INTO properties(agency_id,id,title) VALUES (%s,'home','A home')",(self.a,))
                cur.execute("SELECT count(*) FROM properties WHERE agency_id=%s",(self.b,))
                self.assertEqual(cur.fetchone()[0],0)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with self.db.transaction():
                        cur.execute("INSERT INTO properties(agency_id,id,title) VALUES (%s,'stolen','B home')",(self.b,))
    def test_other_agency_cannot_read_property(self):
        with self.db.transaction():
            with self.db.cursor() as cur:
                cur.execute("SELECT set_config('roger.agency_id',%s,true)",(str(self.a),))
                cur.execute("INSERT INTO properties(agency_id,id,title) VALUES (%s,'secret','Private A') ON CONFLICT DO NOTHING",(self.a,))
                cur.execute("SELECT set_config('roger.agency_id',%s,true)",(str(self.b),))
                cur.execute("SELECT count(*) FROM properties WHERE id='secret'")
                self.assertEqual(cur.fetchone()[0],0)

    def test_cross_agency_foreign_key_rejected(self):
        with self.db.transaction():
            with self.db.cursor() as cur:
                cur.execute("SELECT set_config('roger.agency_id',%s,true)",(str(self.a),))
                cur.execute("INSERT INTO properties(agency_id,id,title) VALUES (%s,'fk-home','A') ON CONFLICT DO NOTHING",(self.a,))
                cur.execute("SELECT set_config('roger.agency_id',%s,true)",(str(self.b),))
                with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                    with self.db.transaction():
                        cur.execute("INSERT INTO cases(agency_id,id,property_id) VALUES (%s,'case-b','fk-home')",(self.b,))

    def test_all_scoped_tables_have_rls(self):
        names = ('properties','cases','jobs','approvals','appointments','documents','registrations','invitations','agency_memberships','subscriptions')
        with self.db.cursor() as cur:
            cur.execute("SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class WHERE relname = ANY(%s)",(list(names),))
            flags = {name:(enabled,forced) for name,enabled,forced in cur.fetchall()}
            self.assertEqual(set(flags),set(names))
            self.assertTrue(all(enabled and forced for enabled,forced in flags.values()))

    def test_no_agency_context_sees_nothing(self):
        with self.db.transaction():
            with self.db.cursor() as cur:
                cur.execute("SELECT set_config('roger.agency_id','',true)")
                cur.execute("SELECT count(*) FROM properties")
                self.assertEqual(cur.fetchone()[0],0)
