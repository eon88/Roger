"""Opt-in, agency-scoped PostgreSQL storage for Roger HQ.

This module does not replace the legacy JSON store. Caller MUST derive agency_id
from an authenticated, verified membership; never from request JSON or headers.
"""
import json
import os
import uuid
from contextlib import contextmanager

TABLES = frozenset(("properties", "cases", "jobs", "approvals",
                    "appointments", "documents", "registrations", "invitations"))

def enabled():
    return os.environ.get("ROGER_STORAGE_BACKEND", "json") == "postgres"

def _uuid(value):
    return str(uuid.UUID(str(value)))

@contextmanager
def agency_transaction(database_url, agency_id):
    validated_agency = _uuid(agency_id)
    import psycopg
    with psycopg.connect(database_url) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('roger.agency_id', %s, true)", (validated_agency,))
                yield cur

def assert_membership(cur, user_id, agency_id, allowed_roles=None):
    """Verify membership inside the same transaction as all scoped queries."""
    cur.execute(
        "SELECT role FROM agency_memberships WHERE agency_id=%s AND user_id=%s",
        (_uuid(agency_id), _uuid(user_id)),
    )
    record = cur.fetchone()
    if not record or (allowed_roles and record[0] not in allowed_roles):
        raise PermissionError("agency membership required")
    return record[0]

def list_records(cur, table):
    if table not in TABLES:
        raise ValueError("unsupported collection")
    cur.execute("SELECT id, payload FROM " + table + " ORDER BY id")
    return [dict(row[1], id=row[0]) for row in cur.fetchall()]

def put_record(cur, table, agency_id, record):
    if table not in TABLES:
        raise ValueError("unsupported collection")
    if not isinstance(record, dict) or "id" not in record:
        raise ValueError("record requires id")
    agency_id = _uuid(agency_id)
    rid = str(record["id"])
    payload = dict(record)
    payload.pop("id")
    if table == "properties":
        cur.execute("""INSERT INTO properties(agency_id,id,title,payload)
            VALUES (%s,%s,%s,%s::jsonb)
            ON CONFLICT (agency_id,id) DO UPDATE
            SET title=EXCLUDED.title,payload=EXCLUDED.payload""",
            (agency_id, rid, str(record.get("title") or record.get("address") or rid), json.dumps(payload)))
    elif table == "cases":
        cur.execute("""INSERT INTO cases(agency_id,id,property_id,payload)
            VALUES (%s,%s,%s,%s::jsonb)
            ON CONFLICT (agency_id,id) DO UPDATE
            SET property_id=EXCLUDED.property_id,payload=EXCLUDED.payload""",
            (agency_id, rid, str(record["property_id"]) if record.get("property_id") is not None else None, json.dumps(payload)))
    elif table == "jobs":
        cur.execute("""INSERT INTO jobs(agency_id,id,case_id,property_id,payload)
            VALUES (%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (agency_id,id) DO UPDATE
            SET case_id=EXCLUDED.case_id,property_id=EXCLUDED.property_id,payload=EXCLUDED.payload""",
            (agency_id, rid, str(record["case_id"]) if record.get("case_id") is not None else None,
             str(record["property_id"]) if record.get("property_id") is not None else None, json.dumps(payload)))
    elif table == "approvals":
        if record.get("job_id") is None:
            raise ValueError("approval requires job_id")
        cur.execute("""INSERT INTO approvals(agency_id,id,job_id,payload)
            VALUES (%s,%s,%s,%s::jsonb)
            ON CONFLICT (agency_id,id) DO UPDATE
            SET job_id=EXCLUDED.job_id,payload=EXCLUDED.payload""",
            (agency_id, rid, str(record["job_id"]), json.dumps(payload)))
    elif table in ("appointments", "documents"):
        cur.execute("INSERT INTO " + table + """(agency_id,id,property_id,payload)
            VALUES (%s,%s,%s,%s::jsonb)
            ON CONFLICT (agency_id,id) DO UPDATE
            SET property_id=EXCLUDED.property_id,payload=EXCLUDED.payload""",
            (agency_id, rid, str(record["property_id"]) if record.get("property_id") is not None else None, json.dumps(payload)))
    else:
        cur.execute("INSERT INTO " + table + """(agency_id,id,payload)
            VALUES (%s,%s,%s::jsonb)
            ON CONFLICT (agency_id,id) DO UPDATE SET payload=EXCLUDED.payload""",
            (agency_id, rid, json.dumps(payload)))
