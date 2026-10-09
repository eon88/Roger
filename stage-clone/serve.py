#!/usr/bin/env python3
"""Local dev server for the Stage clone. Maps clean URLs to saved files.

v2 (post-audit): status-sync between cases/jobs/approvals, credential gating
on trades jobs, structured registrations, evidence on approvals, validation.
"""
from http.server import SimpleHTTPRequestHandler, HTTPServer
import email.parser
import email.policy
import email.utils
import email.errors
from email.message import EmailMessage
from email.utils import formataddr
import smtplib
import hashlib
import calendar
import imaplib
import hmac
import http.cookies
import json
import os
import re
import secrets
import tempfile
import urllib.parse
from datetime import datetime, timedelta, timezone

import jev_client

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", ROOT)
os.makedirs(DATA_DIR, exist_ok=True)
STAGE_FILE = os.path.join(DATA_DIR, "stage.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
FILES_DIR = os.environ.get("ROGER_FILES_DIR", os.path.join(DATA_DIR, "files"))
os.makedirs(FILES_DIR, mode=0o700, exist_ok=True)
SESSION_TTL = timedelta(days=7)
LOGIN_TRIES = {}  # ip -> [timestamps]; in-memory, resets on restart (acceptable for demo-scale)

def login_throttled(ip):
    nowts = datetime.now(timezone.utc)
    tries = [t for t in LOGIN_TRIES.get(ip, []) if (nowts - t).total_seconds() < 300]
    LOGIN_TRIES[ip] = tries
    return len(tries) >= 5

def login_note(ip, ok):
    if ok:
        LOGIN_TRIES.pop(ip, None)
    else:
        LOGIN_TRIES.setdefault(ip, []).append(datetime.now(timezone.utc))

def postgres_connection():
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is required when ROGER_STORAGE_BACKEND=postgres")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("install psycopg[binary] to use PostgreSQL storage") from exc
    return psycopg.connect(os.environ["DATABASE_URL"])

def load_users():
    if os.environ.get("ROGER_STORAGE_BACKEND", "file") == "postgres":
        with postgres_connection() as connection:
            row = connection.execute("SELECT payload FROM roger_users_snapshot WHERE singleton_id=1").fetchone()
        if not row:
            raise RuntimeError("PostgreSQL users snapshot is empty; run the migration first")
        return row[0]
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def atomic_json_write(path, data):
    """Replace JSON snapshots atomically so a crash cannot leave a truncated file."""
    fd, tmp_path = tempfile.mkstemp(prefix=".roger-write-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
        try:
            dir_fd = os.open(os.path.dirname(path), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

def load_stage():
    if os.environ.get("ROGER_STORAGE_BACKEND", "file") == "postgres":
        with postgres_connection() as connection:
            row = connection.execute("SELECT payload FROM roger_stage_snapshot WHERE singleton_id=1").fetchone()
        if not row:
            raise RuntimeError("PostgreSQL stage snapshot is empty; run the migration first")
        return row[0]
    with open(STAGE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_users(data):
    if os.environ.get("ROGER_STORAGE_BACKEND", "file") == "postgres":
        with postgres_connection() as connection:
            connection.execute(
                "INSERT INTO roger_users_snapshot(singleton_id,payload) VALUES (1,%s::jsonb) "
                "ON CONFLICT(singleton_id) DO UPDATE SET payload=EXCLUDED.payload, imported_at=now()",
                (json.dumps(data),),
            )
        return
    atomic_json_write(USERS_FILE, data)

def save_stage(data):
    if os.environ.get("ROGER_STORAGE_BACKEND", "file") != "postgres":
        atomic_json_write(STAGE_FILE, data)
        return
    collection_tables = {
        "parties": ("roger_parties", ("id",)),
        "properties": ("roger_properties", ("id",)),
        "tenancies": ("roger_tenancies", ("id", "property_id")),
        "cases": ("roger_cases", ("id", "property_id")),
        "jobs": ("roger_jobs", ("id", "case_id", "property_id")),
        "documents": ("roger_documents", ("id", "case_id", "property_id")),
    }
    with postgres_connection() as connection:
        connection.execute(
            "INSERT INTO roger_stage_snapshot(singleton_id,payload) VALUES (1,%s::jsonb) "
            "ON CONFLICT(singleton_id) DO UPDATE SET payload=EXCLUDED.payload, imported_at=now()",
            (json.dumps(data),),
        )
        for collection, (table, columns) in collection_tables.items():
            connection.execute("TRUNCATE TABLE " + table)
            for record in data.get(collection, []):
                values = [record.get(column) if column != "id" else str(record.get("id")) for column in columns]
                values.append(json.dumps(record))
                placeholders = ",".join(["%s"] * len(columns) + ["%s::jsonb"])
                column_sql = ",".join(columns + ("payload",))
                connection.execute(
                    "INSERT INTO " + table + "(" + column_sql + ") VALUES (" + placeholders + ")",
                    tuple(values),
                )

# Demo tradesperson credential store. In the real product: verified at
# registration (Gas Safe lookup), carried on the profile.
TRADE_PROFILES = {
    "R. Doyle Gas & Heat": {"trades": ["gas", "plumbing", "heating"], "gas_safe": "VERIFIED-DEMO"},
}
# Trades that legally need a specific verified certificate before booking
CERT_REQUIRED = {"gas": "Gas Safe"}

def now():
    return datetime.utcnow().isoformat() + "Z"

class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    # ---------- auth plumbing ----------
    PUBLIC_GET = {"/", "/login", "/logout", "/signin", "/register/landlord", "/register/trades",
              "/dash.css", "/favicon.svg", "/sample-home.jpg", "/api/whoami"}
    PUBLIC_POST = {"/login", "/api/public", "/register/landlord", "/register/trades", "/api/enquiry"}

    def parse_cookies(self):
        raw = self.headers.get("Cookie") or ""
        c = http.cookies.SimpleCookie()
        try:
            c.load(raw)
        except http.cookies.CookieError:
            pass
        return {k: m.value for k, m in c.items()}

    def session_user(self):
        tok = self.parse_cookies().get("stage_session")
        if not tok:
            return None
        users = load_users()
        sess = users.get("sessions", {}).get(tok)
        if not sess:
            return None
        if datetime.fromisoformat(sess["exp"]) < datetime.now(timezone.utc):
            users["sessions"].pop(tok, None)
            save_users(users)
            return None
        return next((u for u in users["users"] if u["username"] == sess["username"]), None)

    ROLE_PAGES = {"/agent": {"agent"}, "/tenant": {"tenant"}, "/landlord": {"landlord"}, "/trades": {"trades"}}
    ROLE_API = {"/api/tenant/issue": {"tenant", "agent"}, "/api/job-action": {"trades", "agent", "landlord"},
                "/api/landlord-action": {"landlord", "agent"}, "/api/registration-action": {"agent"}, "/api/prospect-action": {"agent"}, "/api/property-action": {"agent"}, "/api/party-action": {"agent"}, "/api/tenancy-action": {"agent"}, "/api/management-agreement-action": {"agent"}, "/api/email-reply": {"agent"}, "/api/rent-ledger-action": {"agent"}, "/api/landlord-statement-action": {"agent"}, "/api/compliance-action": {"agent"}, "/api/email-sync": {"agent"},
                "/api/case-action": {"agent", "tenant", "landlord", "trades"},
                "/api/appointment": {"agent"}, "/api/appointment-action": {"agent", "tenant", "landlord"},
                "/api/invitation": {"agent"}, "/api/invitation-action": {"agent"},
                "/api/document": {"agent"}, "/api/document-action": {"agent"}}

    def require(self, roles=None):
        """Returns user or None (response already sent)."""
        u = self.session_user()
        if not u:
            if self.path.startswith("/api/"):
                self._json({"error": "authentication required"}, 401)
            else:
                self.send_response(302)
                self.send_header("Location", "/login")
                self.end_headers()
            return None
        if roles and u["role"] not in roles:
            if self.path.startswith("/api/"):
                self._json({"error": "not your portal"}, 403)
            else:
                self.send_response(302)
                self.send_header("Location", "/" + u["role"])
                self.end_headers()
            return None
        return u

    def is_public(self, path):
        return path in self.PUBLIC_GET or path.startswith("/_next/") or path == "/api/public"

    def do_POST_login(self, data):
        ip = self.client_address[0]
        if login_throttled(ip):
            return self._json({"error": "too many attempts — try again in 5 minutes"}, 429)
        username = str(data.get("username", ""))[:40]
        password = str(data.get("password", ""))[:200]
        users = load_users()
        u = next((x for x in users["users"] if x["username"] == username), None)
        if u:
            h = hashlib.scrypt(password.encode(), salt=bytes.fromhex(u["salt"]), n=2**14, r=8, p=1).hex()
            if not hmac.compare_digest(h, u["hash"]):
                u = None
        if not u:
            login_note(ip, ok=False)
            return self._json({"error": "wrong username or password"}, 401)
        login_note(ip, ok=True)
        tok = secrets.token_urlsafe(32)
        nowiso = datetime.now(timezone.utc)
        users["sessions"] = {k: v for k, v in users.get("sessions", {}).items()
                             if datetime.fromisoformat(v["exp"]) > nowiso}
        users["sessions"][tok] = {"username": username, "exp": (nowiso + SESSION_TTL).isoformat()}
        save_users(users)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        ck = http.cookies.SimpleCookie()
        ck["stage_session"] = tok
        ck["stage_session"]["httponly"] = True
        ck["stage_session"]["samesite"] = "Lax"
        ck["stage_session"]["path"] = "/"
        self.send_header("Set-Cookie", ck.output(header="").strip())
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "role": u["role"]}).encode())

    # ---------- routes ----------
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/login":
            return self.serve_file("login.html")
        if path == "/logout":
            self.send_response(302)
            self.send_header("Set-Cookie", "stage_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax")
            self.send_header("Location", "/")
            self.end_headers()
            return
        if path == "/api/trades-pool":
            u = self.require({"agent"})
            if not u:
                return
            return self._json({"trades": self.approved_trades(load_stage())})
        if path == "/api/compliance":
            if not self.require({"agent"}):
                return
            stage = load_stage()
            return self._json({"records": [self.safe_compliance_record(x) for x in stage.get("compliance_records", [])]})
        if path == "/api/landlord-statements":
            if not self.require({"agent"}):
                return
            return self._json({"statements": load_stage().get("landlord_statements", [])})
        if path == "/api/rent-ledger":
            if not self.require({"agent"}):
                return
            stage = load_stage()
            return self._json({"entries": [self.safe_rent_entry(x) for x in stage.get("rent_ledger_entries", [])]})
        if path == "/api/appointments":
            u = self.require({"agent", "tenant", "landlord"})
            if not u:
                return
            return self._json({"appointments": self.scoped_appointments(u)})
        if path == "/api/public":
            return self.serve_public_listings()
        if path == "/api/whoami":
            u = self.session_user()
            return self._json({"authenticated": False} if not u else
                              {"username": u["username"], "role": u["role"], "display_name": u["display_name"]})
        m = re.fullmatch(r"/api/invitation/validate/([A-Za-z0-9_\-]+)", path)
        if m:
            return self._json(self.validate_invitation_token(m.group(1)))
        m = re.fullmatch(r"/api/documents", path)
        if m:
            u = self.require({"agent", "tenant", "landlord", "trades"})
            if not u:
                return
            return self._json({"documents": self.scoped_documents(u)})
        m = re.fullmatch(r"/api/document/([A-Za-z0-9_\-]+)$", path)
        if m:
            u = self.require({"agent", "tenant", "landlord", "trades"})
            if not u:
                return
            doc = self.get_document(m.group(1))
            if not doc:
                return self._json({"error": "document not found"}, 404)
            if not self.can_view_document(u, doc):
                return self._json({"error": "not your portal"}, 403)
            return self._json({"document": self.safe_document(doc)})
        m = re.fullmatch(r"/api/document/([A-Za-z0-9_\-]+)/file", path)
        if m:
            u = self.require({"agent", "tenant", "landlord", "trades"})
            if not u:
                return
            doc = self.get_document(m.group(1))
            if not doc:
                return self._json({"error": "document not found"}, 404)
            if not self.can_view_document(u, doc):
                return self._json({"error": "not your portal"}, 403)
            return self.serve_document_file(doc)
        if not self.is_public(path):
            if not self.require(self.ROLE_PAGES.get(path)):
                return
        routes = {
            "/api/public": "api-public.json",
            "/api/stage": "__scoped_stage__",
            "/signin": "signin.html",
            "/register/landlord": "register-landlord.html",
            "/register/trades": "register-trades.html",
            "/agent": "agent.html",
            "/tenant": "tenant.html",
            "/landlord": "landlord.html",
            "/trades": "trades.html",
        }
        if path in routes:
            if routes[path] == "__scoped_stage__":
                return self.serve_scoped_stage()
            return self.serve_file(routes[path])
        if path != "/" and os.path.isdir(os.path.join(ROOT, path.lstrip("/"))):
            self.path = path.rstrip("/") + ".html"
        return super().do_GET()

    def serve_scoped_stage(self):
        """The audit's biggest hole closed: the SERVER decides what each role may see."""
        u = self.session_user()
        stage = load_stage()
        if u["role"] == "agent":
            return self._json(stage)
        d = json.loads(json.dumps(stage))  # deep copy
        me = u["display_name"]
        props = d.get("properties", [])
        if u["role"] == "tenant":
            myprops = [p for p in props if p.get("tenant") == me]
            mycases = [c for c in d.get("cases", []) if c.get("name") == me]
            cids = {c["id"] for c in mycases}
            myjobs = [{k: v for k, v in j.items() if k != "email"}
                      for j in d.get("jobs", []) if j.get("case_id") in cids]
            for c in mycases:
                c["thread"] = [t for t in (c.get("thread") or []) if "tenant" in (t.get("to") or []) or t.get("author") == me]
            d = {"properties": myprops, "cases": mycases, "jobs": myjobs,
                 "authority": d.get("authority"), "role": "tenant"}
        elif u["role"] == "landlord":
            myprops = [p for p in props if p.get("landlord") == me]
            pids = {p["id"] for p in myprops}
            mycases = [c for c in d.get("cases", []) if c.get("property_id") in pids]
            for c in mycases:
                c["thread"] = [t for t in (c.get("thread") or []) if "landlord" in (t.get("to") or []) or t.get("author") == me]
            d = {"properties": myprops,
                 "cases": mycases,
                 "jobs": [j for j in d.get("jobs", []) if j.get("property_id") in pids],
                 "approvals": [a for a in d.get("approvals", []) if a.get("landlord") == me],
                 "authority": d.get("authority"), "role": "landlord"}
        elif u["role"] == "trades":
            keep = ("id", "case_id", "property_id", "message", "triage", "required_trade",
                    "status", "assigned_to", "requested_by", "gate_reason", "quotes",
                    "approved_quote_pence", "invoice_pence", "created_at", "completed_at", "paid_at")
            me = u["display_name"]
            myjobs = [j for j in d.get("jobs", []) if j.get("status") == "open" or j.get("assigned_to") == me or j.get("requested_by") == me]
            mycase_ids = {j.get("case_id") for j in myjobs}
            threads = {}
            for c in d.get("cases", []):
                if c["id"] in mycase_ids or me in (c.get("participants") or []):
                    threads[c["id"]] = [t for t in c.get("thread", [])
                                        if "trades" in (t.get("to") or []) or t.get("author") == me]
            d = {"properties": [{k: v for k, v in p.items() if k != "tenant"} for p in props],
                 "jobs": [{k: v for k, v in j.items() if k in keep} for j in myjobs],
                 "threads": threads,
                 "approvals": [{k: v for k, v in a.items() if k != "reason"}
                               for a in d.get("approvals", []) if a.get("evidence", {}).get("tradesperson") == me],
                 "authority": d.get("authority"), "role": "trades"}
        self._json(d)

    def do_POST(self):
        path = self.path.split("?")[0]
        self.user = None
        if not self.is_public(path) and path not in self.PUBLIC_POST:
            u = self.require(self.ROLE_API.get(path))
            if not u:
                return
            self.user = u
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            data = json.loads(body)
        except Exception:
            data = dict(urllib.parse.parse_qsl(body))
        handlers = {
            "/login": self.do_POST_login,
            "/api/public": self.handle_public_post,
            "/register/landlord": lambda d: self.handle_registration("landlord", d),
            "/register/trades": lambda d: self.handle_registration("trades", d),
            "/api/enquiry": self.handle_enquiry,
            "/api/appointment": self.handle_appointment,
            "/api/appointment-action": self.handle_appointment_action,
            "/api/invitation": self.handle_invitation,
            "/api/invitation-action": self.handle_invitation_action,
            "/api/document": self.handle_document,
            "/api/document-action": self.handle_document_action,
            "/api/tenant/issue": self.handle_tenant_issue,
            "/api/job-action": self.handle_job_action,
            "/api/landlord-action": self.handle_landlord_action,
            "/api/registration-action": self.handle_registration_action,
            "/api/prospect-action": self.handle_prospect_action,
            "/api/property-action": self.handle_property_action,
            "/api/party-action": self.handle_party_action,
            "/api/tenancy-action": self.handle_tenancy_action,
            "/api/management-agreement-action": self.handle_management_agreement_action,
            "/api/case-action": self.handle_case_action,
            "/api/email-reply": self.handle_email_reply,
            "/api/email-sync": self.handle_email_sync,
            "/api/rent-ledger-action": self.handle_rent_ledger_action,
            "/api/landlord-statement-action": self.handle_landlord_statement_action,
            "/api/compliance-action": self.handle_compliance_action,
        }
        if path in handlers:
            return handlers[path](data)
        self._json({"error": "unknown endpoint"}, 404)

    # ---------- shared helpers ----------
    def _json(self, obj, code=200):
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def triage(self, message):
        return jev_client.triage(message or "")

    def find_prop(self, stage, pid):
        return next((p for p in stage.get("properties", []) if p["id"] == pid), None)

    def sync_case(self, stage, case_id, status):
        """P1 spine: case status follows the job/approval lifecycle."""
        c = next((c for c in stage.get("cases", []) if c["id"] == case_id), None)
        if c and c.get("status") != "closed":
            c["status"] = status
            c["status_at"] = now()

    def audit(self, stage, entry):
        stage.setdefault("audit_log", []).append({"at": now(), **entry})

    def post_msg(self, stage, case_id, text, to=("tenant", "landlord", "trades")):
        """Thread message authored by the LOGGED-IN user — never trust client identity."""
        u = getattr(self, "user", None) or {"display_name": "System", "role": "system", "username": "system"}
        c = next((c for c in stage.get("cases", []) if c["id"] == case_id), None)
        if not c:
            return None
        c.setdefault("thread", []).append({
            "author": u["display_name"], "role": u["role"],
            "text": str(text)[:2000], "to": list(to), "at": now()})
        return c

    def store_case_attachments(self, stage, case, attachments, uploaded_by):
        """Store small issue evidence files as document records linked to the case."""
        if not attachments:
            return []
        if not isinstance(attachments, list):
            raise ValueError("attachments must be a list")
        import base64
        created = []
        for item in attachments[:4]:
            if not isinstance(item, dict):
                continue
            b64 = str(item.get("content_b64", ""))
            try:
                raw = base64.b64decode(b64, validate=True)
            except Exception as exc:
                raise ValueError("attachment content_b64 must be valid base64") from exc
            if not raw:
                continue
            if len(raw) > 5 * 1024 * 1024:
                raise ValueError("attachment file too large (max 5 MB)")
            fname = os.path.basename(str(item.get("file_name", "evidence"))[:120]) or "evidence"
            fname = re.sub(r"[^A-Za-z0-9._ -]", "_", fname)
            content_type = str(item.get("content_type", "application/octet-stream"))[:80]
            if not (content_type.startswith("image/") or content_type == "application/pdf"):
                raise ValueError("attachments must be images or PDFs")
            doc_id = f"doc-{len(stage.get('documents', [])) + len(created) + 1}"
            created.append({
                "id": doc_id, "case_id": case["id"], "property_id": case.get("property_id"),
                "document_type": "maintenance_evidence", "title": "Maintenance evidence",
                "description": "Uploaded with tenant maintenance report",
                "file_name": fname, "content_type": content_type, "file_size": len(raw),
                "storage_key": self.store_document_body(raw),
                "uploaded_by": uploaded_by, "uploaded_at": now(),
                "verified_by": None, "verified_at": None, "status": "pending", "notes": "",
            })
        if created:
            stage.setdefault("documents", []).extend(created)
            case.setdefault("document_ids", []).extend(d["id"] for d in created)
            self.audit(stage, {"actor": uploaded_by, "action": "maintenance_evidence_uploaded",
                               "target": case["id"], "note": str(len(created)) + " file(s)"})
        return created

    def approved_trades(self, stage):
        """Companies an agent may put on a case: seeded profiles + approved registrations."""
        out = []
        for name, prof in TRADE_PROFILES.items():
            out.append({"company": name, "trades": prof["trades"], "gas_safe": bool(prof.get("gas_safe"))})
        for r in stage.get("registrations", []):
            if (r.get("role") == "trades" and r.get("status") == "approved"
                    and r.get("prospect_stage") not in ("suspended", "rejected")):
                trades = [t for t in (r.get("trades") or []) if t]
                out.append({"company": r["name"], "trades": trades or ["general"],
                            "gas_safe": bool(r.get("gas_safe_number"))})
        return out

    # ---------- public site form (the cloned bundle posts here) ----------
    KIND_MAP = {"Landlord enquiry": "landlord", "Trade application": "trades", "Rental enquiry": "renter"}

    def handle_public_post(self, data):
        kind = str(data.get("kind", ""))
        role = self.KIND_MAP.get(kind, "renter")
        # honeypot: pretend success to bots
        if data.get("website"):
            return self._json({"ok": True, "reference": "received", "demo": True})
        message = str(data.get("message", ""))[:3000]
        name = str(data.get("name", "Someone"))[:100]
        email = str(data.get("email", ""))[:254]
        stage = load_stage()
        t = self.triage(message)
        if role in ("landlord", "trades"):
            reg = {"id": self._next_reg_id(), "role": role, "name": name,
                   "email": email, "details": message, "status": "pending",
                   "consent": bool(data.get("consent")), "submitted_at": now()}
            stage.setdefault("registrations", []).append(reg)
            ref = reg["id"]
        else:
            cid = stage.get("next_case_id", 490)
            stage["next_case_id"] = cid + 1
            pid = data.get("propertyId") if self.find_prop(stage, data.get("propertyId")) else None
            stage.setdefault("cases", []).append({"id": cid, "type": "enquiry", "property_id": pid,
                "role": "renter", "name": name, "email": email, "message": message,
                "status": "new", "triage": t, "consent": bool(data.get("consent")), "submitted_at": now()})
            ref = f"case-{cid}"
        self.audit(stage, {"actor": "public-site", "action": f"{role}_submission", "target": ref})
        save_stage(stage)
        # The cloned bundle renders this success state natively:
        # "Thank you, {name}. Reference: {ref}"
        self._json({"ok": True, "reference": ref, "received": now()})

    # ---------- registrations ----------
    def handle_registration(self, role, data):
        # honeypot: silently drop bots
        if data.get("website"):
            return self._json({"success": True, "queued": False})
        reg = {
            "id": self._next_reg_id(),
            "role": role,
            "name": str(data.get("name", ""))[:100],
            "email": str(data.get("email", ""))[:254],
            "details": str(data.get("details", ""))[:3000],
            "phone": str(data.get("phone", ""))[:30],
            "status": "pending",
            "submitted_at": now(),
        }
        if role == "trades":
            reg["gas_safe_number"] = str(data.get("gas_safe_number", ""))[:20]
            reg["trades"] = [str(t)[:20] for t in (data.get("trades") or [])][:8]
            reg["insurance_expiry"] = str(data.get("insurance_expiry", ""))[:20]
            reg["coverage"] = str(data.get("coverage", ""))[:100]
        else:
            reg["property_address"] = str(data.get("property_address", ""))[:200]
            reg["units"] = str(data.get("units", ""))[:6]
        stage = load_stage()
        stage.setdefault("registrations", []).append(reg)
        save_stage(stage)
        self._json({"success": True, "registration_id": reg["id"]})

    def _reg_ids(self):
        return [r["id"] for r in load_stage().get("registrations", [])]

    def _next_reg_id(self):
        nums = [int(i.split("-")[1]) for i in self._reg_ids() if re.fullmatch(r"reg-\d+", i)]
        return f"reg-{(max(nums) + 1) if nums else 1}"

    def handle_registration_action(self, data):
        stage = load_stage()
        reg = next((r for r in stage.get("registrations", []) if r["id"] == data.get("id")), None)
        if not reg:
            return self._json({"error": "not found"}, 404)
        action = data.get("action")
        if action not in ("approve", "reject"):
            return self._json({"error": "action must be approve|reject"}, 400)
        if action == "approve" and reg.get("role") == "trades" and not reg.get("credentials_checked_at"):
            return self._json({"error": "record a credentials check in the Trades pipeline before approval"}, 409)
        reg["status"] = "approved" if action == "approve" else "rejected"
        reg["actioned_at"] = now()
        reg["decision_note"] = str(data.get("note", ""))[:300]
        # approving a trades reg with credentials registers them in the profile store
        if action == "approve" and reg["role"] == "trades" and reg.get("name"):
            prof = TRADE_PROFILES.setdefault(reg["name"], {"trades": [], "gas_safe": None})
            prof["trades"] = sorted(set(prof["trades"]) | set(reg.get("trades") or []))
            if reg.get("gas_safe_number"):
                prof["gas_safe"] = reg["gas_safe_number"]
        self.audit(stage, {"actor": "agent", "action": f"registration_{reg['status']}", "target": reg["id"], "note": reg["decision_note"]})
        save_stage(stage)
        self._json({"success": True})

    def serve_public_listings(self):
        """Return only explicitly advertised properties and only safe marketing fields."""
        stage = load_stage()
        properties = []
        for prop in stage.get("properties", []):
            listing = prop.get("public_listing") or {}
            occupied = any(t.get("property_id") == prop.get("id")
                           and t.get("status") in ("active", "renewal", "notice_given", "checkout")
                           for t in stage.get("tenancies", []))
            if occupied or prop.get("lifecycle_status") != "advertised" or not listing.get("description"):
                continue
            try:
                rent = int(listing.get("rent", prop.get("rent", 0)))
                beds = int(listing.get("beds", prop.get("beds", 0)))
            except (TypeError, ValueError):
                continue
            title = str(listing.get("title", prop.get("title", "")))[:160]
            area = str(listing.get("area", prop.get("area", "")))[:160]
            if not title or not area or rent < 0 or beds < 0:
                continue
            properties.append({
                "id": prop["id"], "title": title, "area": area, "beds": beds,
                "rent": rent, "description": str(listing["description"])[:3000],
                "availableFrom": str(listing.get("availableFrom", ""))[:30],
                "sample": False,
            })
        return self._json({"demo": not bool(properties), "properties": properties})

    def handle_party_action(self, data):
        """Agent creates a distinct Party record; no email-based merging or access grant."""
        stage = load_stage()
        if data.get("action", "create") != "create":
            return self._json({"error": "only party creation is supported"}, 400)
        kind = str(data.get("kind", "person"))
        if kind not in ("person", "organisation"):
            return self._json({"error": "kind must be person|organisation"}, 400)
        name = str(data.get("display_name", "")).strip()[:160]
        if not name:
            return self._json({"error": "display_name is required"}, 400)
        roles = data.get("roles", [])
        allowed = {"agent", "landlord", "tenant", "trades"}
        if not isinstance(roles, list) or not roles or any(not isinstance(r, str) or r not in allowed for r in roles):
            return self._json({"error": "roles must contain one or more supported roles"}, 400)
        pid_num = int(stage.get("next_party_id", 1))
        party = {
            "id": "party-" + str(pid_num),
            "kind": kind,
            "display_name": name,
            "legal_name": str(data.get("legal_name", "")).strip()[:160] or None,
            "email": str(data.get("email", "")).strip()[:254] or None,
            "phone": str(data.get("phone", "")).strip()[:40] or None,
            "address": str(data.get("address", "")).strip()[:300] or None,
            "roles": sorted(set(roles)),
            "status": "active",
            "notes": str(data.get("notes", "")).strip()[:1000],
            "account_id": None,
            "created_at": now(),
            "created_by": (self.user or {}).get("username", "agent"),
        }
        registration_id = str(data.get("registration_id", ""))[:100] or None
        registration = None
        if registration_id:
            registration = next((r for r in stage.get("registrations", [])
                                 if str(r.get("id")) == registration_id), None)
            if (kind != "person" or "landlord" not in party["roles"] or not registration
                    or registration.get("role") != "landlord" or registration.get("status") != "approved"):
                return self._json({"error": "link only an approved landlord registration to a landlord Party"}, 409)
            if registration.get("party_id"):
                return self._json({"error": "this registration is already linked to a Party"}, 409)
            party["source_registration_id"] = registration_id
            registration["party_id"] = party["id"]
            registration["party_linked_at"] = now()
        stage["next_party_id"] = pid_num + 1
        stage.setdefault("parties", []).append(party)
        self.audit(stage, {"actor": (self.user or {}).get("display_name", "agent"),
                           "action": "party_created", "target": party["id"],
                           "note": kind + ": " + name})
        save_stage(stage)
        return self._json({"success": True, "party": party})

    def handle_management_agreement_action(self, data):
        """Create or advance a dated management agreement for a landlord and properties."""
        transitions = {
            "draft": ("sent", "cancelled"),
            "sent": ("signed", "cancelled"),
            "signed": ("active", "ended"),
            "active": ("ended",),
            "ended": (),
            "cancelled": (),
        }
        stage = load_stage()
        action = str(data.get("action", "create"))
        if action == "create":
            landlord_id = str(data.get("landlord_party_id", ""))[:100]
            landlord = next((p for p in stage.get("parties", [])
                             if p.get("id") == landlord_id and p.get("status") == "active"
                             and "landlord" in p.get("roles", [])), None)
            if not landlord:
                return self._json({"error": "active landlord Party not found"}, 404)
            property_ids = data.get("property_ids", [])
            known = {p.get("id") for p in stage.get("properties", [])}
            if not isinstance(property_ids, list) or not property_ids:
                return self._json({"error": "select at least one property"}, 400)
            property_ids = list(dict.fromkeys(str(pid) for pid in property_ids))
            if any(pid not in known for pid in property_ids):
                return self._json({"error": "one or more properties were not found"}, 404)
            agreement_type = str(data.get("agreement_type", "full_management"))
            if agreement_type not in ("let_only", "full_management"):
                return self._json({"error": "invalid management agreement type"}, 400)
            try:
                fee_bps = int(data.get("management_fee_bps", 0))
            except (TypeError, ValueError):
                return self._json({"error": "management fee must be an integer basis point value"}, 400)
            if fee_bps < 0 or fee_bps > 10000:
                return self._json({"error": "management fee must be between 0 and 10000 basis points"}, 400)
            agreement_num = int(stage.get("next_management_agreement_id", 1))
            aid = "management-" + str(agreement_num)
            at = now()
            agreement = {
                "id": aid, "landlord_party_id": landlord_id, "property_ids": property_ids,
                "agreement_type": agreement_type, "management_fee_bps": fee_bps,
                "status": "draft", "signed_at": None, "ended_at": None,
                "evidence_note": str(data.get("evidence_note", "")).strip()[:1000],
                "created_at": at, "updated_at": at,
                "history": [{"from": None, "to": "draft", "at": at,
                             "by": (self.user or {}).get("username", "agent")}],
            }
            stage["next_management_agreement_id"] = agreement_num + 1
            stage.setdefault("management_agreements", []).append(agreement)
            self.audit(stage, {"actor": (self.user or {}).get("display_name", "agent"),
                               "action": "management_agreement_created", "target": aid,
                               "note": "Landlord " + landlord_id})
            save_stage(stage)
            return self._json({"success": True, "agreement": agreement})
        if action != "transition":
            return self._json({"error": "action must be create|transition"}, 400)
        aid = str(data.get("id", ""))[:100]
        agreement = next((a for a in stage.get("management_agreements", []) if a.get("id") == aid), None)
        if not agreement:
            return self._json({"error": "management agreement not found"}, 404)
        target = str(data.get("status", ""))
        current = agreement.get("status")
        if target not in transitions:
            return self._json({"error": "invalid management agreement status"}, 400)
        if target == current:
            return self._json({"success": True, "unchanged": True, "status": current})
        if target not in transitions.get(current, ()):
            return self._json({"error": "invalid management agreement transition"}, 409)
        signed_at = None
        ended_at = None
        if target == "signed":
            try:
                signed_at = datetime.strptime(str(data.get("signed_at", "")), "%Y-%m-%d").date().isoformat()
            except ValueError:
                return self._json({"error": "signed date in YYYY-MM-DD format is required"}, 400)
            if signed_at > datetime.now(timezone.utc).date().isoformat():
                return self._json({"error": "signed date cannot be in the future"}, 400)
            agreement["signed_at"] = signed_at
            agreement["evidence_note"] = str(data.get("evidence_note", agreement.get("evidence_note", ""))).strip()[:1000]
        if target == "active" and not agreement.get("signed_at"):
            return self._json({"error": "record the signed agreement before activating management"}, 409)
        if target == "active":
            for other in stage.get("management_agreements", []):
                if other.get("id") != aid and other.get("status") == "active" and set(other.get("property_ids", [])) & set(agreement.get("property_ids", [])):
                    return self._json({"error": "a property already has active management authority"}, 409)
        if target == "ended":
            try:
                ended_at = datetime.strptime(str(data.get("ended_at", "")), "%Y-%m-%d").date().isoformat()
            except ValueError:
                return self._json({"error": "end date in YYYY-MM-DD format is required"}, 400)
            if agreement.get("signed_at") and ended_at < agreement["signed_at"]:
                return self._json({"error": "end date cannot precede the signed date"}, 400)
            agreement["ended_at"] = ended_at
        at = now()
        agreement["status"] = target
        agreement["updated_at"] = at
        agreement.setdefault("history", []).append({
            "from": current, "to": target, "at": at, "signed_at": signed_at,
            "ended_at": ended_at, "by": (self.user or {}).get("username", "agent")
        })
        self.audit(stage, {"actor": (self.user or {}).get("display_name", "agent"),
                           "action": "management_agreement_status_changed", "target": aid,
                           "note": current + " -> " + target})
        save_stage(stage)
        return self._json({"success": True, "status": target, "updated_at": at})

    def handle_tenancy_action(self, data):
        """Agent creates a tenancy or advances its audited lifecycle state."""
        transitions = {
            "application": ("referencing", "cancelled"),
            "referencing": ("approved", "cancelled"),
            "approved": ("offer", "cancelled"),
            "offer": ("agreement", "cancelled"),
            "agreement": ("deposit", "cancelled"),
            "deposit": ("move_in_scheduled", "cancelled"),
            "move_in_scheduled": ("active", "cancelled"),
            "active": ("renewal", "notice_given"),
            "renewal": ("active", "notice_given"),
            "notice_given": ("active", "checkout"),
            "checkout": ("deposit_resolution", "former_tenant"),
            "deposit_resolution": ("former_tenant",),
            "former_tenant": (),
            "cancelled": (),
        }
        stage = load_stage()
        action = str(data.get("action", "create"))
        if action == "create":
            prop = self.find_prop(stage, str(data.get("property_id", "")))
            if not prop:
                return self._json({"error": "property not found"}, 404)
            tenant_ids = data.get("tenant_party_ids", [])
            landlord_ids = data.get("landlord_party_ids", [])
            parties = {p.get("id"): p for p in stage.get("parties", []) if p.get("status") == "active"}
            if (not isinstance(tenant_ids, list) or not tenant_ids or not isinstance(landlord_ids, list)
                    or not landlord_ids):
                return self._json({"error": "at least one tenant and landlord Party are required"}, 400)
            tenant_ids = list(dict.fromkeys(str(x) for x in tenant_ids))
            landlord_ids = list(dict.fromkeys(str(x) for x in landlord_ids))
            if any(pid not in parties or "tenant" not in parties[pid].get("roles", []) for pid in tenant_ids):
                return self._json({"error": "each tenant must be an active tenant Party"}, 400)
            if any(pid not in parties or "landlord" not in parties[pid].get("roles", []) for pid in landlord_ids):
                return self._json({"error": "each landlord must be an active landlord Party"}, 400)
            source_prospect_id = str(data.get("source_prospect_id", ""))[:100] or None
            if source_prospect_id:
                source_prospect = next((c for c in stage.get("cases", [])
                                        if str(c.get("id")) == source_prospect_id
                                        and c.get("type") == "enquiry"
                                        and c.get("role") in ("renter", "tenant")), None)
                if not source_prospect:
                    return self._json({"error": "source tenant enquiry not found"}, 404)
            try:
                rent = int(data.get("rent_amount_pence"))
                deposit = int(data.get("deposit_amount_pence", 0))
                start_date = datetime.strptime(str(data.get("start_date", "")), "%Y-%m-%d").date()
            except (TypeError, ValueError):
                return self._json({"error": "valid start_date and integer pence amounts are required"}, 400)
            frequency = str(data.get("rent_frequency", "monthly"))
            if rent <= 0 or deposit < 0 or frequency not in ("weekly", "fortnightly", "monthly", "quarterly", "annually"):
                return self._json({"error": "invalid rent, deposit or rent frequency"}, 400)
            tenancy_num = int(stage.get("next_tenancy_id", 1))
            tid = "tenancy-" + str(tenancy_num)
            at = now()
            tenancy = {
                "id": tid, "property_id": prop["id"],
                "source_prospect_id": source_prospect_id,
                "tenant_party_ids": tenant_ids, "landlord_party_ids": landlord_ids,
                "start_date": start_date.isoformat(), "end_date": None,
                "rent_amount_pence": rent, "rent_frequency": frequency,
                "deposit_amount_pence": deposit, "deposit_scheme": None,
                "deposit_reference": None, "agreement_status": "draft",
                "status": "application", "move_in_date": None, "notice_date": None,
                "checkout_date": None, "document_ids": [], "created_at": at, "updated_at": at,
                "history": [{"from": None, "to": "application", "at": at,
                             "by": (self.user or {}).get("username", "agent")}],
            }
            stage["next_tenancy_id"] = tenancy_num + 1
            stage.setdefault("tenancies", []).append(tenancy)
            self.audit(stage, {"actor": (self.user or {}).get("display_name", "agent"),
                               "action": "tenancy_created", "target": tid,
                               "note": "Property " + str(prop["id"])})
            save_stage(stage)
            return self._json({"success": True, "tenancy": tenancy})
        if action == "agreement":
            tid = str(data.get("id", ""))[:100]
            tenancy = next((t for t in stage.get("tenancies", []) if t.get("id") == tid), None)
            if not tenancy:
                return self._json({"error": "tenancy not found"}, 404)
            agreement_status = str(data.get("agreement_status", ""))
            if agreement_status not in ("draft", "sent", "signed", "cancelled"):
                return self._json({"error": "invalid agreement status"}, 400)
            signed_at = None
            if agreement_status == "signed":
                try:
                    signed_at = datetime.strptime(str(data.get("signed_at", "")), "%Y-%m-%d").date().isoformat()
                except ValueError:
                    return self._json({"error": "signed_at in YYYY-MM-DD format is required"}, 400)
            previous_agreement_status = tenancy.get("agreement_status", "draft")
            if previous_agreement_status == "signed" and (
                    agreement_status != "signed" or tenancy.get("agreement_signed_at") != signed_at):
                return self._json({"error": "signed agreements are immutable; record a separate variation"}, 409)
            if previous_agreement_status == agreement_status and tenancy.get("agreement_signed_at") == signed_at:
                return self._json({"success": True, "unchanged": True, "agreement_status": agreement_status})
            at = now()
            tenancy["agreement_status"] = agreement_status
            tenancy["agreement_signed_at"] = signed_at
            tenancy["updated_at"] = at
            tenancy.setdefault("history", []).append({
                "event": "agreement_status", "from": previous_agreement_status,
                "to": agreement_status, "at": at,
                "by": (self.user or {}).get("username", "agent")
            })
            self.audit(stage, {"actor": (self.user or {}).get("display_name", "agent"),
                               "action": "tenancy_agreement_status_changed", "target": tid,
                               "note": previous_agreement_status + " -> " + agreement_status})
            save_stage(stage)
            return self._json({"success": True, "agreement_status": agreement_status, "updated_at": at})
        if action != "transition":
            return self._json({"error": "action must be create|transition|agreement"}, 400)
        tid = str(data.get("id", ""))[:100]
        tenancy = next((t for t in stage.get("tenancies", []) if t.get("id") == tid), None)
        if not tenancy:
            return self._json({"error": "tenancy not found"}, 404)
        target = str(data.get("status", ""))
        current = tenancy.get("status")
        if target not in transitions:
            return self._json({"error": "invalid tenancy status"}, 400)
        if target == current:
            return self._json({"success": True, "unchanged": True, "status": current})
        if target not in transitions.get(current, ()):
            return self._json({"error": "invalid tenancy transition"}, 409)
        effective_date = str(data.get("effective_date", ""))
        if target in ("notice_given", "checkout"):
            try:
                parsed_date = datetime.strptime(effective_date, "%Y-%m-%d").date()
            except ValueError:
                return self._json({"error": "an effective_date in YYYY-MM-DD format is required"}, 400)
            if target == "notice_given" and parsed_date < datetime.strptime(tenancy["start_date"], "%Y-%m-%d").date():
                return self._json({"error": "notice date cannot predate the tenancy start"}, 400)
            if target == "checkout" and tenancy.get("notice_date") and parsed_date < datetime.strptime(tenancy["notice_date"], "%Y-%m-%d").date():
                return self._json({"error": "checkout date cannot predate the notice date"}, 400)
            field = "notice_date" if target == "notice_given" else "checkout_date"
            tenancy[field] = parsed_date.isoformat()
        if target == "former_tenant" and not tenancy.get("checkout_date"):
            return self._json({"error": "checkout must be recorded before ending the tenancy"}, 409)
        if target == "active":
            if tenancy.get("agreement_status") != "signed":
                return self._json({"error": "mark the agreement signed before activating the tenancy"}, 409)
            if tenancy.get("start_date") > datetime.now(timezone.utc).date().isoformat():
                return self._json({"error": "the tenancy start date has not arrived"}, 409)
            for other in stage.get("tenancies", []):
                if other.get("id") == tid or other.get("property_id") != tenancy.get("property_id"):
                    continue
                if other.get("status") in ("active", "renewal", "notice_given"):
                    return self._json({"error": "another tenancy is still active for this property"}, 409)
        if target == "former_tenant":
            tenancy["end_date"] = tenancy.get("checkout_date")
        prop = self.find_prop(stage, tenancy.get("property_id"))
        property_targets = {"active": ("let_agreed", "occupied"), "notice_given": ("occupied", "notice_given"),
                            "checkout": ("notice_given", "checkout"), "former_tenant": ("checkout", "void")}
        if target in property_targets:
            expected, next_property = property_targets[target]
            property_status = (prop or {}).get("lifecycle_status") or "onboarding"
            if not prop or property_status != expected:
                return self._json({"error": "advance the property to " + expected + " before this tenancy transition"}, 409)
            prop["lifecycle_status"] = next_property
            prop["lifecycle_status_at"] = now()
            prop.setdefault("lifecycle_history", []).append({
                "from": expected, "to": next_property, "at": prop["lifecycle_status_at"],
                "by": (self.user or {}).get("username", "agent")
            })
            self.audit(stage, {"actor": (self.user or {}).get("display_name", "agent"),
                               "action": "property_lifecycle_changed", "target": prop["id"],
                               "note": expected + " -> " + next_property + " (tenancy " + tid + ")"})
        if target == "active":
            tenancy["move_in_date"] = tenancy.get("start_date")
        at = now()
        tenancy["status"] = target
        tenancy["updated_at"] = at
        tenancy.setdefault("history", []).append({
            "from": current, "to": target, "at": at, "effective_date": effective_date or None,
            "by": (self.user or {}).get("username", "agent")
        })
        self.audit(stage, {"actor": (self.user or {}).get("display_name", "agent"),
                           "action": "tenancy_status_changed", "target": tid,
                           "note": current + " -> " + target})
        save_stage(stage)
        return self._json({"success": True, "status": target, "updated_at": at})

    def handle_property_action(self, data):
        """Agent-controlled property lifecycle transition and public listing draft update."""
        transitions = {
            "prospect": ("onboarding", "offboarded"),
            "onboarding": ("ready_to_market", "offboarded"),
            "ready_to_market": ("onboarding", "advertised", "offboarded"),
            "advertised": ("application", "void", "offboarded"),
            "application": ("advertised", "let_agreed", "void"),
            "let_agreed": ("occupied", "void"),
            "occupied": ("notice_given", "offboarded"),
            "notice_given": ("occupied", "checkout"),
            "checkout": ("void",),
            "void": ("remarketing", "offboarded"),
            "remarketing": ("advertised", "onboarding", "offboarded"),
            "offboarded": (),
        }
        stage = load_stage()
        pid = str(data.get("property_id", ""))[:100]
        prop = self.find_prop(stage, pid)
        if not prop:
            return self._json({"error": "property not found"}, 404)
        current = prop.get("lifecycle_status") or "onboarding"
        target = str(data.get("status", ""))[:40]
        if target not in transitions:
            return self._json({"error": "invalid property lifecycle status"}, 400)
        if target != current and target not in transitions.get(current, ()):
            return self._json({"error": "invalid property lifecycle transition"}, 409)
        description = data.get("description")
        listing = prop.setdefault("public_listing", {})
        old_description = listing.get("description", "")
        new_description = str(description)[:3000].strip() if description is not None else old_description
        description_changed = new_description != old_description
        if description is not None and description_changed:
            listing["description"] = new_description
        if target == "advertised":
            try:
                rent = int(prop.get("rent", 0))
                beds = int(prop.get("beds", 0))
            except (TypeError, ValueError):
                rent, beds = -1, -1
            if (not str(prop.get("title", "")).strip() or not str(prop.get("area", "")).strip()
                    or not listing.get("description") or rent < 0 or beds < 0):
                return self._json({"error": "add a public description and confirm listing details before advertising"}, 400)
            listing.update({"title": prop["title"], "area": prop["area"],
                            "beds": beds, "rent": rent})
        if target == current and not description_changed:
            return self._json({"success": True, "unchanged": True, "status": current})
        at = now()
        if target != current:
            prop["lifecycle_status"] = target
            prop["lifecycle_status_at"] = at
            prop.setdefault("lifecycle_history", []).append({
                "from": current, "to": target, "at": at,
                "by": (self.user or {}).get("username", "agent")
            })
            action, note = "property_lifecycle_changed", current + " -> " + target
        else:
            action, note = "property_listing_updated", "Public description updated"
        self.audit(stage, {"actor": (self.user or {}).get("display_name", "agent"),
                           "action": action, "target": pid, "note": note})
        save_stage(stage)
        return self._json({"success": True, "status": target, "updated_at": at})

    def handle_prospect_action(self, data):
        """Advance a tenant enquiry or landlord/trades application through its acquisition pipeline."""
        stage = load_stage()
        kind = str(data.get("kind", ""))
        rid = str(data.get("id", ""))[:100]
        next_stage = str(data.get("stage", ""))[:40]
        options = {
            "tenant": ("enquiry", "viewing", "application", "referencing", "approved", "offer", "converted", "closed"),
            "landlord": ("lead", "conversation", "valuation", "proposal", "terms", "signed", "onboarding", "active", "closed"),
            "trades": ("applicant", "credentials_submitted", "checked", "approved", "available", "suspended", "rejected"),
        }
        if kind not in options:
            return self._json({"error": "kind must be tenant|landlord|trades"}, 400)
        if next_stage not in options[kind]:
            return self._json({"error": "invalid stage for prospect type"}, 400)
        if kind == "tenant":
            record = next((c for c in stage.get("cases", [])
                           if str(c.get("id")) == rid and c.get("type") == "enquiry"
                           and c.get("role") in ("renter", "tenant")), None)
            default = "enquiry"
        else:
            record = next((r for r in stage.get("registrations", [])
                           if str(r.get("id")) == rid and r.get("role") == kind), None)
            if kind == "trades":
                default = "rejected" if record and record.get("status") == "rejected" else (
                    "approved" if record and record.get("status") == "approved" else "applicant")
            else:
                default = "closed" if record and record.get("status") == "rejected" else (
                    "onboarding" if record and record.get("status") == "approved" else "lead")
        if not record:
            return self._json({"error": "prospect not found"}, 404)
        if kind == "landlord" and next_stage in ("signed", "onboarding", "active"):
            party_id = record.get("party_id")
            required_agreement_status = "signed" if next_stage == "signed" else "active"
            if record.get("status") != "approved" or not party_id or not any(
                    a.get("landlord_party_id") == party_id and a.get("status") in
                    (("signed", "active") if required_agreement_status == "signed" else ("active",))
                    for a in stage.get("management_agreements", [])):
                return self._json({"error": "an approved landlord Party needs the matching signed management agreement"}, 409)
        if kind == "landlord" and next_stage in ("signed", "onboarding", "active") and record.get("status") != "approved":
            return self._json({"error": "approve the landlord registration before advancing this stage"}, 409)
        previous = record.get("prospect_stage") or default
        if kind == "trades":
            transitions = {
                "applicant": ("credentials_submitted", "rejected"),
                "credentials_submitted": ("checked", "rejected"),
                "checked": ("approved", "rejected"),
                "approved": ("available", "suspended"),
                "available": ("suspended",),
                "suspended": ("available", "rejected"),
                "rejected": (),
            }
            if next_stage != previous and next_stage not in transitions.get(previous, ()):
                return self._json({"error": "invalid trades lifecycle transition"}, 409)
            if next_stage in ("approved", "available") and record.get("status") != "approved":
                return self._json({"error": "approve the trades registration before advancing this stage"}, 409)
            if next_stage == "checked":
                at_checked = now()
                record["credentials_checked_at"] = at_checked
                record["credentials_checked_by"] = (self.user or {}).get("username", "agent")
        if kind == "landlord" and next_stage in ("signed", "onboarding", "active") and record.get("status") != "approved":
            return self._json({"error": "approve the landlord registration before advancing this stage"}, 409)
        if previous == next_stage:
            return self._json({"success": True, "unchanged": True, "stage": next_stage})
        at = now()
        record.setdefault("prospect_history", []).append({
            "from": previous, "to": next_stage, "at": at,
            "by": (self.user or {}).get("username", "agent")
        })
        record["prospect_stage"] = next_stage
        record["prospect_stage_at"] = at
        self.audit(stage, {"actor": (self.user or {}).get("display_name", "agent"),
                           "action": "prospect_stage_changed", "target": rid,
                           "note": kind + ": " + previous + " -> " + next_stage})
        save_stage(stage)
        self._json({"success": True, "stage": next_stage, "updated_at": at})

    # ---------- enquiries (public connect form) ----------
    def handle_enquiry(self, data):
        stage = load_stage()
        role = data.get("role") if data.get("role") in ("landlord", "trades", "renter") else "other"
        t = self.triage(data.get("message", ""))
        case = {
            "id": stage.get("next_case_id", 490),
            "type": "enquiry",
            "property_id": data.get("property_id") if self.find_prop(stage, data.get("property_id")) else None,
            "role": role,
            "name": str(data.get("name", "Someone"))[:100],
            "email": str(data.get("email", ""))[:254],
            "phone": str(data.get("phone", ""))[:30],
            "message": str(data.get("message", ""))[:3000],
            "status": "new",
            "triage": t,
            "submitted_at": now(),
        }
        stage["next_case_id"] = case["id"] + 1
        stage.setdefault("cases", []).append(case)
        save_stage(stage)
        self._json({"success": True, "case_id": case["id"], "triage": t})

    # ---------- tenant issues: REPORT → dispatch ----------
    def handle_tenant_issue(self, data):
        stage = load_stage()
        prop = self.find_prop(stage, data.get("property_id"))
        message = str(data.get("message", ""))[:3000]
        issuer = self.user or {}
        name = issuer.get("display_name") if issuer.get("role") == "tenant" else str(data.get("name", "Tenant"))[:100]
        t = self.triage(message)
        case = {
            "id": stage.get("next_case_id", 490),
            "type": "issue",
            "property_id": prop["id"] if prop else None,
            "role": "tenant",
            "name": name or "Tenant",
            "email": str(data.get("email", ""))[:254],
            "message": message,
            "status": "reported",
            "triage": t,
            "submitted_at": now(),
        }
        stage["next_case_id"] = case["id"] + 1
        stage.setdefault("cases", []).append(case)
        try:
            docs = self.store_case_attachments(stage, case, data.get("attachments"), name or "Tenant")
        except ValueError as exc:
            return self._json({"error": str(exc)}, 400)
        job = None
        if t["category"] == "maintenance":
            stage.setdefault("jobs", [])
            job = {
                "id": f"job-{max([int(j['id'].split('-')[1]) for j in stage['jobs']] or [0]) + 1}",
                "case_id": case["id"],
                "property_id": case["property_id"],
                "message": message,
                "triage": t,
                "required_trade": t.get("trade") if t.get("trade") not in (None, "other") else None,
                "status": "open",
                "assigned_to": None,
                "invoice_pence": None,
                "created_at": now(),
            }
            if case.get("document_ids"):
                job["evidence_document_ids"] = list(case["document_ids"])
            stage["jobs"].append(job)
            case["status"] = "dispatched"
        self.audit(stage, {"actor": "system", "action": "case_created", "target": case["id"],
                           "note": f"{t['category']}/{t.get('trade','-')} urgency {t['urgency']}"})
        save_stage(stage)
        self._json({"success": True, "case_id": case["id"], "triage": t,
                    "job_id": job["id"] if job else None,
                    "document_ids": [d["id"] for d in docs] if docs else []})

    # ---------- trades: BOOK → complete → settle or escalate ----------
    def credential_check(self, job, tradesperson):
        """P2: gate jobs whose required trade needs a verified certificate."""
        req = job.get("required_trade")
        if not req:
            return {"ok": True, "reason": None}
        prof = TRADE_PROFILES.get(tradesperson)
        if not prof:
            return {"ok": False, "reason": f"{tradesperson} has no verified profile; job needs {req}"}
        if req not in prof["trades"] and not (req == "gas" and prof.get("gas_safe")):
            return {"ok": False, "reason": f"credentials list {', '.join(prof['trades']) or 'nothing'} — job needs {req}"}
        return {"ok": True, "reason": None}

    def handle_job_action(self, data):
        stage = load_stage()
        action = data.get("action")
        job = next((j for j in stage.get("jobs", []) if j["id"] == data.get("id")), None)
        if not job:
            return self._json({"error": "job not found"}, 404)
        role = (self.user or {}).get("role")
        AGENT_ONLY = {"assign", "request_quote", "approve_quote", "decline_quote",
                      "send_to_landlord", "verify_approve", "verify_decline"}
        TRADES_ONLY = {"accept", "start", "complete", "release", "submit_quote"}
        if action in AGENT_ONLY and role != "agent":
            return self._json({"error": "agent-only move"}, 403)
        if action in TRADES_ONLY and role != "trades":
            return self._json({"error": "tradesperson-only move"}, 403)
        actor = (self.user or {}).get("display_name") or "Unknown"
        if action == "release" and actor != job.get("assigned_to"):
            return self._json({"error": "not your job to release"}, 403)

        if action == "accept":
            chk = self.credential_check(job, actor)
            if chk["ok"]:
                job["status"] = "in_progress"
                job["assigned_to"] = actor
                self.sync_case(stage, job["case_id"], "in_progress")
                self.post_msg(stage, job["case_id"], f"{actor} took this job and will get in touch to arrange access.", to=("tenant",))
                self.audit(stage, {"actor": actor, "action": "job_booked", "target": job["id"]})
            else:
                # human decision required before a cert-gated job can be booked
                job["status"] = "pending_verification"
                job["requested_by"] = actor
                job["gate_reason"] = chk["reason"]
                self.audit(stage, {"actor": actor, "action": "job_booking_blocked_pending_verification",
                                   "target": job["id"], "note": chk["reason"]})
        elif action == "verify_approve" and job["status"] == "pending_verification":
            job["status"] = "in_progress"
            job["assigned_to"] = job.pop("requested_by", None)
            job.pop("gate_reason", None)
            job["override_by"] = "agent"
            self.sync_case(stage, job["case_id"], "in_progress")
            self.audit(stage, {"actor": "agent", "action": "booking_overridden", "target": job["id"]})
        elif action == "verify_decline" and job["status"] == "pending_verification":
            job["status"] = "open"
            job.pop("requested_by", None)
            job.pop("gate_reason", None)
            self.audit(stage, {"actor": "agent", "action": "booking_declined", "target": job["id"]})
        elif action == "release" and job["status"] in ("in_progress", "assigned", "quote_requested") and actor == (job.get("assigned_to") or job.get("requested_by")):
            job["status"] = "open"
            job["assigned_to"] = None
            job.pop("requested_by", None)
            self.post_msg(stage, job["case_id"], f"{actor} handed this job back to the board.", to=("tenant",))
            self.audit(stage, {"actor": actor, "action": "job_returned", "target": job["id"]})
        # ---- agent choreography: direct the dance instead of waiting for it ----
        elif action == "assign" and self.user["role"] == "agent" and job["status"] in ("open", "quote_requested", "quoted", "pending_verification"):
            who = str(data.get("tradesperson", ""))[:100]
            known = {t["company"] for t in self.approved_trades(stage)}
            if who not in known:
                return self._json({"error": f"{who or 'nobody'} is not an approved tradesperson — approve their registration first"}, 400)
            job["status"] = "assigned"
            job["assigned_to"] = who
            c = self.post_msg(stage, job["case_id"], f"{who} has been put on this job by the agency.", to=("tenant", "trades"))
            self.audit(stage, {"actor": "agent", "action": "job_assigned", "target": job["id"], "note": who})
        elif action in ("request_quote",) and self.user["role"] == "agent" and job["status"] in ("open", "assigned"):
            who = str(data.get("tradesperson", ""))[:100]
            known = {t["company"] for t in self.approved_trades(stage)}
            if who not in known:
                return self._json({"error": f"{who or 'nobody'} is not an approved tradesperson"}, 400)
            job["status"] = "quote_requested"
            job["assigned_to"] = who
            self.post_msg(stage, job["case_id"], f"Quote requested from {who} — the work starts once the agency approves a price.", to=("trades",))
            self.audit(stage, {"actor": "agent", "action": "quote_requested", "target": job["id"], "note": who})
        elif action == "submit_quote" and job["status"] == "quote_requested" and actor == job.get("assigned_to"):
            job["quotes"] = job.get("quotes", [])
            q = {"tradesperson": actor, "pence": max(0, int(data.get("quote_pence", 0))),
                 "note": str(data.get("note", ""))[:500], "at": now(), "status": "pending"}
            job["quotes"].append(q)
            job["status"] = "quoted"
            self.sync_case(stage, job["case_id"], "quoted")
            self.post_msg(stage, job["case_id"], f"{actor} quoted £{q['pence']/100:.2f}"
                          + (f" — {q['note']}" if q["note"] else "") + ". Waiting on the agency to approve.", to=("tenant",))
            self.audit(stage, {"actor": actor, "action": "quote_submitted", "target": job["id"], "note": f"£{q['pence']/100:.2f}"})
        elif action == "approve_quote" and self.user["role"] == "agent" and job["status"] == "quoted":
            pend = [q for q in job.get("quotes", []) if q["status"] == "pending"]
            if not pend:
                return self._json({"error": "no pending quote"}, 400)
            q = max(pend, key=lambda x: x.get("at", ""))
            q["status"] = "approved"
            job["approved_quote_pence"] = q["pence"]
            job["status"] = "in_progress"
            self.sync_case(stage, job["case_id"], "in_progress")
            self.post_msg(stage, job["case_id"], f"Quote of £{q['pence']/100:.2f} approved — {job['assigned_to']} can start.", to=("tenant", "trades"))
            self.audit(stage, {"actor": "agent", "action": "quote_approved", "target": job["id"], "note": f"£{q['pence']/100:.2f}"})
        elif action == "decline_quote" and self.user["role"] == "agent" and job["status"] == "quoted":
            for q in job.get("quotes", []):
                if q["status"] == "pending":
                    q["status"] = "declined"
            job["status"] = "quote_requested"
            self.sync_case(stage, job["case_id"], "dispatched")
            self.post_msg(stage, job["case_id"], "Quote declined — " + str(data.get("reason", "price not right"))[:300]
                          + ". Please re-quote or a different trade will be asked.", to=("trades",))
            self.audit(stage, {"actor": "agent", "action": "quote_declined", "target": job["id"]})
        elif action == "send_to_landlord" and self.user["role"] == "agent":
            if job["status"] not in ("paid", "in_progress") or not job.get("invoice_pence"):
                return self._json({"error": "nothing to send — job has no invoice yet"}, 400)
            prop = self.find_prop(stage, job["property_id"]) or {}
            stage.setdefault("approvals", [])
            stage["approvals"].append({
                "id": f"appr-{len(stage['approvals']) + 1}", "job_id": job["id"],
                "property_id": job["property_id"], "landlord": prop.get("landlord", "Landlord"),
                "amount_pence": job["invoice_pence"], "reason": job["message"],
                "evidence": {"tradesperson": job.get("assigned_to"), "job_created": job.get("created_at"),
                             "work_completed": job.get("completed_at")},
                "status": "pending", "requested_at": now(),
                "sent_by_agent": True})
            job["status"] = "awaiting_approval"
            self.sync_case(stage, job["case_id"], "awaiting_approval")
            self.post_msg(stage, job["case_id"], "The agency has sent your invoice to the landlord for sign-off.", to=("trades",))
            self.audit(stage, {"actor": "agent", "action": "invoice_sent_to_landlord", "target": job["id"],
                               "note": f"£{job['invoice_pence']/100:.2f}"})
        elif action == "start" and job["status"] == "assigned" and actor == job.get("assigned_to"):
            job["status"] = "in_progress"
            self.sync_case(stage, job["case_id"], "in_progress")
            self.audit(stage, {"actor": actor, "action": "job_started", "target": job["id"]})
        elif action == "complete" and job["status"] == "in_progress":
            job["invoice_pence"] = max(0, int(data.get("invoice_pence", 0)))
            job["completed_at"] = now()
            limit = stage.get("authority", {}).get("standing_limit_pence", 15000)
            if job["invoice_pence"] > limit:
                prop = self.find_prop(stage, job["property_id"]) or {}
                stage.setdefault("approvals", [])
                appr = {
                    "id": f"appr-{len(stage['approvals']) + 1}",
                    "job_id": job["id"],
                    "property_id": job["property_id"],
                    "landlord": prop.get("landlord", "Landlord"),
                    "amount_pence": job["invoice_pence"],
                    "reason": job["message"],
                    "evidence": {
                        "tradesperson": job.get("assigned_to"),
                        "job_created": job.get("created_at"),
                        "work_completed": job["completed_at"],
                    },
                    "status": "pending",
                    "requested_at": now(),
                }
                stage["approvals"].append(appr)
                job["status"] = "awaiting_approval"
                self.sync_case(stage, job["case_id"], "awaiting_approval")
                self.post_msg(stage, job["case_id"], f"Work done. Invoice £{job['invoice_pence']/100:.2f} is above the standing authority, so the landlord will sign it off.", to=("tenant", "landlord"))
                self.audit(stage, {"actor": job.get("assigned_to") or "trades", "action": "invoice_submitted",
                                   "target": job["id"], "note": f"£{job['invoice_pence']/100:.2f} above standing authority"})
            else:
                job["status"] = "paid"
                job["paid_at"] = now()
                self.sync_case(stage, job["case_id"], "resolved")
                self.audit(stage, {"actor": "system", "action": "invoice_auto_settled",
                                   "target": job["id"], "note": f"£{job['invoice_pence']/100:.2f} under limit"})
        else:
            return self._json({"error": f"invalid action {action} for status {job['status']}"}, 400)

        save_stage(stage)
        self._json({"success": True, "job": job})

    # ---------- landlord: APPROVE / REJECT with reason ----------
    def handle_landlord_action(self, data):
        stage = load_stage()
        appr = next((a for a in stage.get("approvals", []) if a["id"] == data.get("id")), None)
        if not appr:
            return self._json({"error": "approval not found"}, 404)
        if (self.user or {}).get("role") != "agent" and appr["landlord"] != (self.user or {}).get("display_name"):
            return self._json({"error": "not your approval"}, 403)
        if appr["status"] != "pending":
            return self._json({"error": "already decided"}, 409)
        action = data.get("action")
        if action not in ("approve", "reject"):
            return self._json({"error": "action must be approve|reject"}, 400)
        appr["status"] = "approved" if action == "approve" else "rejected"
        appr["reason_given"] = str(data.get("reason", ""))[:300] if action == "reject" else None
        if action == "reject" and not appr["reason_given"]:
            return self._json({"error": "a reason is required when rejecting"}, 400)
        appr["decided_at"] = now()
        job = next((j for j in stage.get("jobs", []) if j["id"] == appr["job_id"]), None)
        if job:
            self.post_msg(stage, next((j["case_id"] for j in stage["jobs"] if j["id"] == job["id"]), None) or -1,
                          ("The landlord approved " if appr["status"] == "approved" else "The landlord declined the invoice — ")
                          + f"£{appr['amount_pence']/100:.2f}" + (f". Reason: {appr['reason_given']}" if appr.get("reason_given") else "."),
                          to=("tenant", "trades", "landlord"))
            if appr["status"] == "approved":
                job["status"] = "paid"
                job["paid_at"] = now()
                self.sync_case(stage, job["case_id"], "resolved")
            else:
                job["status"] = "rejected"
                self.sync_case(stage, job["case_id"], "declined")
                # P1: rejection creates agent work, never a silent death
                stage.setdefault("cases", []).append({
                    "id": stage.get("next_case_id", 490),
                    "type": "agent_task",
                    "property_id": appr.get("property_id"),
                    "role": "agent",
                    "name": "System",
                    "message": f"Landlord declined {job['id']} (£{appr['amount_pence']/100:.2f}): {appr['reason_given']}. Decide next step with the tradesperson and tenant.",
                    "status": "new",
                    "submitted_at": now(),
                })
                stage["next_case_id"] = stage.get("next_case_id", 490) + 1
        self.audit(stage, {"actor": appr["landlord"], "action": f"invoice_{appr['status']}",
                           "target": appr["id"], "note": appr.get("reason_given")})
        save_stage(stage)
        self._json({"success": True, "approval": appr})

    # ---------- agent: close with reason ----------
    def safe_rent_entry(self, entry):
        """Compute a ledger balance without storing derived status."""
        due = int(entry.get("amount_due_pence", 0)) + sum(int(a.get("amount_pence", 0)) for a in entry.get("adjustments", []))
        received = sum(int(p.get("amount_pence", 0)) for p in entry.get("payments", []))
        balance = due - received
        status = "paid" if balance == 0 else ("partial" if received else "due")
        if balance > 0 and entry.get("due_date") and entry["due_date"] < datetime.now(timezone.utc).date().isoformat():
            status = "overdue"
        return {**entry, "amount_due_pence": due, "amount_received_pence": received,
                "balance_pence": balance, "status": status}

    def safe_compliance_record(self, record):
        """Derive expiry and reminder states from explicit dates."""
        today = datetime.now(timezone.utc).date()
        expiry = None
        if record.get("expiry_date"):
            try:
                expiry = datetime.strptime(record["expiry_date"], "%Y-%m-%d").date()
            except ValueError:
                expiry = None
        superseded = bool(record.get("superseded_by"))
        if superseded:
            status = "superseded"
        elif record.get("record_status") == "missing":
            status = "missing"
        elif expiry and expiry < today:
            status = "expired"
        elif expiry and expiry <= today + timedelta(days=30):
            status = "expiring_soon"
        else:
            status = "current"
        reminder_due = False
        if record.get("reminder_date") and not superseded:
            try:
                reminder_due = datetime.strptime(record["reminder_date"], "%Y-%m-%d").date() <= today
            except ValueError:
                pass
        return {**record, "status": status, "reminder_due": reminder_due}

    def handle_compliance_action(self, data):
        """Record missing evidence or a dated compliance record and retain replaced versions."""
        stage = load_stage()
        prop_id = str(data.get("property_id", ""))[:100]
        prop = self.find_prop(stage, prop_id)
        if not prop:
            return self._json({"error": "property not found"}, 404)
        requirement = str(data.get("requirement_type", ""))
        allowed = {"gas_safety", "eicr", "epc", "smoke_co_alarms",
                   "deposit_protection", "right_to_rent", "tenancy_agreement",
                   "inventory", "landlord_authority", "trades_credentials", "other"}
        if requirement not in allowed:
            return self._json({"error": "invalid compliance requirement type"}, 400)
        action = str(data.get("action", "record"))
        if action not in ("record", "missing"):
            return self._json({"error": "action must be record|missing"}, 400)
        issue = expiry = reminder = None
        document_id = str(data.get("document_id", ""))[:100] or None
        if action == "record":
            try:
                issue = datetime.strptime(str(data.get("issue_date", "")), "%Y-%m-%d").date()
            except ValueError:
                return self._json({"error": "issue date in YYYY-MM-DD format is required"}, 400)
            if issue > datetime.now(timezone.utc).date():
                return self._json({"error": "issue date cannot be in the future"}, 400)
            if data.get("expiry_date"):
                try:
                    expiry = datetime.strptime(str(data.get("expiry_date")), "%Y-%m-%d").date()
                except ValueError:
                    return self._json({"error": "expiry date must use YYYY-MM-DD"}, 400)
                if expiry <= issue:
                    return self._json({"error": "expiry date must be after issue date"}, 400)
            if document_id and not any(d.get("id") == document_id for d in stage.get("documents", [])):
                return self._json({"error": "document not found"}, 404)
        if data.get("reminder_date"):
            try:
                reminder = datetime.strptime(str(data.get("reminder_date")), "%Y-%m-%d").date()
            except ValueError:
                return self._json({"error": "reminder date must use YYYY-MM-DD"}, 400)
        records = stage.setdefault("compliance_records", [])
        num = int(stage.get("next_compliance_record_id", 1))
        rid = "compliance-" + str(num)
        at = now()
        record = {
            "id": rid, "property_id": prop_id, "requirement_type": requirement,
            "record_status": "missing" if action == "missing" else "recorded",
            "issue_date": issue.isoformat() if issue else None,
            "expiry_date": expiry.isoformat() if expiry else None,
            "reminder_date": reminder.isoformat() if reminder else None,
            "document_id": document_id,
            "notes": str(data.get("notes", "")).strip()[:1000],
            "created_at": at, "created_by": (self.user or {}).get("username", "agent"),
        }
        for prior in records:
            if prior.get("property_id") == prop_id and prior.get("requirement_type") == requirement and not prior.get("superseded_by"):
                prior["superseded_by"] = rid
                prior["superseded_at"] = at
        records.append(record)
        stage["next_compliance_record_id"] = num + 1
        self.audit(stage, {"actor": (self.user or {}).get("display_name", "Agent"),
                           "action": "compliance_" + action, "target": rid,
                           "note": requirement + " · " + prop_id})
        save_stage(stage)
        return self._json({"success": True, "record": self.safe_compliance_record(record)})

    def handle_landlord_statement_action(self, data):
        """Create an immutable landlord period snapshot from recorded rent and paid jobs."""
        stage = load_stage()
        landlord_id = str(data.get("landlord_party_id", ""))[:100]
        landlord = next((p for p in stage.get("parties", []) if p.get("id") == landlord_id
                         and "landlord" in p.get("roles", [])), None)
        if not landlord:
            return self._json({"error": "landlord Party not found"}, 404)
        try:
            start = datetime.strptime(str(data.get("period_start", "")), "%Y-%m-%d").date()
            end = datetime.strptime(str(data.get("period_end", "")), "%Y-%m-%d").date()
        except ValueError:
            return self._json({"error": "period start and end dates are required"}, 400)
        if end < start:
            return self._json({"error": "period end cannot precede period start"}, 400)
        start_iso, end_iso = start.isoformat(), end.isoformat()
        statements = stage.setdefault("landlord_statements", [])
        duplicate = next((s for s in statements if s.get("landlord_party_id") == landlord_id
                          and s.get("period_start") == start_iso and s.get("period_end") == end_iso), None)
        if duplicate:
            return self._json({"error": "a statement already exists for this landlord and period",
                               "statement": duplicate}, 409)
        property_ids = sorted({pid for a in stage.get("management_agreements", [])
                                if a.get("landlord_party_id") == landlord_id
                                and a.get("status") in ("active", "ended")
                                and (not a.get("ended_at") or a.get("ended_at") >= start_iso)
                                and (not a.get("created_at") or str(a.get("created_at"))[:10] <= end_iso)
                                for pid in a.get("property_ids", [])})
        if not property_ids:
            return self._json({"error": "no managed properties found for this landlord"}, 409)
        rent_lines = []
        for entry in stage.get("rent_ledger_entries", []):
            if entry.get("property_id") not in property_ids:
                continue
            for payment in entry.get("payments", []):
                paid_date = str(payment.get("received_date", ""))
                if start_iso <= paid_date <= end_iso and payment.get("landlord_party_id") == landlord_id:
                    rent_lines.append({
                        "rent_entry_id": entry.get("id"), "tenancy_id": entry.get("tenancy_id"),
                        "property_id": entry.get("property_id"), "received_date": paid_date,
                        "rent_received_pence": int(payment.get("amount_pence", 0)),
                        "agency_fee_pence": int(payment.get("agency_fee_pence", 0)),
                    })
        maintenance_lines = []
        for job in stage.get("jobs", []):
            paid_date = str(job.get("paid_at", ""))[:10]
            covered = any(a.get("landlord_party_id") == landlord_id
                           and job.get("property_id") in a.get("property_ids", [])
                           and a.get("status") in ("active", "ended")
                           and (not a.get("created_at") or str(a.get("created_at"))[:10] <= paid_date)
                           and (not a.get("ended_at") or a.get("ended_at") >= paid_date)
                           for a in stage.get("management_agreements", []))
            if covered and job.get("property_id") in property_ids and job.get("status") == "paid" and start_iso <= paid_date <= end_iso:
                maintenance_lines.append({
                    "job_id": job.get("id"), "property_id": job.get("property_id"),
                    "paid_date": paid_date, "amount_pence": int(job.get("invoice_pence") or 0),
                })
        gross = sum(x["rent_received_pence"] for x in rent_lines)
        fees = sum(x["agency_fee_pence"] for x in rent_lines)
        maintenance = sum(x["amount_pence"] for x in maintenance_lines)
        num = int(stage.get("next_landlord_statement_id", 1))
        at = now()
        statement = {
            "id": "statement-" + str(num), "landlord_party_id": landlord_id,
            "period_start": start_iso, "period_end": end_iso,
            "property_ids": property_ids, "rent_lines": rent_lines,
            "maintenance_lines": maintenance_lines,
            "rent_received_pence": gross, "agency_fee_pence": fees,
            "maintenance_pence": maintenance,
            "net_payout_pence": gross - fees - maintenance,
            "created_at": at, "created_by": (self.user or {}).get("username", "agent"),
        }
        stage["next_landlord_statement_id"] = num + 1
        statements.append(statement)
        self.audit(stage, {"actor": (self.user or {}).get("display_name", "Agent"),
                           "action": "landlord_statement_created", "target": statement["id"],
                           "note": start_iso + " to " + end_iso})
        save_stage(stage)
        return self._json({"success": True, "statement": statement})

    def handle_rent_ledger_action(self, data):
        """Create rent schedules and record manual payments or adjustments."""
        stage = load_stage()
        action = str(data.get("action", ""))
        entries = stage.get("rent_ledger_entries", [])
        if action == "generate":
            tenancy_id = str(data.get("tenancy_id", ""))[:100]
            tenancy = next((t for t in stage.get("tenancies", []) if t.get("id") == tenancy_id), None)
            if not tenancy:
                return self._json({"error": "tenancy not found"}, 404)
            if tenancy.get("status") not in ("move_in_scheduled", "active", "renewal", "notice_given"):
                return self._json({"error": "rent schedule requires a move-in scheduled or active tenancy"}, 409)
            if tenancy.get("agreement_status") != "signed":
                return self._json({"error": "signed tenancy agreement required"}, 409)
            try:
                first_due = datetime.strptime(str(data.get("first_due_date", "")), "%Y-%m-%d").date()
                periods = int(data.get("periods", 1))
            except (ValueError, TypeError):
                return self._json({"error": "first due date and period count are required"}, 400)
            if not 1 <= periods <= 36:
                return self._json({"error": "periods must be between 1 and 36"}, 400)
            rent = int(tenancy.get("rent_amount_pence", 0))
            if rent <= 0:
                return self._json({"error": "tenancy rent must be greater than zero"}, 409)
            frequency = tenancy.get("rent_frequency", "monthly")
            months = {"monthly": 1, "quarterly": 3, "annually": 12}
            days = {"weekly": 7, "fortnightly": 14}
            if frequency not in months and frequency not in days:
                return self._json({"error": "unsupported rent frequency"}, 409)
            if "rent_ledger_entries" not in stage:
                stage["rent_ledger_entries"] = entries
            existing_dates = {x.get("due_date") for x in entries if x.get("tenancy_id") == tenancy_id}
            next_num = int(stage.get("next_rent_ledger_id", 1))
            created = []
            for n in range(periods):
                if frequency in days:
                    due = first_due + timedelta(days=days[frequency] * n)
                else:
                    index = first_due.year * 12 + (first_due.month - 1) + months[frequency] * n
                    year, month0 = divmod(index, 12)
                    month = month0 + 1
                    day = min(first_due.day, calendar.monthrange(year, month)[1])
                    due = first_due.replace(year=year, month=month, day=day)
                due_iso = due.isoformat()
                if due_iso in existing_dates:
                    continue
                at = now()
                entry = {
                    "id": "rent-" + str(next_num), "tenancy_id": tenancy_id,
                    "property_id": tenancy.get("property_id"), "due_date": due_iso,
                    "amount_due_pence": rent, "payments": [], "adjustments": [],
                    "created_at": at, "updated_at": at,
                }
                entries.append(entry)
                created.append(entry)
                existing_dates.add(due_iso)
                next_num += 1
            stage["next_rent_ledger_id"] = next_num
            if created:
                self.audit(stage, {"actor": (self.user or {}).get("display_name", "Agent"),
                                   "action": "rent_schedule_created", "target": tenancy_id,
                                   "note": str(len(created)) + " rent periods"})
                save_stage(stage)
            return self._json({"success": True, "created": [self.safe_rent_entry(x) for x in created],
                               "skipped_duplicates": periods - len(created)})
        entry_id = str(data.get("entry_id", ""))[:100]
        entry = next((x for x in entries if x.get("id") == entry_id), None)
        if not entry:
            return self._json({"error": "rent ledger entry not found"}, 404)
        if action == "receipt":
            try:
                amount = int(data.get("amount_pence", 0))
                received_date = datetime.strptime(str(data.get("received_date", "")), "%Y-%m-%d").date()
            except (ValueError, TypeError):
                return self._json({"error": "receipt amount and date are required"}, 400)
            current = self.safe_rent_entry(entry)
            if amount <= 0 or amount > current["balance_pence"]:
                return self._json({"error": "receipt must be positive and no greater than the outstanding balance"}, 400)
            if received_date > datetime.now(timezone.utc).date():
                return self._json({"error": "receipt date cannot be in the future"}, 400)
            payment = {
                "amount_pence": amount, "received_date": received_date.isoformat(),
                "note": str(data.get("note", "")).strip()[:500], "recorded_at": now(),
                "recorded_by": (self.user or {}).get("username", "agent"),
                "agency_fee_pence": 0, "management_fee_bps": 0,
                "management_agreement_id": None,
            }
            agreement = next((a for a in reversed(stage.get("management_agreements", []))
                              if a.get("status") == "active" and a.get("agreement_type") == "full_management"
                              and entry.get("property_id") in a.get("property_ids", [])), None)
            if agreement:
                fee_bps = int(agreement.get("management_fee_bps", 0))
                payment["agency_fee_pence"] = (amount * fee_bps + 5000) // 10000
                payment["management_fee_bps"] = fee_bps
                payment["management_agreement_id"] = agreement.get("id")
                payment["landlord_party_id"] = agreement.get("landlord_party_id")
            entry.setdefault("payments", []).append(payment)
        elif action == "adjustment":
            try:
                amount = int(data.get("amount_pence", 0))
            except (ValueError, TypeError):
                return self._json({"error": "adjustment must be an integer pence amount"}, 400)
            reason = str(data.get("reason", "")).strip()[:500]
            current = self.safe_rent_entry(entry)
            if amount == 0 or not reason or current["amount_due_pence"] + amount < current["amount_received_pence"]:
                return self._json({"error": "adjustment needs a reason and cannot reduce the charge below receipts"}, 400)
            entry.setdefault("adjustments", []).append({
                "amount_pence": amount, "reason": reason, "at": now(),
                "by": (self.user or {}).get("username", "agent"),
            })
        else:
            return self._json({"error": "action must be generate|receipt|adjustment"}, 400)
        entry["updated_at"] = now()
        self.audit(stage, {"actor": (self.user or {}).get("display_name", "Agent"),
                           "action": "rent_" + action, "target": entry_id,
                           "note": str(data.get("amount_pence", ""))})
        save_stage(stage)
        return self._json({"success": True, "entry": self.safe_rent_entry(entry)})

    def handle_email_sync(self, data):
        """Import unseen plain-text email into the best matching case, or create a new email case."""
        host = os.environ.get("ROGER_IMAP_HOST", "").strip()
        username = os.environ.get("ROGER_IMAP_USER", "").strip()
        password = os.environ.get("ROGER_IMAP_PASSWORD", "")
        if not host or not username or not password:
            return self._json({"error": "inbound email is not configured"}, 503)
        try:
            port = int(os.environ.get("ROGER_IMAP_PORT", "993"))
        except ValueError:
            return self._json({"error": "ROGER_IMAP_PORT must be a number"}, 503)
        folder = os.environ.get("ROGER_IMAP_FOLDER", "INBOX").strip()[:100] or "INBOX"
        try:
            mailbox = imaplib.IMAP4_SSL(host, port, timeout=15)
            mailbox.login(username, password)
            mailbox.select(folder)
            status, data = mailbox.uid("search", None, "UNSEEN")
            if status != "OK":
                mailbox.logout()
                return self._json({"error": "mailbox search failed"}, 502)
            uids = (data[0] or b"").split()
            stage = load_stage()
            seen = set(stage.get("imported_email_uids", []))
            imported = []
            to_mark_seen = []
            for uid in uids:
                key = host + ":" + folder + ":" + uid.decode("ascii", "ignore")
                if key in seen:
                    to_mark_seen.append(uid)
                    continue
                status, fetched = mailbox.uid("fetch", uid, "(RFC822)")
                if status != "OK":
                    continue
                raw = next((part[1] for part in fetched if isinstance(part, tuple) and isinstance(part[1], bytes)), None)
                if raw is None:
                    continue
                incoming = email.parser.BytesParser(policy=email.policy.default).parsebytes(raw)
                sender_name, sender_addr = email.utils.parseaddr(str(incoming.get("From", "")))
                sender_addr = sender_addr.strip().lower()
                if not sender_addr or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", sender_addr):
                    continue
                part = incoming.get_body(preferencelist=("plain",))
                body_text = part.get_content() if part else ""
                text = ("Subject: " + str(incoming.get("Subject", "(no subject)"))[:200] + "\n\n" + str(body_text)).strip()[:3000]
                if not text:
                    text = "(Email contained no plain-text body.)"
                existing = [c for c in stage.get("cases", []) if str(c.get("email", "")).strip().lower() == sender_addr]
                existing.sort(key=lambda c: str(c.get("thread", [{}])[-1].get("at", c.get("submitted_at", "")) if c.get("thread") else c.get("submitted_at", "")), reverse=True)
                case = next((c for c in existing if c.get("status") not in ("closed", "resolved", "declined")), None) or (existing[0] if existing else None)
                at = now()
                if case:
                    case.setdefault("thread", []).append({
                        "author": sender_name or sender_addr, "role": "contact",
                        "text": text[:2000], "to": ["agent"], "channel": "email",
                        "email_from": sender_addr, "at": at,
                    })
                    case_id = case.get("id")
                    event = "case_email_received"
                else:
                    case_id = stage.get("next_case_id", 490)
                    triage = self.triage(text)
                    case = {
                        "id": case_id, "type": "email", "property_id": None,
                        "role": "other", "name": sender_name or sender_addr,
                        "email": sender_addr, "message": text[:2000],
                        "status": "new", "triage": triage, "submitted_at": at,
                        "source": "email",
                        "thread": [{"author": sender_name or sender_addr, "role": "contact",
                                    "text": text[:2000], "to": ["agent"], "channel": "email",
                                    "email_from": sender_addr, "at": at}],
                    }
                    stage["next_case_id"] = case_id + 1
                    stage.setdefault("cases", []).append(case)
                    event = "email_case_created"
                self.audit(stage, {"actor": sender_addr, "action": event,
                                   "target": case_id, "note": "Inbound email"})
                seen.add(key)
                stage["imported_email_uids"] = sorted(seen)
                imported.append({"case_id": case_id, "email": sender_addr})
                to_mark_seen.append(uid)
            if imported:
                save_stage(stage)
            for uid in to_mark_seen:
                mailbox.uid("store", uid, "+FLAGS", "(\\Seen)")
            mailbox.logout()
            return self._json({"success": True, "imported": imported, "count": len(imported)})
        except (OSError, imaplib.IMAP4.error, ValueError) as exc:
            return self._json({"error": "mailbox sync failed: " + str(exc)[:240]}, 502)

    def handle_email_reply(self, data):
        """Send a deliberate agent-authored reply to the contact email on a case."""
        stage = load_stage()
        case_id = data.get("id")
        case = next((c for c in stage.get("cases", []) if str(c.get("id")) == str(case_id)), None)
        if not case:
            return self._json({"error": "case not found"}, 404)
        recipient = str(case.get("email") or "").strip()
        if not recipient or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", recipient):
            return self._json({"error": "this case has no valid contact email"}, 400)
        body = str(data.get("text", "")).strip()[:2000]
        if not body:
            return self._json({"error": "email reply text is required"}, 400)
        host = os.environ.get("ROGER_SMTP_HOST", "").strip()
        sender = os.environ.get("ROGER_FROM_EMAIL", "").strip()
        if not host or not sender:
            return self._json({"error": "outbound email is not configured"}, 503)
        try:
            port = int(os.environ.get("ROGER_SMTP_PORT", "587"))
        except ValueError:
            return self._json({"error": "ROGER_SMTP_PORT must be a number"}, 503)
        message = EmailMessage()
        message["Subject"] = "Re: Roger case #" + str(case.get("id"))
        message["From"] = formataddr(("Roger", sender))
        message["To"] = recipient
        message.set_content(body)
        try:
            if port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=15) as client:
                    username = os.environ.get("ROGER_SMTP_USER", "")
                    password = os.environ.get("ROGER_SMTP_PASSWORD", "")
                    if username:
                        client.login(username, password)
                    client.send_message(message)
            else:
                with smtplib.SMTP(host, port, timeout=15) as client:
                    client.starttls()
                    username = os.environ.get("ROGER_SMTP_USER", "")
                    password = os.environ.get("ROGER_SMTP_PASSWORD", "")
                    if username:
                        client.login(username, password)
                    client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            return self._json({"error": "email provider could not accept this message: " + str(exc)[:240]}, 502)
        at = now()
        case.setdefault("thread", []).append({
            "author": (self.user or {}).get("display_name", "Agent"),
            "role": "agent", "text": body, "to": ["email"], "channel": "email",
            "email_to": recipient, "at": at,
        })
        self.audit(stage, {"actor": (self.user or {}).get("display_name", "Agent"),
                           "action": "case_email_sent", "target": case.get("id"),
                           "note": "to " + recipient})
        save_stage(stage)
        return self._json({"success": True, "sent_at": at, "to": recipient})

    def handle_case_action(self, data):
        stage = load_stage()
        c = next((c for c in stage.get("cases", []) if str(c.get("id")) == str(data.get("id"))), None)
        if not c:
            return self._json({"error": "case not found"}, 404)
        action = data.get("action")
        u = getattr(self, "user", None) or {}
        if action in ("close", "reopen", "add_tradesperson", "mark_read", "mark_unread", "note", "follow_up") and u.get("role") != "agent":
            return self._json({"error": "agent-only move"}, 403)
        if action in ("reply", "inform", "confirm_resolution", "reopen_unresolved") and u.get("role") == "tenant" and c.get("name") != u.get("display_name"):
            return self._json({"error": "not your case"}, 403)
        if action in ("reply", "inform") and u.get("role") == "landlord" and not any(
                p["id"] == c.get("property_id") and p.get("landlord") == u.get("display_name")
                for p in stage.get("properties", [])):
            return self._json({"error": "not your property"}, 403)
        if action in ("reply", "inform") and u.get("role") == "trades" and u.get("display_name") not in (
                (c.get("participants") or []) + [j.get("assigned_to") for j in stage.get("jobs", [])
                                                 if j.get("case_id") == c["id"]]):
            return self._json({"error": "not your case"}, 403)
        if action in ("reply", "inform"):
            to = data.get("to") or ["tenant"]
            if u.get("role") == "tenant" and "tenant" not in (to + [u.get("role")]):
                return self._json({"error": "not your audience"}, 403)
            if not str(data.get("text", "")).strip():
                return self._json({"error": "nothing to say"}, 400)
            self.post_msg(stage, c["id"], data.get("text"), to=to)
            self.audit(stage, {"actor": u.get("display_name", "?"), "action": f"case_{action}",
                               "target": c["id"], "note": "-> " + ",".join(to)})
        elif action == "add_tradesperson":
            who = str(data.get("tradesperson", ""))[:100]
            known = {t["company"] for t in self.approved_trades(stage)}
            if who not in known:
                return self._json({"error": f"{who or 'nobody'} is not an approved tradesperson"}, 400)
            if who in (c.get("participants") or []):
                return self._json({"error": "already in the discussion"}, 400)
            c.setdefault("participants", []).append(who)
            self.post_msg(stage, c["id"], f"{who} has been added to this discussion by the agency.", to=("tenant", "trades"))
            self.audit(stage, {"actor": u.get("display_name", "?"), "action": "tradesperson_added", "target": c["id"], "note": who})
        elif action == "close":
            reason = str(data.get("reason", "")).strip()[:300]
            if not reason:
                return self._json({"error": "a closing reason is required"}, 400)
            c["status"] = "closed"
            c["closed_reason"] = reason
            c["actioned_at"] = now()
            self.post_msg(stage, c["id"], f"Case closed: {reason}", to=("tenant", "trades", "landlord"))
            self.audit(stage, {"actor": "agent", "action": "case_closed", "target": c["id"], "note": reason})
        elif action == "reopen":
            c["status"] = "new"
            self.post_msg(stage, c["id"], "Case reopened by the agency.", to=("tenant",))
            self.audit(stage, {"actor": "agent", "action": "case_reopened", "target": c["id"]})
        elif action == "mark_read":
            c["agent_read_at"] = now()
            self.audit(stage, {"actor": "agent", "action": "case_marked_read", "target": c["id"]})
        elif action == "mark_unread":
            c["agent_read_at"] = None
            self.audit(stage, {"actor": "agent", "action": "case_marked_unread", "target": c["id"]})
        elif action == "note":
            text = str(data.get("text", "")).strip()[:1000]
            if not text:
                return self._json({"error": "internal note text is required"}, 400)
            c.setdefault("internal_notes", []).append({
                "text": text, "at": now(), "by": u.get("display_name", "agent"),
            })
            self.audit(stage, {"actor": u.get("display_name", "agent"), "action": "case_internal_note",
                               "target": c["id"], "note": text[:120]})
        elif action == "follow_up":
            follow_up_at = str(data.get("follow_up_at", "")).strip()[:30]
            try:
                datetime.strptime(follow_up_at, "%Y-%m-%d")
            except ValueError:
                return self._json({"error": "follow_up_at must be a YYYY-MM-DD date"}, 400)
            c["follow_up_at"] = follow_up_at
            note = str(data.get("note", "")).strip()[:500]
            if note:
                c.setdefault("internal_notes", []).append({
                    "text": "Follow-up: " + note, "at": now(), "by": u.get("display_name", "agent"),
                    "follow_up_at": follow_up_at,
                })
            self.audit(stage, {"actor": u.get("display_name", "agent"), "action": "case_follow_up_set",
                               "target": c["id"], "note": follow_up_at})
        elif action == "confirm_resolution":
            if c.get("status") not in ("resolved", "awaiting_confirmation"):
                return self._json({"error": "only resolved cases can be confirmed"}, 409)
            c["status"] = "closed"
            c["tenant_confirmed_at"] = now()
            self.post_msg(stage, c["id"], "Tenant confirmed the repair is resolved.", to=("agent", "landlord", "trades"))
            self.audit(stage, {"actor": u.get("display_name", "tenant"), "action": "tenant_confirmed_resolution",
                               "target": c["id"]})
        elif action == "reopen_unresolved":
            reason = str(data.get("text", "")).strip()[:1000]
            if not reason:
                return self._json({"error": "explain what is still unresolved"}, 400)
            c["status"] = "reported"
            c["reopened_at"] = now()
            self.post_msg(stage, c["id"], "This repair is still unresolved: " + reason, to=("agent", "landlord", "trades"))
            self.audit(stage, {"actor": u.get("display_name", "tenant"), "action": "tenant_reopened_unresolved",
                               "target": c["id"], "note": reason[:120]})
        else:
            return self._json({"error": f"unknown action {action}"}, 400)
        save_stage(stage)
        self._json({"success": True})


    # ---------- invitations ----------
    def handle_invitation(self, data):
        """Agent issues a secure token a prospect/tenant uses to join the portal.
        Roles: agent only."""
        stage = load_stage()
        prop = self.find_prop(stage, data.get("property_id"))
        if not prop:
            return self._json({"error": "property not found"}, 404)
        role = str(data.get("role", "tenant"))[:20]
        if role not in ("tenant", "landlord", "trades"):
            return self._json({"error": "role must be tenant|landlord|trades"}, 400)
        token = secrets.token_urlsafe(24)
        expires = datetime.now(timezone.utc) + timedelta(days=7)
        inv = {
            "token": token,
            "property_id": prop["id"],
            "role": role,
            "email": str(data.get("email", ""))[:254],
            "name": str(data.get("name", ""))[:100],
            "status": "pending",
            "created_by": (self.user or {}).get("display_name", "Agent"),
            "created_at": now(),
            "expires_at": expires.isoformat().replace("+00:00", "Z"),
            "used_at": None,
            "revoked_at": None,
        }
        stage.setdefault("invitations", []).append(inv)
        self.audit(stage, {"actor": (self.user or {}).get("display_name", "?"),
                           "action": "invitation_created", "target": token[:8],
                           "note": f"{role} for {prop['id']}"})
        save_stage(stage)
        return self._json({"success": True, "token": token,
                           "invite_url": f"/invite?token={token}",
                           "expires_at": inv["expires_at"]})

    def handle_invitation_action(self, data):
        """use (mark accepted after account creation) or revoke. Roles: agent only."""
        stage = load_stage()
        token = str(data.get("token", ""))[:64]
        inv = next((i for i in stage.get("invitations", []) if i["token"] == token), None)
        if not inv:
            return self._json({"error": "invitation not found"}, 404)
        action = data.get("action")
        if action == "use":
            if inv["status"] != "pending":
                return self._json({"error": f"invitation already {inv['status']}"}, 409)
            inv["status"] = "used"
            inv["used_at"] = now()
            self.audit(stage, {"actor": (self.user or {}).get("display_name", "?"),
                               "action": "invitation_used", "target": token[:8]})
        elif action == "revoke":
            inv["status"] = "revoked"
            inv["revoked_at"] = now()
            self.audit(stage, {"actor": (self.user or {}).get("display_name", "?"),
                               "action": "invitation_revoked", "target": token[:8]})
        else:
            return self._json({"error": "action must be use|revoke"}, 400)
        save_stage(stage)
        return self._json({"success": True, "status": inv["status"]})

    def validate_invitation_token(self, token):
        """Public check used by the invitee's browser before account creation.
        No session required — the invitee may not have an account yet."""
        stage = load_stage()
        inv = next((i for i in stage.get("invitations", []) if i["token"] == token), None)
        if not inv:
            return {"valid": False, "reason": "not_found"}
        if inv["status"] != "pending":
            return {"valid": False, "reason": f"already_{inv['status']}"}
        exp = inv.get("expires_at")
        if exp and datetime.fromisoformat(exp.replace("Z", "+00:00").replace("+00:00+00:00", "+00:00")) < datetime.now(timezone.utc):
            return {"valid": False, "reason": "expired"}
        prop = self.find_prop(stage, inv["property_id"]) or {}
        return {"valid": True, "token": token, "property_id": inv["property_id"],
                "property_title": prop.get("title"), "role": inv["role"],
                "email": inv.get("email", ""), "name": inv.get("name", "")}

    # ---------- documents ----------
    def get_document(self, doc_id):
        return next((d for d in load_stage().get("documents", []) if d["id"] == doc_id), None)

    def can_view_document(self, u, doc):
        if u["role"] == "agent":
            return True
        stage = load_stage()
        me = u["display_name"]
        c = next((c for c in stage.get("cases", []) if c["id"] == doc.get("case_id")), None)
        prop = self.find_prop(stage, doc.get("property_id") or (c or {}).get("property_id")) or {}
        if u["role"] == "tenant":
            return prop.get("tenant") == me or (c or {}).get("name") == me
        if u["role"] == "landlord" and prop.get("landlord") == me:
            return True
        if u["role"] == "trades":
            case_ids = {j.get("case_id") for j in stage.get("jobs", []) if j.get("assigned_to") == me}
            if c and (c["id"] in case_ids or me in (c.get("participants") or [])):
                return True
        return False

    def scoped_documents(self, u):
        stage = load_stage()
        docs = stage.get("documents", [])
        if u["role"] == "agent":
            return [self.safe_document(d) for d in docs]
        return [self.safe_document(d) for d in docs if self.can_view_document(u, d)]

    def document_path(self, doc):
        key = str(doc.get("storage_key", ""))
        if not re.fullmatch(r"[a-f0-9]{64}", key):
            return None
        return os.path.join(FILES_DIR, key[:2], key)

    def store_document_body(self, raw):
        key = hashlib.sha256(raw).hexdigest()
        folder = os.path.join(FILES_DIR, key[:2])
        os.makedirs(folder, mode=0o700, exist_ok=True)
        path = os.path.join(folder, key)
        if not os.path.exists(path):
            fd, temp_path = tempfile.mkstemp(prefix=".roger-file-", dir=folder)
            try:
                with os.fdopen(fd, "wb") as target:
                    target.write(raw)
                    target.flush()
                    os.fsync(target.fileno())
                os.chmod(temp_path, 0o600)
                os.replace(temp_path, path)
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        return key

    def safe_document(self, d):
        out = {k: v for k, v in d.items() if k != "data_b64"}
        out["has_file"] = bool(d.get("storage_key") or d.get("data_b64"))
        return out

    def handle_document(self, data):
        """Agent uploads a tenancy agreement / deposit receipt / inspection report.
        Content received as base64 in JSON (stdlib server has no multipart parser)."""
        stage = load_stage()
        case_id = data.get("case_id")
        c = next((c for c in stage.get("cases", []) if c["id"] == case_id), None)
        property_id = data.get("property_id")
        if not property_id and c:
            property_id = c.get("property_id")
        prop = self.find_prop(stage, property_id)
        if not prop:
            return self._json({"error": "property not found (pass property_id or a valid case_id)"}, 404)
        dtype = str(data.get("document_type", "other"))[:40]
        allowed = ("tenancy_agreement", "deposit_receipt", "inspection_report", "id_proof", "maintenance_evidence", "other")
        if dtype not in allowed:
            return self._json({"error": f"document_type must be one of {', '.join(allowed)}"}, 400)
        b64 = str(data.get("content_b64", ""))
        import base64
        try:
            raw = base64.b64decode(b64, validate=True)
        except Exception:
            return self._json({"error": "content_b64 must be valid base64"}, 400)
        if len(raw) > 5 * 1024 * 1024:
            return self._json({"error": "file too large (max 5 MB)"}, 400)
        storage_key = self.store_document_body(raw)
        fname = os.path.basename(str(data.get("file_name", "document"))[:120]) or "document"
        fname = re.sub(r"[^A-Za-z0-9._ -]", "_", fname)
        doc_id = f"doc-{len(stage.get('documents', [])) + 1}"
        flist = stage.setdefault("documents", [])
        doc = {
            "id": doc_id,
            "case_id": case_id if c else None,
            "property_id": prop["id"],
            "document_type": dtype,
            "title": str(data.get("title", ""))[:120],
            "description": str(data.get("description", ""))[:500],
            "file_name": fname,
            "content_type": str(data.get("content_type", "application/octet-stream"))[:80],
            "file_size": len(raw),
            "storage_key": storage_key,
            "uploaded_by": (self.user or {}).get("display_name", "Agent"),
            "uploaded_at": now(),
            "verified_by": None,
            "verified_at": None,
            "status": "pending",
            "notes": "",
        }
        flist.append(doc)
        self.audit(stage, {"actor": (self.user or {}).get("display_name", "?"),
                           "action": "document_uploaded", "target": doc_id,
                           "note": f"{dtype} / {fname} / {len(raw)}B for {prop['id']}"})
        save_stage(stage)
        return self._json({"success": True, "document": self.safe_document(doc)})

    def handle_document_action(self, data):
        """verify or reject an uploaded document with an optional note. Roles: agent only."""
        stage = load_stage()
        doc = next((d for d in stage.get("documents", []) if d["id"] == data.get("id")), None)
        if not doc:
            return self._json({"error": "document not found"}, 404)
        action = data.get("action")
        if action not in ("verify", "reject"):
            return self._json({"error": "action must be verify|reject"}, 400)
        if action == "reject" and not str(data.get("note", "")).strip():
            return self._json({"error": "a note is required when rejecting"}, 400)
        doc["status"] = "verified" if action == "verify" else "rejected"
        doc["verified_by"] = (self.user or {}).get("display_name", "Agent")
        doc["verified_at"] = now()
        if data.get("note"):
            doc["notes"] = str(data["note"])[:500]
        self.audit(stage, {"actor": (self.user or {}).get("display_name", "?"),
                           "action": f"document_{action}", "target": doc["id"], "note": doc.get("notes")})
        save_stage(stage)
        return self._json({"success": True, "document": self.safe_document(doc)})

    def serve_document_file(self, doc):
        import base64
        path = self.document_path(doc)
        try:
            if path and os.path.isfile(path):
                with open(path, "rb") as handle:
                    body = handle.read()
            elif doc.get("data_b64"):
                body = base64.b64decode(doc["data_b64"])
            else:
                return self._json({"error": "document file is missing"}, 404)
        except (OSError, ValueError):
            return self._json({"error": "document file could not be read"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", doc.get("content_type", "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'inline; filename="{doc.get("file_name", "document")}"')
        self.end_headers()
        self.wfile.write(body)

    # ---------- appointments ----------
    def scoped_appointments(self, u):
        stage = load_stage()
        appts = [a for a in stage.get("appointments", [])]
        if u["role"] == "agent":
            return appts
        me = u["display_name"]
        if u["role"] == "tenant":
            mine = {p["id"] for p in stage.get("properties", []) if p.get("tenant") == me}
            return [a for a in appts if a["property_id"] in mine]
        mine = {p["id"] for p in stage.get("properties", []) if p.get("landlord") == me}
        return [a for a in appts if a["property_id"] in mine]

    def handle_appointment(self, data):
        """Agent schedules a viewing/inspection/key handover. Roles: agent only."""
        stage = load_stage()
        prop = self.find_prop(stage, data.get("property_id"))
        if not prop:
            return self._json({"error": "property not found"}, 404)
        start = str(data.get("start_time", ""))[:40]
        end = str(data.get("end_time", ""))[:40]
        if not start:
            return self._json({"error": "start_time is required"}, 400)
        if end and end < start:
            return self._json({"error": "end_time must be after start_time"}, 400)
        appts = stage.setdefault("appointments", [])
        nums = [int(a["id"].split("-")[1]) for a in appts if re.fullmatch(r"appt-\d+", a["id"])]
        appt = {
            "id": f"appt-{(max(nums) + 1) if nums else 1}",
            "property_id": prop["id"],
            "case_id": data.get("case_id") or None,
            "title": str(data.get("title", "Viewing"))[:120] or "Viewing",
            "description": str(data.get("description", ""))[:1000],
            "start_time": start,
            "end_time": end or None,
            "location": str(data.get("location", "At the property"))[:200],
            "status": "proposed",
            "invitee_role": str(data.get("invitee_role", "tenant"))[:20]
                         if data.get("invitee_role") in ("tenant", "landlord", "trades") else "tenant",
            "created_by": (self.user or {}).get("display_name", "Agent"),
            "created_at": now(),
            "updated_at": now(),
            "notes": "",
            "outcome": None,
        }
        appts.append(appt)
        self.audit(stage, {"actor": (self.user or {}).get("display_name", "?"),
                           "action": "appointment_created", "target": appt["id"],
                           "note": f"{appt['title']} @ {appt['start_time']}"})
        save_stage(stage)
        return self._json({"success": True, "appointment": appt})

    def handle_appointment_action(self, data):
        """Confirm/decline/complete/miss/cancel an appointment. Roles: agent (any),
        tenant/landlord on their own property."""
        stage = load_stage()
        appt = next((a for a in stage.get("appointments", []) if a["id"] == data.get("id")), None)
        if not appt:
            return self._json({"error": "appointment not found"}, 404)
        action = data.get("action")
        allowed = ("confirm", "decline", "complete", "miss", "cancel")
        if action not in allowed:
            return self._json({"error": f"action must be one of {', '.join(allowed)}"}, 400)
        u = self.user or {}
        if u["role"] == "agent":
            pass  # agent may take any action
        else:
            prop = self.find_prop(stage, appt["property_id"]) or {}
            if u["role"] == "tenant" and prop.get("tenant") != u["display_name"]:
                return self._json({"error": "not your property"}, 403)
            if u["role"] == "landlord" and prop.get("landlord") != u["display_name"]:
                return self._json({"error": "not your property"}, 403)
            # parties may not cancel an agency-set appointment; agent must
            if action == "cancel":
                return self._json({"error": "only the agency can cancel"}, 403)
        status_map = {"confirm": "confirmed", "decline": "declined",
                      "complete": "completed", "miss": "missed", "cancel": "cancelled"}
        appt["status"] = status_map[action]
        appt["updated_at"] = now()
        if data.get("note"):
            appt["notes"] = str(data["note"])[:500]
        if data.get("outcome"):
            appt["outcome"] = str(data["outcome"])[:500]
        self.audit(stage, {"actor": u.get("display_name", "?"),
                           "action": f"appointment_{action}", "target": appt["id"]})
        save_stage(stage)
        return self._json({"success": True, "appointment": appt})

    # ---------- static ----------
    def serve_file(self, name, ctype="text/html; charset=utf-8"):
        fp = os.path.join(ROOT, name)
        try:
            with open(fp, "rb") as f:
                body = f.read()
        except OSError:
            return self.send_error(404)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

if __name__ == "__main__":
    bind_host = os.environ.get("BIND_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8901"))
    print(f"Roger portal listening on http://{bind_host}:{port}", flush=True)
    HTTPServer((bind_host, port), H).serve_forever()
