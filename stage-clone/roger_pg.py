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
    if table == "properties":
        cur.execute("SELECT id, payload, title FROM properties ORDER BY id")
        return [dict(row[1], id=row[0], title=row[2]) for row in cur.fetchall()]
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

def authenticate_agency_user(database_url, username, password, agency_slug):
    """Resolve tenant identity on the server from credentials and membership.

    Password hashes use the same scrypt salt:hash encoding as legacy accounts.
    No agency identifier from the client is trusted as a membership assertion.
    """
    import hashlib
    import hmac
    import psycopg
    if not username or not password or not agency_slug:
        return None
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            # Resolve the agency first; memberships are RLS protected.
            cur.execute("SELECT id, status FROM agencies WHERE slug=%s", (agency_slug,))
            agency = cur.fetchone()
            if not agency or agency[1] != "active":
                return None
            cur.execute("SELECT set_config('roger.agency_id',%s,true)", (str(agency[0]),))
            cur.execute("""SELECT u.id, u.password_hash, a.id, a.status
                FROM app_users u JOIN agency_memberships m ON m.user_id=u.id
                JOIN agencies a ON a.id=m.agency_id
                WHERE u.username=%s AND a.slug=%s""", (username, agency_slug))
            row = cur.fetchone()
            if not row or row[3] != "active":
                return None
            user_id, stored, agency_id, _ = row
            try:
                salt, digest = stored.split(":", 1)
                candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                    n=2**14, r=8, p=1).hex()
                valid = hmac.compare_digest(candidate, digest)
            except (ValueError, TypeError):
                valid = False
            if not valid:
                return None
            cur.execute("SELECT set_config('roger.agency_id',%s,true)", (str(agency_id),))
            role = assert_membership(cur, user_id, agency_id)
            return {"id":str(user_id), "agency_id":str(agency_id),
                    "username":username, "role":role}

def create_session(database_url, identity, token, expires_at):
    import hashlib
    digest = hashlib.sha256(token.encode()).hexdigest()
    with agency_transaction(database_url, identity["agency_id"]) as cur:
        assert_membership(cur, identity["id"], identity["agency_id"])
        cur.execute("""INSERT INTO agency_sessions(token_hash,user_id,agency_id,expires_at)
            VALUES (%s,%s,%s,%s)""", (digest, identity["id"], identity["agency_id"], expires_at))

def session_identity(database_url, agency_id, token):
    """Resolve only a server-issued session within its agency RLS context."""
    import hashlib
    digest = hashlib.sha256(token.encode()).hexdigest()
    with agency_transaction(database_url, agency_id) as cur:
        cur.execute("""SELECT s.user_id, s.agency_id, u.username, m.role
            FROM agency_sessions s
            JOIN app_users u ON u.id=s.user_id
            JOIN agency_memberships m ON m.user_id=s.user_id AND m.agency_id=s.agency_id
            JOIN agencies a ON a.id=s.agency_id
            WHERE s.token_hash=%s AND s.expires_at>now() AND a.status='active'""", (digest,))
        row = cur.fetchone()
        if not row:
            return None
        return {"id":str(row[0]), "agency_id":str(row[1]),
                "username":row[2], "role":row[3], "display_name":row[2]}

def portal_properties(cur, identity):
    """Property list with explicit per-user grants for non-agent roles."""
    role = assert_membership(cur, identity["id"], identity["agency_id"])
    if role != identity["role"]:
        raise PermissionError("stale role")
    if role == "agent":
        return list_records(cur, "properties")
    if role not in ("tenant", "landlord", "trades"):
        raise PermissionError("unsupported role")
    cur.execute("""SELECT p.id,p.payload,p.title
        FROM properties p
        JOIN property_access a ON a.agency_id=p.agency_id AND a.property_id=p.id
        WHERE a.user_id=%s AND a.access_role=%s
        ORDER BY p.id""", (_uuid(identity["id"]), role))
    return [dict(row[1], id=row[0], title=row[2]) for row in cur.fetchall()]

def portal_workflow_records(cur, identity, collection):
    """Read-only, agency-scoped workflows. No unassigned rows leak to other roles."""
    if collection not in ("cases", "appointments", "jobs", "approvals", "documents"):
        raise ValueError("unsupported workflow")
    role = assert_membership(cur, identity["id"], identity["agency_id"])
    if role != identity["role"]:
        raise PermissionError("stale role")
    if role == "agent":
        return list_records(cur, collection)
    if collection in ("cases", "appointments") and role in ("tenant", "landlord"):
        cur.execute("""SELECT w.id,w.payload
            FROM """ + collection + """ w
            WHERE EXISTS (
              SELECT 1 FROM property_access a
              WHERE a.agency_id=w.agency_id AND a.property_id=w.property_id
                AND a.user_id=%s AND a.access_role=%s
            ) ORDER BY w.id""", (_uuid(identity["id"]), role))
    elif collection == "jobs" and role == "trades":
        cur.execute("""SELECT w.id,w.payload FROM jobs w
            WHERE EXISTS (SELECT 1 FROM job_assignments a
              WHERE a.agency_id=w.agency_id AND a.job_id=w.id AND a.user_id=%s)
            ORDER BY w.id""", (_uuid(identity["id"]),))
    elif collection == "approvals" and role == "landlord":
        cur.execute("""SELECT w.id,w.payload FROM approvals w
            WHERE EXISTS (SELECT 1 FROM approval_recipients a
              WHERE a.agency_id=w.agency_id AND a.approval_id=w.id AND a.user_id=%s)
            ORDER BY w.id""", (_uuid(identity["id"]),))
    elif collection == "documents" and role in ("tenant","landlord","trades"):
        cur.execute("""SELECT w.id,w.payload FROM documents w
            WHERE EXISTS (SELECT 1 FROM document_grants a
              WHERE a.agency_id=w.agency_id AND a.document_id=w.id AND a.user_id=%s)
            ORDER BY w.id""", (_uuid(identity["id"]),))
    else:
        raise PermissionError("workflow access not granted")
    return [dict(row[1], id=row[0]) for row in cur.fetchall()]

def create_maintenance_case(cur, identity, property_id, description):
    """Tenant creates a case for an explicitly assigned property."""
    import secrets
    role = assert_membership(cur, identity["id"], identity["agency_id"], {"tenant"})
    if role != identity["role"]:
        raise PermissionError("stale role")
    description = str(description).strip()
    if not description or len(description) > 2000:
        raise ValueError("description must be 1-2000 characters")
    property_id = str(property_id)
    cur.execute("""SELECT 1 FROM property_access
        WHERE agency_id=%s AND property_id=%s AND user_id=%s AND access_role='tenant'""",
        (_uuid(identity["agency_id"]),property_id,_uuid(identity["id"])))
    if not cur.fetchone():
        raise PermissionError("property not assigned")
    case_id = "case-" + secrets.token_hex(12)
    payload = {"description":description,"status":"open","reported_by":_uuid(identity["id"])}
    cur.execute("""INSERT INTO cases(agency_id,id,property_id,payload)
        VALUES (%s,%s,%s,%s::jsonb)""",
        (_uuid(identity["agency_id"]),case_id,property_id,json.dumps(payload)))
    return {"id":case_id,"property_id":property_id,**payload}

def create_repair_job(cur, identity, case_id, trades_user_id, description):
    """Agent creates a job linked to a case and assigns an agency tradesperson."""
    import secrets
    role = assert_membership(cur, identity["id"], identity["agency_id"], {"agent"})
    if role != identity["role"]:
        raise PermissionError("agent required")
    agency = _uuid(identity["agency_id"])
    trades_user_id = _uuid(trades_user_id)
    description = str(description).strip()
    if not description or len(description) > 2000:
        raise ValueError("description must be 1-2000 characters")
    cur.execute("SELECT property_id FROM cases WHERE agency_id=%s AND id=%s",
                (agency,str(case_id)))
    row = cur.fetchone()
    if not row or not row[0]:
        raise ValueError("case not found or lacks property")
    cur.execute("""SELECT 1 FROM agency_memberships
        WHERE agency_id=%s AND user_id=%s AND role='trades'""",
        (agency,trades_user_id))
    if not cur.fetchone():
        raise PermissionError("tradesperson not in agency")
    job_id = "job-" + secrets.token_hex(12)
    payload = {"description":description,"status":"assigned",
               "assigned_by":_uuid(identity["id"])}
    cur.execute("""INSERT INTO jobs(agency_id,id,case_id,property_id,payload)
        VALUES (%s,%s,%s,%s,%s::jsonb)""",
        (agency,job_id,str(case_id),row[0],json.dumps(payload)))
    cur.execute("""INSERT INTO job_assignments(agency_id,job_id,user_id)
        VALUES (%s,%s,%s)""",(agency,job_id,trades_user_id))
    return {"id":job_id,"case_id":str(case_id),"property_id":row[0],**payload}


def decide_repair_approval(cur, identity, approval_id, decision):
    """Only a recipient landlord can decide a pending approval, once."""
    role = assert_membership(cur, identity["id"], identity["agency_id"], {"landlord"})
    if role != identity["role"]:
        raise PermissionError("landlord required")
    if decision not in ("approved","rejected"):
        raise ValueError("invalid decision")
    agency = _uuid(identity["agency_id"])
    cur.execute("""SELECT 1 FROM approval_recipients
        WHERE agency_id=%s AND approval_id=%s AND user_id=%s""",
        (agency,str(approval_id),_uuid(identity["id"])))
    if not cur.fetchone():
        raise PermissionError("approval not assigned")
    cur.execute("""UPDATE approvals SET payload=jsonb_set(
        jsonb_set(payload,'{status}',to_jsonb(%s::text)),
        '{decided_by}',to_jsonb(%s::text))
        WHERE agency_id=%s AND id=%s AND COALESCE(payload->>'status','pending')='pending'
        RETURNING id""",(decision,_uuid(identity["id"]),agency,str(approval_id)))
    if not cur.fetchone():
        raise ValueError("approval already decided")
    return {"id":str(approval_id),"status":decision}

def respond_to_appointment(cur, identity, appointment_id, decision):
    role = assert_membership(cur, identity["id"], identity["agency_id"])
    if role != identity["role"] or role not in ("tenant", "landlord"):
        raise PermissionError("appointment response denied")
    if decision not in ("confirmed", "declined"):
        raise ValueError("invalid decision")
    cur.execute("""UPDATE appointments ap
      SET payload=jsonb_set(payload,'{status}',to_jsonb(%s::text))
      WHERE ap.agency_id=%s AND ap.id=%s
        AND COALESCE(ap.payload->>'status','pending')='pending'
        AND EXISTS (SELECT 1 FROM property_access a
          WHERE a.agency_id=ap.agency_id AND a.property_id=ap.property_id
            AND a.user_id=%s AND a.access_role=%s)
      RETURNING ap.id""",
      (decision,_uuid(identity["agency_id"]),str(appointment_id),_uuid(identity["id"]),role))
    if not cur.fetchone():
        raise PermissionError("appointment not available")
    return {"id":str(appointment_id),"status":decision}

def agency_inbox(cur, identity):
    role = assert_membership(cur, identity["id"], identity["agency_id"])
    if role != identity["role"]:
        raise PermissionError("stale role")
    uid = _uuid(identity["id"])
    cur.execute("""SELECT id,sender_id,recipient_id,body,created_at
      FROM agency_messages WHERE sender_id=%s OR recipient_id=%s
      ORDER BY created_at DESC LIMIT 100""", (uid,uid))
    return [{"id":str(r[0]),"sender_id":str(r[1]),"recipient_id":str(r[2]),
             "body":r[3],"created_at":r[4].isoformat()} for r in cur.fetchall()]

def send_agency_message(cur, identity, recipient_id, body):
    role = assert_membership(cur, identity["id"], identity["agency_id"])
    if role != identity["role"]:
        raise PermissionError("stale role")
    body = str(body).strip()
    if not body or len(body) > 4000:
        raise ValueError("invalid message length")
    recipient = _uuid(recipient_id)
    agency = _uuid(identity["agency_id"])
    cur.execute("SELECT role FROM agency_memberships WHERE agency_id=%s AND user_id=%s",
                (agency, recipient))
    if not cur.fetchone():
        raise PermissionError("recipient not a member")
    cur.execute("INSERT INTO agency_messages(agency_id,sender_id,recipient_id,body) VALUES (%s,%s,%s,%s) RETURNING id",
                (agency,_uuid(identity["id"]),recipient,body))
    return str(cur.fetchone()[0])
