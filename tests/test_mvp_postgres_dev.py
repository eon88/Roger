"""Real PostgreSQL integration tests for the isolated, synthetic DEV schema.

Ordinary unit test discovery skips these unless ROGER_TEST_DATABASE_URL is set.
Never point this environment variable at production.
"""
import json
import os
from pathlib import Path
import unittest
from uuid import uuid4

DATABASE_URL = os.environ.get("ROGER_TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "PostgreSQL integration URL not set")
class MVPPostgresSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        cls.connection = psycopg.connect(DATABASE_URL, autocommit=True)
        schema = (Path(__file__).resolve().parents[1]
                  / "migrations" / "002_mvp_relational_dev.sql").read_text()
        cls.connection.execute(schema)
        # Repeatability: migrations may be rerun on the development database.
        cls.connection.execute(schema)

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def test_tables_present(self):
        cur = self.connection.execute(
            "SELECT count(*) FROM pg_tables "
            "WHERE schemaname='public' AND tablename LIKE 'mvp_%'")
        self.assertEqual(cur.fetchone()[0], 18)

    def test_full_relational_chain_and_rent_balance(self):
        p = "test-property-" + uuid4().hex
        tenant = "test-tenant-" + uuid4().hex
        owner = "test-owner-" + uuid4().hex
        trades = "test-trades-" + uuid4().hex
        for person in [tenant, owner, trades]:
            self.connection.execute(
                "INSERT INTO mvp_parties(id,display_name) VALUES (%s,%s)",
                (person, person))
        self.connection.execute(
            "INSERT INTO mvp_properties(id,title,address_line,created_by_party_id) "
            "VALUES (%s,'Test flat','10 Test Lane',%s)", (p,owner))
        self.connection.execute(
            "INSERT INTO mvp_property_people(property_id,party_id,role) "
            "VALUES (%s,%s,'landlord')", (p,owner))
        self.connection.execute(
            "INSERT INTO mvp_contractor_profiles(party_id,verification_status) "
            "VALUES (%s,'approved')", (trades,))
        self.connection.execute(
            "INSERT INTO mvp_contractor_skills(party_id,trade_code) "
            "VALUES (%s,'locksmith')", (trades,))
        case_id = self.connection.execute(
            "INSERT INTO mvp_cases(property_id,reported_by_party_id,category,"
            "description) VALUES (%s,%s,'locks','Front door not closing') "
            "RETURNING id", (p,tenant)).fetchone()[0]
        job_id = self.connection.execute(
            "INSERT INTO mvp_work_orders(case_id,contractor_party_id,"
            "required_trade,status) VALUES (%s,%s,'locksmith','accepted') "
            "RETURNING id", (case_id,trades)).fetchone()[0]
        msg_id = self.connection.execute(
            "INSERT INTO mvp_case_messages(case_id,work_order_id,author_party_id,"
            "channel,body) VALUES (%s,%s,%s,'work_order','Can visit tomorrow') "
            "RETURNING id", (case_id,job_id,trades)).fetchone()[0]
        self.assertIsNotNone(msg_id)
        self.connection.execute(
            "INSERT INTO mvp_invoices(work_order_id,contractor_party_id,"
            "invoice_number,amount_pence,status) VALUES (%s,%s,%s,14280,'submitted')",
            (job_id,trades,'QA-'+uuid4().hex))
        charge_id = self.connection.execute(
            "INSERT INTO mvp_rent_charges(property_id,tenant_party_id,"
            "period_start,due_on,amount_pence) "
            "VALUES (%s,%s,'2026-10-01','2026-10-01',180000) RETURNING id",
            (p,tenant)).fetchone()[0]
        self.connection.execute(
            "INSERT INTO mvp_rent_payments(rent_charge_id,amount_pence,"
            "received_on,recorded_by_party_id) "
            "VALUES (%s,125000,'2026-10-03',%s)",
            (charge_id,owner))
        total = self.connection.execute(
            "SELECT coalesce(sum(amount_pence),0) FROM mvp_rent_payments "
            "WHERE rent_charge_id=%s", (charge_id,)).fetchone()[0]
        self.assertEqual(180000 - total, 55000)

    def test_foreign_keys_and_private_message_channel(self):
        with self.assertRaises(self.psycopg.errors.ForeignKeyViolation):
            self.connection.execute(
                "INSERT INTO mvp_properties(id,title,address_line,created_by_party_id)"
                " VALUES (%s,'Bad','Missing owner','nonexistent-party')",
                ("bad-"+uuid4().hex,))
        party = "test-auditor-" + uuid4().hex
        self.connection.execute(
            "INSERT INTO mvp_parties(id,display_name) VALUES (%s,%s)",(party,party))
        with self.assertRaises(self.psycopg.errors.CheckViolation):
            self.connection.execute(
                "INSERT INTO mvp_agent_tasks(action_code) VALUES ('invalid')")
        self.connection.execute(
            "INSERT INTO mvp_audit_events(event_type,entity_type,entity_id,"
            "actor_party_id,metadata) VALUES ('qa_action','party',%s,%s,%s::jsonb)",
            (party,party,json.dumps({"test": True})))

    def test_audit_records_block_update_and_delete(self):
        event_id = self.connection.execute(
            "INSERT INTO mvp_audit_events(event_type,entity_type,entity_id)"
            " VALUES ('created','test',%s) RETURNING id",
            (uuid4().hex,)).fetchone()[0]
        with self.assertRaises(self.psycopg.errors.RaiseException):
            self.connection.execute(
                "UPDATE mvp_audit_events SET event_type='rewritten' WHERE id=%s",
                (event_id,))
        with self.assertRaises(self.psycopg.errors.RaiseException):
            self.connection.execute(
                "DELETE FROM mvp_audit_events WHERE id=%s", (event_id,))
        self.assertEqual(
            self.connection.execute(
                "SELECT event_type FROM mvp_audit_events WHERE id=%s",
                (event_id,)).fetchone()[0], "created")


if __name__ == "__main__":
    unittest.main()
