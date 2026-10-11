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
import mimetypes
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

# Legacy compatibility only. Never ship a fake "verified" trade to production.
# New repair work checks persistent registration, Party ownership and insurance.
TRADE_PROFILES = {}
# Trades that legally need a specific verified certificate before booking
CERT_REQUIRED = {"gas": "Gas Safe"}

def now():
    return datetime.utcnow().isoformat() + "Z"

class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    # ---------- auth plumbing ----------
    PUBLIC_GET = {"/", "/login", "/signin", "/register/landlord", "/register/trades",
              "/dash.css", "/favicon.svg", "/sample-home.jpg", "/api/whoami"}
    PUBLIC_POST = {"/login", "/logout", "/api/public", "/register/landlord", "/register/trades", "/api/enquiry"}

    def parse_cookies(self):
        raw = self.headers.get("Cookie") or ""
        c = http.cookies.SimpleCookie()
        try:
            c.load(raw)
        except http.cookies.CookieError:
            pass
        return {k: m.value for k, m in c.items()}

    @staticmethod
    def session_cookie_header(token, revoke=False):
        """Secure by default; permit HTTP only in isolated lab."""
        cookie = http.cookies.SimpleCookie()
        cookie["stage_session"] = "" if revoke else token
        morsel = cookie["stage_session"]
        morsel["httponly"] = True
        morsel["samesite"] = "Lax"
        morsel["path"] = "/"

        if revoke:
            morsel["max-age"] = 0

        lab_http = (
            os.environ.get("ROGER_ENV") == "security-lab"
            and os.environ.get("ROGER_LAB_HTTP_COOKIES") == "1"
        )
        if not lab_http:
            morsel["secure"] = True

        return cookie.output(header="").strip()

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
                "/api/landlord-action": {"landlord", "agent"}, "/api/landlord/property-submission": {"landlord"}, "/api/agent/property-submission": {"agent"}, "/api/registration-action": {"agent"}, "/api/contractor-verification": {"agent"}, "/api/office-settings": {"agent"}, "/api/prospect-action": {"agent"}, "/api/property-action": {"agent"}, "/api/party-action": {"agent"}, "/api/tenancy-action": {"agent"}, "/api/management-agreement-action": {"agent"}, "/api/email-reply": {"agent"}, "/api/rent-ledger-action": {"agent"}, "/api/landlord-statement-action": {"agent"}, "/api/compliance-action": {"agent"}, "/api/task-action": {"agent"}, "/api/notification-action": {"agent", "tenant", "landlord", "trades"}, "/api/email-sync": {"agent"},
                "/api/case-action": {"agent", "tenant", "landlord", "trades"},
                "/api/appointment": {"agent", "trades"}, "/api/appointment-action": {"agent", "tenant", "landlord", "trades"},
                "/api/invitation": {"agent"}, "/api/invitation-action": {"agent"},
                "/api/document": {"agent"}, "/api/document-action": {"agent"}}
    DOCUMENT_TYPES = (
        "property_document", "tenancy_agreement", "deposit_receipt", "inspection_report",
        "id_proof", "landlord_document", "trades_document", "job_document",
        "maintenance_evidence", "compliance_certificate", "other",
    )
    APPOINTMENT_TYPES = (
        "viewing", "inspection", "contractor_visit", "valuation", "check_in",
        "check_out", "key_handover", "compliance_visit", "agent_appointment",
    )

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
        return path in self.PUBLIC_GET or path.startswith("/_next/static/") or path == "/api/public"

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
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Set-Cookie",
            self.session_cookie_header(tok)
        )
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "role": u["role"]}).encode())

    # ---------- routes ----------
    def do_HEAD(self):
        return self.send_error(405, "HEAD not supported")

    def do_POST_logout(self, data):
        """Revoke the presented session token on the server."""
        token = self.parse_cookies().get("stage_session")
        if token:
            users = load_users()
            sessions = users.get("sessions", {})
            if isinstance(sessions, dict):
                if sessions.pop(token, None) is not None:
                    save_users(users)

        self.send_response(303)
        self.send_header(
            "Set-Cookie",
            self.session_cookie_header("", revoke=True)
        )
        self.send_header("Cache-Control", "no-store")
        self.send_header("Location", "/login")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if ("%" in path or "\\" in path or "//" in path
                or any(x in (".", "..") for x in path.split("/"))):
            return self.send_error(404)
        if path == "/login":
            return self.serve_file("login.html")
        if path == "/logout":
            self.send_response(405)
            self.send_header("Allow", "POST")
            self.send_header("Cache-Control", "no-store")
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
        if path == "/api/landlord/rent-ledger":
            u = self.require({"landlord"})
            if not u:
                return
            stage = load_stage()
            # Never resolve ownership from a display name or untrusted query value.
            party_ids = self.account_party_ids(stage, u, "landlord")
            property_ids = {
                p["id"] for p in stage.get("properties", [])
                if isinstance(p, dict) and isinstance(p.get("id"), str)
                and self.has_party_link(p, "landlord", party_ids)
            }
            entries = []
            for entry in stage.get("rent_ledger_entries", []):
                if not isinstance(entry, dict) or entry.get("property_id") not in property_ids:
                    continue
                safe = self.safe_rent_entry(entry)
                # Landlords may see rent and receipt dates, not internal notes,
                # agency fee calculations or other tenants' payment data.
                entries.append({
                    k: safe.get(k) for k in (
                        "id", "property_id", "tenancy_id", "due_date",
                        "amount_due_pence", "amount_received_pence",
                        "balance_pence", "status"
                    )
                } | {"payments": [
                    {"received_date": payment.get("received_date"),
                     "amount_pence": payment.get("amount_pence")}
                    for payment in entry.get("payments", [])
                    if isinstance(payment, dict)
                ]})
            return self._json({"entries": entries})
        if path == "/api/appointments":
            u = self.require({"agent", "tenant", "landlord", "trades"})
            if not u:
                return
            return self._json({"appointments": self.scoped_appointments(u)})
        if path == "/api/tasks":
            if not self.require({"agent"}):
                return
            return self._json({"tasks": load_stage().get("tasks", [])})
        if path == "/api/office-settings":
            u = self.require({"agent", "tenant", "landlord", "trades"})
            if not u:
                return
            return self._json({"office": self.safe_office_settings(load_stage(), u)})
        if path == "/api/notifications":
            u = self.require({"agent", "tenant", "landlord", "trades"})
            if not u:
                return
            return self._json({"notifications": self.scoped_notifications(u)})
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
        public_files = {"/", "/dash.css", "/favicon.svg",
                        "/sample-home.jpg"}
        if (path not in routes and path not in public_files
                and not path.startswith("/_next/static/")):
            return self.send_error(404)
        if not self.is_public(path):
            if not self.require(self.ROLE_PAGES.get(path)):
                return
        if path in routes:
            if routes[path] == "__scoped_stage__":
                return self.serve_scoped_stage()
            return self.serve_file(routes[path])
        # ROGER_PUBLIC_ASSET_ALLOWLIST
        files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/dash.css": ("dash.css", "text/css; charset=utf-8"),
            "/favicon.svg": ("favicon.svg", "image/svg+xml"),
            "/sample-home.jpg": ("sample-home.jpg", "image/jpeg"),
        }
        if path in files:
            return self.serve_file(*files[path])

        if path.startswith("/_next/static/"):
            root = os.path.realpath(
                os.path.join(ROOT, "_next", "static"))
            target = os.path.realpath(
                os.path.join(ROOT, path.lstrip("/")))
            suffix = path.rsplit(".", 1)[-1].lower()
            allowed = {"js", "css", "woff", "woff2",
                       "ttf", "png", "jpg", "jpeg",
                       "svg", "webp", "ico"}
            if (os.path.commonpath((root, target)) != root
                    or suffix not in allowed
                    or not os.path.isfile(target)):
                return self.send_error(404)
            mime = mimetypes.guess_type(target)[0]
            return self.serve_file(
                path.lstrip("/"), mime or "application/octet-stream")

        return self.send_error(404)

    def account_party_ids(self, stage, user, role):
        """Resolve ownership by immutable account ID, never a name."""
        account_id = user.get("account_id")
        if not account_id or not isinstance(account_id, str):
            return set()
        return {
            p["id"] for p in stage.get("parties", [])
            if isinstance(p, dict)
            and isinstance(p.get("id"), str)
            and p.get("status") == "active"
            and p.get("account_id") == account_id
            and role in p.get("roles", [])
        }

    def has_party_link(self, record, role, party_ids):
        """Missing or ambiguous legacy ownership fails closed."""
        if not party_ids or not isinstance(record, dict):
            return False
        one = record.get(role + "_party_id")
        many = record.get(role + "_party_ids")
        return (isinstance(one, str) and one in party_ids
                or isinstance(many, list)
                and any(isinstance(x, str) and x in party_ids
                        for x in many))

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
            party_ids = self.account_party_ids(stage, u, "tenant")
            myprops = [p for p in props
                       if self.has_party_link(p, "tenant", party_ids)]
            property_ids = {p["id"] for p in myprops}
            mycases = [c for c in d.get("cases", [])
                       if self.has_party_link(c, "tenant", party_ids)
                       and (not c.get("property_id")
                            or c.get("property_id") in property_ids)]
            cids = {c["id"] for c in mycases}
            myjobs = [{k: v for k, v in j.items() if k != "email"}
                      for j in d.get("jobs", []) if j.get("case_id") in cids]
            for c in mycases:
                c.pop("internal_notes", None)
                c["thread"] = [t for t in (c.get("thread") or []) if "tenant" in (t.get("to") or [])
                                        or t.get("author_account_id") == u.get("account_id")]
            d = {"properties": myprops, "cases": mycases, "jobs": myjobs,
                 "authority": d.get("authority"), "role": "tenant"}
        elif u["role"] == "landlord":
            party_ids = self.account_party_ids(stage, u, "landlord")
            myprops = [p for p in props
                       if self.has_party_link(p, "landlord", party_ids)]
            pids = {p["id"] for p in myprops}
            mycases = [c for c in d.get("cases", []) if c.get("property_id") in pids]
            for c in mycases:
                c.pop("internal_notes", None)
                c["thread"] = [t for t in (c.get("thread") or []) if "landlord" in (t.get("to") or [])
                                        or t.get("author_account_id") == u.get("account_id")]
            d = {"properties": myprops,
                 "property_submissions": [
                     s for s in d.get("property_submissions", [])
                     if s.get("landlord_party_id") in party_ids
                     and s.get("created_by_account_id") == u.get("account_id")
                 ],
                 "cases": mycases,
                 "jobs": [j for j in d.get("jobs", []) if j.get("property_id") in pids],
                 "approvals": [a for a in d.get("approvals", []) if (self.has_party_link(a, "landlord", party_ids)
                                   and a.get("property_id") in pids)],
                 "repair_authority": {p["id"]: self.repair_authority(stage, p["id"]) for p in myprops},
                 "authority": d.get("authority"), "role": "landlord"}
        elif u["role"] == "trades":
            ids = self.account_party_ids(stage, u, "trades")
            jobs = d.get("jobs", [])

            owned = [
                j for j in jobs
                if ids and (
                    j.get("assigned_to_party_id") in ids
                    or j.get("requested_by_party_id") in ids
                )
            ]

            available = [
                j for j in jobs
                if ids
                and j.get("status") == "open"
                and not j.get("assigned_to")
                and not j.get("assigned_to_party_id")
                and not j.get("requested_by")
                and not j.get("requested_by_party_id")
            ]

            private_fields = {
                "id", "case_id", "property_id",
                "message", "triage", "required_trade",
                "status", "assigned_to", "requested_by",
                "gate_reason", "quotes", "approved_quote_version",
                "approved_quote_pence", "approved_variations", "pending_variation",
                "invoice_pence", "invoice_number", "invoice_line_items",
                "invoice_net_pence", "invoice_vat_pence",
                "balance_due_pence", "payments", "credit_notes",
                "payment_reference", "payment_amount_pence",
                "created_at", "completed_at", "paid_at",
            }

            private_jobs = [
                {k: v for k, v in j.items()
                 if k in private_fields}
                for j in owned
            ]

            # An open job is a listing, not permission
            # to read the tenant's full maintenance report.
            public_jobs = []
            for j in available:
                triage = j.get("triage")
                safe_triage = (
                    {k: triage[k] for k in ("urgency", "safety")
                     if k in triage}
                    if isinstance(triage, dict) else None
                )
                public_jobs.append({
                    "id": j.get("id"),
                    "case_id": j.get("case_id"),
                    "status": "open",
                    "required_trade": j.get("required_trade"),
                    "created_at": j.get("created_at"),
                    "triage": safe_triage,
                    "message": (
                        "Further details available after "
                        "accepting this job."
                    ),
                })

            owned_case_ids = {
                str(j.get("case_id"))
                for j in owned
                if j.get("case_id") is not None
            }
            threads = {}
            for case in d.get("cases", []):
                cid = str(case.get("id"))
                if cid not in owned_case_ids:
                    continue
                threads[case["id"]] = [
                    {
                        k: v for k, v in msg.items()
                        if k in (
                            "author", "role", "text",
                            "to", "at"
                        )
                    }
                    for msg in (case.get("thread") or [])
                    if isinstance(msg, dict)
                    and (
                        "trades" in (msg.get("to") or [])
                        or (
                            msg.get("author_account_id")
                            == u.get("account_id")
                            and u.get("account_id")
                        )
                    )
                ]

            owned_property_ids = {
                j.get("property_id") for j in owned
            }
            safe_properties = [
                {k: p.get(k) for k in ("id", "title", "area")}
                for p in props
                if p.get("id") in owned_property_ids
            ]

            owned_job_ids = {
                str(j.get("id")) for j in owned
            }
            safe_approvals = [
                {
                    k: a.get(k)
                    for k in (
                        "id", "job_id", "status",
                        "amount_pence", "requested_at",
                        "reason_given"
                    )
                }
                for a in d.get("approvals", [])
                if str(a.get("job_id")) in owned_job_ids
            ]

            authority = d.get("authority") or {}
            d = {
                "role": "trades",
                "jobs": private_jobs + public_jobs,
                "threads": threads,
                "properties": safe_properties,
                "approvals": safe_approvals,
                "authority": {
                    "standing_limit_pence":
                    authority.get("standing_limit_pence", 15000)
                },
            }
        self._json(d)

    def valid_csrf_origin(self):
        """Accept POST only from explicitly trusted browser origins.

        Never infer the trusted origin from Host or proxy headers.
        """
        configured = os.environ.get(
            "ROGER_ALLOWED_ORIGINS",
            "https://agency.lifecompass.shop"
        )

        allowed = set()
        for item in configured.split(","):
            origin = item.strip()
            try:
                parsed = urllib.parse.urlsplit(origin)
                if (parsed.scheme in ("http", "https")
                        and parsed.hostname
                        and not parsed.username
                        and not parsed.password
                        and not parsed.path
                        and not parsed.query
                        and not parsed.fragment
                        and origin == (
                            parsed.scheme + "://" + parsed.netloc
                        )):
                    allowed.add(origin)
            except ValueError:
                continue

        if not allowed:
            return False

        fetch_site = self.headers.get_all(
            "Sec-Fetch-Site", []
        )
        if len(fetch_site) > 1:
            return False
        if fetch_site and (
            fetch_site[0].strip().lower() == "cross-site"
        ):
            return False

        origins = self.headers.get_all("Origin", [])
        if origins:
            return (
                len(origins) == 1
                and origins[0].strip() in allowed
            )

        referers = self.headers.get_all("Referer", [])
        if len(referers) != 1:
            return False

        try:
            ref = urllib.parse.urlsplit(
                referers[0].strip()
            )
            if (ref.scheme not in ("http", "https")
                    or not ref.hostname
                    or ref.username
                    or ref.password):
                return False

            ref_origin = (
                ref.scheme + "://" + ref.netloc
            )
            return ref_origin in allowed
        except ValueError:
            return False

    def do_POST(self):
        path = self.path.split("?")[0]
        self.user = None
        if not self.valid_csrf_origin():
            return self._json(
                {"error": "untrusted request origin"}, 403
            )
        if not self.is_public(path) and path not in self.PUBLIC_POST:
            u = self.require(self.ROLE_API.get(path))
            if not u:
                return
            self.user = u
        limits = {
            "/login": 8 * 1024,
            "/api/document": 8 * 1024 * 1024,
            "/api/tenant/issue": 32 * 1024 * 1024,
        }
        max_length = limits.get(path, 256 * 1024)

        # Do not attempt to read an unbounded or ambiguous body.
        if self.headers.get_all("Transfer-Encoding"):
            self.close_connection = True
            return self._json(
                {"error": "transfer encoding not supported"}, 400
            )

        values = self.headers.get_all("Content-Length", [])
        if len(values) != 1:
            self.close_connection = True
            return self._json(
                {"error": "one Content-Length header required"},
                400 if values else 411
            )

        value = values[0].strip()
        if not re.fullmatch(r"[0-9]+", value):
            self.close_connection = True
            return self._json(
                {"error": "invalid Content-Length"}, 400
            )

        length = int(value)
        if length > max_length:
            self.close_connection = True
            return self._json(
                {"error": "request body too large"}, 413
            )

        raw = self.rfile.read(length)
        if len(raw) != length:
            self.close_connection = True
            return self._json(
                {"error": "incomplete request body"}, 400
            )

        try:
            body = raw.decode("utf-8") if raw else "{}"
        except UnicodeDecodeError:
            return self._json(
                {"error": "request must be UTF-8"}, 400
            )

        try:
            data = json.loads(body)
        except ValueError:
            data = dict(urllib.parse.parse_qsl(body))

        if not isinstance(data, dict):
            return self._json(
                {"error": "request body must be an object"}, 400
            )
        handlers = {
            "/login": self.do_POST_login,
            "/logout": self.do_POST_logout,
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
            "/api/contractor-verification": self.handle_contractor_verification,
            "/api/office-settings": self.handle_office_settings,
            "/api/prospect-action": self.handle_prospect_action,
            "/api/property-action": self.handle_property_action,
            "/api/landlord/property-submission": self.handle_landlord_property_submission,
            "/api/agent/property-submission": self.handle_agent_property_submission,
            "/api/party-action": self.handle_party_action,
            "/api/tenancy-action": self.handle_tenancy_action,
            "/api/management-agreement-action": self.handle_management_agreement_action,
            "/api/case-action": self.handle_case_action,
            "/api/email-reply": self.handle_email_reply,
            "/api/email-sync": self.handle_email_sync,
            "/api/rent-ledger-action": self.handle_rent_ledger_action,
            "/api/landlord-statement-action": self.handle_landlord_statement_action,
            "/api/compliance-action": self.handle_compliance_action,
            "/api/task-action": self.handle_task_action,
            "/api/notification-action": self.handle_notification_action,
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
            "author_account_id": u.get("account_id"),
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
                "party_id": None, "tenancy_id": None, "job_id": None,
                "document_type": "maintenance_evidence", "title": "Maintenance evidence",
                "description": "Uploaded with tenant maintenance report",
                "file_name": fname, "content_type": content_type, "file_size": len(raw),
                "storage_key": self.store_document_body(raw),
                "expiry_date": None, "access_roles": ["agent", "tenant"],
                "version": 1, "supersedes_id": None, "replaced_by_id": None,
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
        """Display active approved registrations; mark dispatch eligibility."""
        out = []
        for reg in stage.get("registrations", []):
            if (reg.get("role") != "trades" or reg.get("status") != "approved"
                    or reg.get("prospect_stage") in ("suspended", "rejected")):
                continue
            pid = reg.get("party_id")
            party = next((p for p in stage.get("parties", [])
                          if p.get("id") == pid and p.get("status") == "active"
                          and p.get("display_name") == reg.get("name")
                          and "trades" in p.get("roles", []) and p.get("account_id")), None)
            party_id = party["id"] if party else None
            verified = (bool(party_id) and self.verified_contractor_for_new_repair(
                stage, party_id, None))
            out.append({
                "company": reg.get("name", "Unknown contractor"),
                "trades": reg.get("trades") or ["general"],
                "gas_safe": bool(verified and self.verified_contractor_for_new_repair(
                    stage, party_id, "gas")),
                "party_id": party_id,
                "ready_for_new_repairs": verified,
                "verification_valid_until": (reg.get("contractor_verification") or {}).get("valid_until"),
                "service_areas": (reg.get("contractor_verification") or {}).get("service_areas", []),
            })
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
            reg["verification_required"] = True
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

    @staticmethod
    def contractor_location_match(verification, property_record):
        """Exact declared service area or postcode outward code, not fuzzy prefix."""
        areas = verification.get("service_areas") or []
        if not isinstance(areas, list) or not areas:
            return False
        postcode = str((property_record or {}).get("postcode") or "").upper().replace(" ", "")
        area = str((property_record or {}).get("area") or "").strip().upper()
        options = {str(item).strip().upper().replace(" ", "") for item in areas
                   if isinstance(item, str)}
        if area and area.replace(" ", "") in options:
            return True
        # Outward postcode is everything before the final three characters.
        outward = postcode[:-3] if len(postcode) >= 5 else ""
        return bool(outward and outward in options)

    @staticmethod
    def contractor_verified_document(stage, party_id, doc_id):
        doc = next((d for d in stage.get("documents", [])
                    if d.get("id") == doc_id and d.get("party_id") == party_id
                    and d.get("document_type") == "trades_document"
                    and d.get("status") == "verified"
                    and not d.get("replaced_by_id")
                    and d.get("verified_at")
                    and (d.get("storage_key") or d.get("data_b64"))
                    ), None)
        if not doc:
            return None
        expiry = doc.get("expiry_date")
        try:
            if not expiry or datetime.strptime(expiry, "%Y-%m-%d").date() < datetime.now(timezone.utc).date():
                return None
        except (ValueError, TypeError):
            return None
        return doc

    def handle_contractor_verification(self, data):
        """Human-reviewed independent checks: keep evidence references, never assert automated verification."""
        if (self.user or {}).get("role") != "agent":
            return self._json({"error": "only agents may attest independent contractor checks"}, 403)
        stage = load_stage()
        reg = next((r for r in stage.get("registrations", [])
                    if r.get("id") == data.get("registration_id") and r.get("role") == "trades"), None)
        if not reg:
            return self._json({"error": "trades registration not found"}, 404)
        pid = reg.get("party_id")
        party = next((p for p in stage.get("parties", [])
                      if p.get("id") == pid and p.get("source_registration_id") == reg["id"]
                      and p.get("status") == "active" and "trades" in p.get("roles", [])
                      and p.get("account_id") and p.get("display_name") == reg.get("name")), None)
        if not party or reg.get("status") != "approved":
            return self._json({"error": "active linked approved contractor account required"}, 409)
        action = data.get("action")
        if action not in ("verify", "revoke"):
            return self._json({"error": "action must be verify or revoke"}, 400)
        if action == "revoke":
            reason = str(data.get("reason") or "").strip()[:500]
            if not reason:
                return self._json({"error": "revocation reason is required"}, 400)
            previous = reg.get("contractor_verification")
            if not previous or previous.get("status") != "verified":
                return self._json({"error": "no active verification to revoke"}, 409)
            previous["status"] = "revoked"
            previous["revoked_at"] = now()
            previous["revocation_reason"] = reason
            previous["revoked_by"] = (self.user or {}).get("username", "agent")
            self.audit(stage, {"actor": (self.user or {}).get("display_name", "Agent"),
                               "action": "contractor_verification_revoked",
                               "target": reg["id"], "note": reason})
            save_stage(stage)
            return self._json({"success": True, "verification_status": "revoked"})
        if reg.get("prospect_stage") in ("suspended", "rejected"):
            return self._json({"error": "suspended contractor cannot be verified"}, 409)
        docs = {}
        for kind in ("insurance", "qualification"):
            doc = self.contractor_verified_document(stage, pid, data.get(kind + "_document_id"))
            if not doc:
                return self._json({"error": "valid verified " + kind + " document linked to this contractor is required"}, 409)
            docs[kind] = doc
        if docs["insurance"]["id"] == docs["qualification"]["id"]:
            return self._json({"error": "insurance and qualification require separate evidence documents"}, 409)
        source = str(data.get("check_source") or "").strip()[:100]
        ref = str(data.get("external_check_reference") or "").strip()[:160]
        insurance_source = str(data.get("insurance_check_source") or "").strip()[:100]
        insurance_ref = str(data.get("insurance_check_reference") or "").strip()[:160]
        valid_until = str(data.get("valid_until") or "").strip()
        try:
            expires = datetime.strptime(valid_until, "%Y-%m-%d").date()
            registered_expires = datetime.strptime(reg["insurance_expiry"], "%Y-%m-%d").date()
            d_expires = [datetime.strptime(d["expiry_date"], "%Y-%m-%d").date() for d in docs.values()]
        except (TypeError, ValueError, KeyError):
            return self._json({"error": "valid review date and insurance expiry required"}, 400)
        today = datetime.now(timezone.utc).date()
        if (not today <= expires <= today + timedelta(days=366)
                or expires > min([registered_expires] + d_expires)):
            return self._json({"error": "verification expiry must be current and no later than underlying evidence"}, 409)
        if (not source or not ref or not insurance_source or not insurance_ref
                or len(ref) < 4 or len(insurance_ref) < 4):
            return self._json({"error": "record separate independent qualification and insurer checks and references"}, 400)
        raw_areas = data.get("service_areas")
        if not isinstance(raw_areas, list) or not 1 <= len(raw_areas) <= 25 or any(
                not isinstance(a, str) or not 2 <= len(a.strip()) <= 70 for a in raw_areas):
            return self._json({"error": "list 1-25 explicitly checked service areas or postcode outward codes"}, 400)
        areas = sorted(set(a.strip().upper() for a in raw_areas))
        verified_trades = data.get("verified_trades")
        submitted = {str(t).lower() for t in reg.get("trades", []) if isinstance(t, str)}
        if (not isinstance(verified_trades, list) or not verified_trades
                or any(not isinstance(t, str) or t.lower() not in submitted for t in verified_trades)):
            return self._json({"error": "choose verified trades from the registered trade list"}, 400)
        scopes = sorted(set(t.lower().strip() for t in verified_trades))
        gas_info = None
        if "gas" in scopes:
            gas = self.contractor_verified_document(stage, pid, data.get("gas_document_id"))
            gas_ref = str(data.get("gas_register_reference") or "").strip()[:160]
            if (not gas or gas["id"] in {d["id"] for d in docs.values()}
                    or not reg.get("gas_safe_number") or len(gas_ref) < 4):
                return self._json({"error": "Gas Safe requires separate verified evidence and an independent current register check"}, 409)
            gas_info = {"document_id": gas["id"], "document_verified_at": gas["verified_at"],
                        "register_reference": gas_ref, "number": reg["gas_safe_number"]}
            gas_expiry = datetime.strptime(gas["expiry_date"], "%Y-%m-%d").date()
            if expires > gas_expiry:
                return self._json({"error": "review date exceeds verified gas qualification expiry"}, 409)
        previous = reg.get("contractor_verification")
        if isinstance(previous, dict) and previous.get("status") == "verified":
            previous["status"] = "superseded"
            previous["superseded_at"] = now()
        verification = {
            "status": "verified", "checked_at": now(), "checked_by": (self.user or {}).get("username", "agent"),
            "party_id": pid, "registration_id": reg["id"], "valid_until": valid_until,
            "insurance_document_id": docs["insurance"]["id"],
            "insurance_document_verified_at": docs["insurance"]["verified_at"],
            "qualification_document_id": docs["qualification"]["id"],
            "qualification_document_verified_at": docs["qualification"]["verified_at"],
            "check_source": source, "external_check_reference": ref,
            "insurance_check_source": insurance_source, "insurance_check_reference": insurance_ref,
            "service_areas": areas, "verified_trades": scopes, "gas": gas_info,
        }
        reg.setdefault("verification_history", []).append(verification)
        reg["contractor_verification"] = verification
        self.audit(stage, {"actor": (self.user or {}).get("display_name", "Agent"),
                           "action": "contractor_independent_checks_recorded",
                           "target": reg["id"], "note": f"{pid}; expiry {valid_until}; {','.join(scopes)}"})
        save_stage(stage)
        return self._json({"success": True, "verification_status": "verified",
                           "valid_until": valid_until})

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
            if (not registration
                    or registration.get("role") not in ("landlord", "trades")
                    or registration.get("role") not in party["roles"]
                    or registration.get("status") != "approved"
                    or (registration.get("role") == "landlord" and kind != "person")
                    or (registration.get("role") == "trades"
                        and (not registration.get("credentials_checked_at")
                             or registration.get("prospect_stage") in ("suspended", "rejected")))):
                return self._json({"error": "link only a matching approved registration to this Party"}, 409)
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

    def repair_authority(self, stage, property_id):
        """Return active, signed property authority from its real linked owner."""
        prop = self.find_prop(stage, property_id)
        if not prop:
            return None
        owners = set()
        if isinstance(prop.get("landlord_party_id"), str):
            owners.add(prop["landlord_party_id"])
        owners.update(pid for pid in prop.get("landlord_party_ids", [])
                      if isinstance(pid, str))
        if not owners:
            return None
        matches = [
            a for a in stage.get("management_agreements", [])
            if a.get("landlord_party_id") in owners
            and a.get("agreement_type") == "full_management"
            and a.get("status") == "active"
            and a.get("signed_at")
            and property_id in a.get("property_ids", [])
            and type(a.get("spending_limit_pence")) is int
            and 0 <= a["spending_limit_pence"] <= 100000000
        ]
        if len(matches) != 1:
            return None
        a = matches[0]
        return {
            "agreement_id": a["id"],
            "limit_pence": a["spending_limit_pence"],
            "mandate_version": a.get("updated_at"),
        }

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
            raw_limit = data.get("spending_limit_pence")
            try:
                spend_limit = None if raw_limit in (None, "") else int(raw_limit)
            except (TypeError, ValueError):
                return self._json({"error": "spending limit must be an integer amount in pence"}, 400)
            if spend_limit is not None and not (0 <= spend_limit <= 100000000):
                return self._json({"error": "spending limit must be between £0 and £1,000,000"}, 400)
            agreement_num = int(stage.get("next_management_agreement_id", 1))
            aid = "management-" + str(agreement_num)
            at = now()
            agreement = {
                "id": aid, "landlord_party_id": landlord_id, "property_ids": property_ids,
                "agreement_type": agreement_type, "management_fee_bps": fee_bps,
                "spending_limit_pence": spend_limit,
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

    # ---------- authenticated landlord property onboarding ----------
    def handle_landlord_property_submission(self, data):
        """Receive a property for review; do NOT advertise it or create a listing."""
        user = self.user
        stage = load_stage()
        party_ids = sorted(self.account_party_ids(stage, user, "landlord"))
        if not party_ids:
            return self._json({"error": "your landlord account is not linked to an active Party"}, 403)
        fields = ("address", "postcode", "area", "property_type", "description")
        vals = {}
        for key in fields:
            raw = data.get(key, "")
            if not isinstance(raw, str):
                return self._json({"error": key + " must be text"}, 400)
            vals[key] = raw.strip()
        for key in ("address", "postcode", "area"):
            if not vals[key]:
                return self._json({"error": key + " is required"}, 400)
        for key, limit in (("address", 200), ("postcode", 20), ("area", 120),
                           ("property_type", 60), ("description", 1500)):
            if len(vals[key]) > limit:
                return self._json({"error": key + " is too long"}, 400)
        try:
            beds = int(data.get("beds"))
            rent = int(data.get("rent_pence"))
        except (TypeError, ValueError):
            return self._json({"error": "bedrooms and monthly rent are required"}, 400)
        if not 0 <= beds <= 30 or not 1 <= rent <= 10000000:
            return self._json({"error": "enter a valid bedroom count and monthly rent"}, 400)

        submission_id = data.get("submission_id")
        items = stage.setdefault("property_submissions", [])
        existing = None
        if submission_id is not None:
            if not isinstance(submission_id, str) or len(submission_id) > 100:
                return self._json({"error": "invalid submission reference"}, 400)
            existing = next((s for s in items if s.get("id") == submission_id), None)
            if not existing:
                return self._json({"error": "submission not found"}, 404)
            if (existing.get("created_by_account_id") != user.get("account_id")
                    or existing.get("landlord_party_id") not in party_ids):
                return self._json({"error": "not your submission"}, 403)
            if existing.get("status") != "changes_requested":
                return self._json({"error": "only submissions needing changes can be resubmitted"}, 409)

        at = now()
        if existing:
            submission = existing
            action = "property_submission_resubmitted"
        else:
            num = int(stage.get("next_property_submission_id", 1))
            submission = {
                "id": "submission-" + str(num),
                "landlord_party_id": party_ids[0],
                "created_by_account_id": user["account_id"],
                "created_at": at,
                "review_history": [],
            }
            stage["next_property_submission_id"] = num + 1
            items.append(submission)
            action = "property_submission_received"
        submission.update(vals)
        submission.update({
            "beds": beds, "rent_pence": rent, "status": "pending",
            "submitted_at": at, "reviewed_at": None, "agent_note": "",
        })
        submission["review_history"].append({
            "at": at, "by": user.get("username", "landlord"), "action": "submitted",
        })
        self.audit(stage, {
            "actor": user.get("username", "landlord"), "action": action,
            "target": submission["id"], "note": submission["address"],
        })
        save_stage(stage)
        return self._json({"success": True, "submission_id": submission["id"], "status": "pending"})

    def handle_agent_property_submission(self, data):
        """An agent reviews a landlord's submission; approval only creates onboarding."""
        stage = load_stage()
        submission_id = str(data.get("submission_id", ""))[:100]
        submission = next((s for s in stage.get("property_submissions", [])
                           if s.get("id") == submission_id), None)
        if not submission:
            return self._json({"error": "submission not found"}, 404)
        if submission.get("status") != "pending":
            return self._json({"error": "submission is not pending review"}, 409)
        action = data.get("action")
        if action not in ("approve", "request_changes", "decline"):
            return self._json({"error": "invalid review action"}, 400)
        raw_note = data.get("note", "")
        if not isinstance(raw_note, str) or len(raw_note) > 1000:
            return self._json({"error": "invalid agent note"}, 400)
        note = raw_note.strip()
        if action != "approve" and not note:
            return self._json({"error": "give the landlord a reason or question"}, 400)
        party_id = submission.get("landlord_party_id")
        owner = next((p for p in stage.get("parties", [])
                      if p.get("id") == party_id and p.get("status") == "active"
                      and "landlord" in p.get("roles", [])), None)
        if not owner:
            return self._json({"error": "landlord account is no longer active"}, 409)
        if action == "approve":
            num = int(stage.get("next_onboarded_property_id", 1))
            existing_ids = {str(x.get("id")) for x in stage.get("properties", [])}
            while "onboarded-" + str(num) in existing_ids:
                num += 1
            property_id = "onboarded-" + str(num)
            stage["next_onboarded_property_id"] = num + 1
            stage.setdefault("properties", []).append({
                "id": property_id, "title": submission["address"],
                "area": submission["area"], "postcode": submission["postcode"],
                "beds": submission["beds"], "rent": submission["rent_pence"],
                "property_type": submission.get("property_type", ""),
                "landlord": owner.get("display_name", "Landlord"),
                "landlord_party_id": party_id,
                "landlord_party_ids": [party_id],
                "tenant": "", "lifecycle_status": "onboarding",
                "public_listing": {},
                "source_submission_id": submission["id"], "created_at": now(),
            })
            submission["property_id"] = property_id
            submission["status"] = "approved"
        elif action == "request_changes":
            submission["status"] = "changes_requested"
        else:
            submission["status"] = "declined"
        at = now()
        submission["agent_note"] = note
        submission["reviewed_at"] = at
        submission.setdefault("review_history", []).append({
            "at": at, "by": (self.user or {}).get("username", "agent"),
            "action": action, "note": note,
        })
        self.audit(stage, {
            "actor": (self.user or {}).get("username", "agent"),
            "action": "property_submission_" + action,
            "target": submission_id, "note": note or submission["address"],
        })
        save_stage(stage)
        return self._json({
            "success": True, "status": submission["status"],
            "property_id": submission.get("property_id"),
        })

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
        self.case_next(case, "agent", "Review the new enquiry and respond",
                       self.internal_case_target())
        stage["next_case_id"] = case["id"] + 1
        stage.setdefault("cases", []).append(case)
        save_stage(stage)
        self._json({"success": True, "case_id": case["id"], "triage": t})

    # ---------- tenant issues: REPORT → dispatch ----------
    @staticmethod
    def internal_case_target():
        """Internal tracking date only; never a promised response time."""
        return (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()

    def case_next(self, case, actor, action, due_date, changed_by="system"):
        """Keep exactly one next actor, task and target date for a case."""
        case["next_actor"] = actor
        case["next_action"] = action
        case["next_due_at"] = due_date
        case["next_action_updated_at"] = now()
        case["next_action_by"] = changed_by

    def handle_tenant_issue(self, data):
        stage = load_stage()
        prop = self.find_prop(stage, data.get("property_id"))
        if not prop:
            return self._json({"error": "property not found"}, 404)

        issuer = self.user or {}
        role = issuer.get("role")
        if role not in ("tenant", "agent"):
            return self._json({"error": "not authorised"}, 403)

        property_party_ids = set()
        if isinstance(prop.get("tenant_party_id"), str):
            property_party_ids.add(prop["tenant_party_id"])
        if isinstance(prop.get("tenant_party_ids"), list):
            property_party_ids.update(
                x for x in prop["tenant_party_ids"]
                if isinstance(x, str)
            )

        eligible = {
            party["id"] for party in stage.get("parties", [])
            if isinstance(party, dict)
            and party.get("status") == "active"
            and "tenant" in party.get("roles", [])
            and party.get("id") in property_party_ids
        }

        if role == "tenant":
            eligible &= self.account_party_ids(stage, issuer, "tenant")

        requested = data.get("tenant_party_id")
        if requested:
            if requested not in eligible:
                return self._json({"error": "not your property"}, 403)
            tenant_party_id = requested
        elif len(eligible) == 1:
            tenant_party_id = next(iter(eligible))
        elif not eligible:
            return self._json({"error": "not your property"}, 403)
        else:
            return self._json(
                {"error": "select the tenant Party explicitly"}, 409
            )

        message = str(data.get("message", "")).strip()[:3000]
        if not message:
            return self._json({"error": "describe the problem before submitting"}, 400)
        request_id = data.get("request_id")
        if request_id is not None and (
                not isinstance(request_id, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_id)):
            return self._json({"error": "invalid report request id"}, 400)
        if request_id:
            previous = next((case for case in stage.get("cases", [])
                             if case.get("request_id") == request_id
                             and case.get("property_id") == prop["id"]
                             and case.get("tenant_party_id") == tenant_party_id
                             and case.get("created_by_account_id") == issuer.get("account_id")
                             and case.get("type") == "issue"), None)
            if previous:
                if previous.get("message") != message:
                    return self._json({"error": "request id already used for a different report"}, 409)
                return self._json({"success": True, "case_id": previous["id"],
                                   "already_received": True, "triage": previous.get("triage"),
                                   "job_id": None, "document_ids": previous.get("document_ids", [])})
        name = (issuer.get("display_name") if role == "tenant"
                else str(data.get("name", "Tenant"))[:100])
        t = self.triage(message)
        case = {
            "id": stage.get("next_case_id", 490),
            "type": "issue",
            "property_id": prop["id"],
            "tenant_party_id": tenant_party_id,
            "created_by_account_id": issuer.get("account_id"),
            "role": "tenant",
            "name": name or "Tenant",
            "email": str(data.get("email", ""))[:254],
            "message": message,
            "request_id": request_id,
            "status": "reported",
            "triage": t,
            "submitted_at": now(),
        }
        self.case_next(case, "agent", "Review the repair report and decide what happens next",
                       self.internal_case_target())
        stage["next_case_id"] = case["id"] + 1
        stage.setdefault("cases", []).append(case)
        try:
            docs = self.store_case_attachments(stage, case, data.get("attachments"), name or "Tenant")
        except ValueError as exc:
            return self._json({"error": str(exc)}, 400)
        # Intake only. A report is NOT permission to advertise a contractor job.
        # The agent reviews it and dispatches explicitly via /api/case-action.
        self.audit(stage, {"actor": "system", "action": "case_created", "target": case["id"],
                           "note": f"{t['category']}/{t.get('trade','-')} urgency {t['urgency']}"})
        save_stage(stage)
        self._json({"success": True, "case_id": case["id"], "triage": t,
                    "job_id": None,
                    "document_ids": [d["id"] for d in docs] if docs else []})

    def update_case_from_job(self, stage, job):
        """Keep the case handoff aligned with a job transition; no extra case database."""
        case = next((c for c in stage.get("cases", [])
                     if str(c.get("id")) == str(job.get("case_id"))), None)
        if not case or case.get("status") in ("closed", "declined"):
            return
        state = job.get("status")
        next_steps = {
            "triaged": ("agent", "Request an eligible contractor quote"),
            "open": ("agent", "Choose an eligible contractor"),
            "quote_requested": ("trades", "Submit the requested repair quote"),
            "quoted": ("agent", "Review the contractor quote"),
            "awaiting_prework_approval": ("landlord", "Approve or reject the pre-work quote"),
            "pending_verification": ("agent", "Review contractor verification"),
            "assigned": ("trades", "Propose a visit and agree access with the tenant"),
            "in_progress": ("trades", "Complete the agreed work and submit evidence"),
            "invoice_submitted": ("agent", "Review the contractor invoice"),
            "awaiting_approval": ("landlord", "Review the pending contractor invoice"),
            "invoice_approved": ("agent", "Record external payments only after bank verification"),
            "partially_paid": ("agent", "Check and reconcile the remaining contractor invoice balance"),
            "credited": ("agent", "Check fully credited invoice and close any accounting follow-up"),
            "paid": ("tenant", "Confirm repair resolution or ask for follow-up"),
            "rejected": ("agent", "Resolve the rejected invoice or dispute"),
        }
        next_step = next_steps.get(state)
        if next_step:
            self.case_next(case, next_step[0], next_step[1],
                           self.internal_case_target(), "job_workflow")

    # ---------- trades: BOOK → complete → settle or escalate ----------
    def verified_contractor_for_new_repair(self, stage, party_id, required_trade, property_id=None):
        """Require current agent-reviewed independent evidence for new repair work.

        This is a human-documented check, NOT automatic issuer certification.
        """
        party = next((p for p in stage.get("parties", [])
                      if p.get("id") == party_id and p.get("status") == "active"
                      and "trades" in p.get("roles", []) and p.get("account_id")), None)
        if not party:
            return False
        reg = next((r for r in stage.get("registrations", [])
                    if r.get("id") == party.get("source_registration_id")
                    and r.get("party_id") == party_id and r.get("role") == "trades"
                    and r.get("name") == party.get("display_name")
                    and r.get("status") == "approved"
                    and r.get("prospect_stage") not in ("suspended", "rejected")), None)
        if not reg:
            return False
        verify = reg.get("contractor_verification")
        if not isinstance(verify, dict) or verify.get("status") != "verified":
            return False
        if (verify.get("party_id") != party_id or verify.get("registration_id") != reg.get("id")
                or not verify.get("checked_at") or not verify.get("checked_by")
                or not verify.get("external_check_reference")
                or not verify.get("insurance_check_reference")):
            return False
        try:
            today = datetime.now(timezone.utc).date()
            expires = datetime.strptime(verify["valid_until"], "%Y-%m-%d").date()
            insurance_end = datetime.strptime(reg["insurance_expiry"], "%Y-%m-%d").date()
            checked_at = datetime.fromisoformat(verify["checked_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError, TypeError):
            return False
        if (expires < today or insurance_end < expires or checked_at.tzinfo is None
                or checked_at.astimezone(timezone.utc).date() > today):
            return False
        for kind in ("insurance", "qualification"):
            doc = self.contractor_verified_document(stage, party_id, verify.get(kind + "_document_id"))
            if not doc or doc.get("verified_at") != verify.get(kind + "_document_verified_at"):
                return False
            if datetime.strptime(doc["expiry_date"], "%Y-%m-%d").date() < expires:
                return False
        if not verify.get("service_areas"):
            return False
        submitted_trades = {str(t).strip().lower() for t in reg.get("trades", []) if isinstance(t, str)}
        if not verify.get("verified_trades") or not set(verify["verified_trades"]).issubset(submitted_trades):
            return False
        if required_trade:
            required_trade = str(required_trade).strip().lower()
            if required_trade not in verify.get("verified_trades", []):
                return False
            if required_trade == "gas":
                gas = verify.get("gas")
                if not isinstance(gas, dict) or gas.get("number") != reg.get("gas_safe_number"):
                    return False
                doc = self.contractor_verified_document(stage, party_id, gas.get("document_id"))
                if (not doc or doc.get("verified_at") != gas.get("document_verified_at")
                        or not gas.get("register_reference")
                        or datetime.strptime(doc["expiry_date"], "%Y-%m-%d").date() < expires):
                    return False
        if property_id:
            prop = self.find_prop(stage, property_id)
            if not prop or not self.contractor_location_match(verify, prop):
                return False
        return True

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

    @staticmethod
    def money_lines(lines):
        """Validate VAT-inclusive totals using integer pence. Nothing inferred from VAT rules."""
        if not isinstance(lines, list) or not 1 <= len(lines) <= 25:
            raise ValueError("provide between 1 and 25 itemised lines")
        result = []
        for item in lines:
            if not isinstance(item, dict):
                raise ValueError("each line must be an object")
            desc = item.get("description")
            net = item.get("net_pence")
            rate = item.get("vat_rate_bps")
            if not isinstance(desc, str) or not 2 <= len(desc.strip()) <= 200:
                raise ValueError("a 2-200 character line description is required")
            if type(net) is not int or not 1 <= net <= 1000000000:
                raise ValueError("net_pence must be a positive integer")
            if type(rate) is not int or rate not in (0, 500, 2000):
                raise ValueError("VAT must be explicitly marked 0%, 5%, or 20%; Roger does not decide the tax rate")
            vat = (net * rate + 5000) // 10000
            result.append({"description": desc.strip(), "net_pence": net,
                           "vat_rate_bps": rate, "vat_pence": vat,
                           "gross_pence": net + vat})
        total = sum(x["gross_pence"] for x in result)
        if total > 1000000000:
            raise ValueError("total exceeds the supported maximum")
        return {"lines": result, "net_pence": sum(x["net_pence"] for x in result),
                "vat_pence": sum(x["vat_pence"] for x in result), "gross_pence": total}

    @staticmethod
    def invoice_balance(job):
        """Manual external money entries only; never infer bank settlement from approval."""
        invoice = job.get("invoice_pence") or 0
        if not isinstance(invoice, int) or invoice < 0:
            raise ValueError("invoice amount is invalid")
        paid = sum(p["amount_pence"] for p in job.get("payments", []) if isinstance(p, dict))
        credited = sum(c["amount_pence"] for c in job.get("credit_notes", []) if isinstance(c, dict))
        return {"invoice_pence": invoice, "paid_pence": paid,
                "credited_pence": credited, "outstanding_pence": invoice - paid - credited}

    def approve_job_variation(self, stage, job, variation, actor):
        """Only approved extra work raises authorised gross cost; never overwrite base quote."""
        extra = variation["extra_pence"]
        before = job["approved_quote_pence"]
        after = before + extra
        job["approved_quote_pence"] = after
        variation["status"] = "approved"
        variation["approved_at"] = now()
        variation["approved_by"] = actor
        variation["total_authorised_pence"] = after
        job.setdefault("approved_variations", []).append(dict(variation))
        job.pop("pending_variation", None)
        self.audit(stage, {"actor": actor, "action": "variation_approved",
                           "target": job["id"], "note": f"+{extra}p total {after}p"})
        self.post_msg(stage, job["case_id"],
                      "Additional work was approved before that extra work starts. "
                      f"Revised maximum authorised amount £{after/100:.2f}.",
                      to=("tenant", "landlord", "trades"))

    def handle_job_action(self, data):
        stage = load_stage()
        action = data.get("action")
        job = next((j for j in stage.get("jobs", []) if j["id"] == data.get("id")), None)
        if not job:
            return self._json({"error": "job not found"}, 404)
        role = (self.user or {}).get("role")
        AGENT_ONLY = {"assign", "request_quote", "approve_quote", "decline_quote",
                      "send_to_landlord", "verify_approve", "verify_decline",
                      "approve_invoice", "record_payment", "record_credit",
                      "approve_variation", "decline_variation"}
        TRADES_ONLY = {"accept", "start", "complete", "release", "submit_quote",
                       "submit_variation"}
        if action in AGENT_ONLY and role != "agent":
            return self._json({"error": "agent-only move"}, 403)
        if action in TRADES_ONLY and role != "trades":
            return self._json({"error": "tradesperson-only move"}, 403)
        actor = (self.user or {}).get("display_name") or "Unknown"
        selected_party_id = None

        if action in TRADES_ONLY:
            ids = self.account_party_ids(
                stage, self.user or {}, "trades"
            )
            if not ids:
                return self._json({"error": "unlinked contractor"}, 403)

            if action == "accept":
                if (job.get("status") != "open"
                        or job.get("assigned_to")
                        or job.get("requested_by")
                        or job.get("assigned_to_party_id")
                        or job.get("requested_by_party_id")):
                    return self._json({"error": "job is not open"}, 409)

                requested = data.get("trades_party_id")
                if requested is not None:
                    if not isinstance(requested, str) or requested not in ids:
                        return self._json({"error": "not your Party"}, 403)
                    selected_party_id = requested
                elif len(ids) == 1:
                    selected_party_id = next(iter(ids))
                else:
                    return self._json(
                        {"error": "select your contractor Party"}, 409
                    )
            else:
                assigned = job.get("assigned_to_party_id")
                if not isinstance(assigned, str) or assigned not in ids:
                    return self._json({"error": "not your job"}, 403)

                allowed_states = {
                    "start": {"assigned"},
                    "complete": {"in_progress"},
                    "release": {
                        "assigned", "in_progress", "quote_requested"
                    },
                    "submit_quote": {"quote_requested"},
                    "submit_variation": {"assigned", "in_progress"},
                }
                if job.get("status") not in allowed_states[action]:
                    return self._json(
                        {"error": "invalid job transition"}, 409
                    )
                selected_party_id = assigned

        if action in ("assign", "request_quote"):
            selected_party_id = data.get("trades_party_id")
            matches = [
                party for party in stage.get("parties", [])
                if isinstance(party, dict)
                and isinstance(selected_party_id, str)
                and party.get("id") == selected_party_id
                and party.get("status") == "active"
                and "trades" in party.get("roles", [])
                and party.get("account_id")
            ]
            if len(matches) != 1:
                return self._json(
                    {"error": "verified contractor Party required"}, 409
                )
            if data.get("tradesperson") != matches[0].get("display_name"):
                return self._json(
                    {"error": "contractor identity mismatch"}, 409
                )
            if (job.get("requires_prework_quote") and
                    not self.verified_contractor_for_new_repair(
                        stage, selected_party_id, job.get("required_trade"), job.get("property_id"))):
                return self._json({
                    "error": "contractor must have an approved linked registration, valid checked credentials, and current insurance for this trade"
                }, 409)

        if (action == "verify_approve"
                and job.get("status") == "pending_verification"):
            pending_id = job.get("requested_by_party_id")
            matches = [
                party for party in stage.get("parties", [])
                if isinstance(party, dict)
                and party.get("id") == pending_id
                and isinstance(pending_id, str)
                and party.get("status") == "active"
                and "trades" in party.get("roles", [])
                and party.get("account_id")
            ]
            if len(matches) != 1:
                return self._json(
                    {"error": "unverified contractor identity"}, 409
                )

        # Regulated jobs never rely on the legacy in-memory/claimed certificate profile.
        if (job.get("required_trade") in CERT_REQUIRED
                and action in ("assign", "accept", "request_quote", "verify_approve", "start")):
            regulated_party = selected_party_id or job.get("assigned_to_party_id")
            if not self.verified_contractor_for_new_repair(
                    stage, regulated_party, job.get("required_trade"), job.get("property_id")):
                return self._json({"error": "regulated work requires current independent trade register evidence and service area"}, 409)

        # Newly triaged repairs cannot skip quote and work authorisation.
        if job.get("requires_prework_quote"):
            if action in ("accept", "assign", "verify_approve"):
                return self._json({"error": "quote approval required before assignment"}, 409)
            if action == "start":
                if not job.get("work_authorised_at") or not job.get("approved_quote_pence"):
                    return self._json({"error": "work not authorised"}, 409)
                if not self.verified_contractor_for_new_repair(
                        stage, job.get("assigned_to_party_id"), job.get("required_trade"), job.get("property_id")):
                    return self._json({"error": "contractor approval or insurance expired; work cannot start"}, 409)
        if action == "complete":
            if job.get("pending_variation"):
                return self._json({"error": "resolve outstanding extra-work request before invoicing"}, 409)
            try:
                proposed_invoice = int(data.get("invoice_pence", 0))
            except (ValueError, TypeError):
                return self._json({"error": "valid invoice amount required"}, 400)
            if proposed_invoice <= 0 or type(data.get("invoice_pence")) not in (int, str):
                return self._json({"error": "positive amount in pence required"}, 400)
            quoted_amount = job.get("approved_quote_pence")
            if job.get("requires_prework_quote") and (
                    not isinstance(quoted_amount, int) or proposed_invoice > quoted_amount):
                return self._json({"error": "invoice exceeds authorised work; approve a variation first"}, 409)
            invoice_number = str(data.get("invoice_number") or "").strip().upper()
            if invoice_number and (len(invoice_number) > 80
                                   or not re.fullmatch(r"[A-Z0-9][A-Z0-9 /_.-]*", invoice_number)):
                return self._json({"error": "invoice number contains unsupported characters"}, 400)
            if invoice_number and any(
                    other.get("id") != job["id"]
                    and other.get("assigned_to_party_id") == job.get("assigned_to_party_id")
                    and other.get("invoice_number") == invoice_number
                    for other in stage.get("jobs", [])):
                return self._json({"error": "duplicate supplier invoice number"}, 409)
            if "line_items" in data:
                try:
                    invoice_items = self.money_lines(data["line_items"])
                except ValueError as exc:
                    return self._json({"error": str(exc)}, 400)
                if invoice_items["gross_pence"] != proposed_invoice:
                    return self._json({"error": "invoice lines plus VAT must equal invoice amount"}, 409)
            else:
                invoice_items = None
        if action == "approve_invoice":
            if job.get("status") != "invoice_submitted":
                return self._json({"error": "invoice must be submitted before approval"}, 409)
            amount = job.get("invoice_pence")
            if not isinstance(amount, int) or amount <= 0:
                return self._json({"error": "valid invoice required"}, 409)
            quoted = job.get("approved_quote_pence")
            if isinstance(quoted, int) and amount > quoted:
                return self._json({"error": "invoice exceeds approved quote"}, 409)
        if action in ("record_payment", "record_credit"):
            if job.get("status") not in ("invoice_approved", "partially_paid"):
                return self._json({"error": "approved invoice required before manual settlements"}, 409)
            balances = self.invoice_balance(job)
            if balances["outstanding_pence"] <= 0:
                return self._json({"error": "invoice is settled"}, 409)
            if action == "record_payment":
                reference = str(data.get("payment_reference") or "").strip()[:120]
                payment_date = str(data.get("payment_date") or "").strip()
                try:
                    parsed_date = datetime.strptime(payment_date, "%Y-%m-%d").date()
                    payment_amount = int(data.get("payment_amount_pence", 0))
                except (ValueError, TypeError):
                    return self._json({"error": "valid external payment date and amount required"}, 400)
                if not reference or parsed_date > datetime.now(timezone.utc).date():
                    return self._json({"error": "real external reference and a non-future date required"}, 400)
                if payment_amount <= 0 or payment_amount > balances["outstanding_pence"]:
                    return self._json({"error": "payment exceeds outstanding invoice"}, 409)
                if any(p.get("reference") == reference for p in job.get("payments", [])):
                    return self._json({"error": "duplicate external payment reference"}, 409)
            else:
                credit_number = str(data.get("credit_note_number") or "").strip().upper()[:80]
                credit_reason = str(data.get("credit_reason") or "").strip()[:500]
                try:
                    credit_amount = int(data.get("credit_amount_pence", 0))
                except (ValueError, TypeError):
                    return self._json({"error": "valid credit amount required"}, 400)
                if not credit_reason or not re.fullmatch(r"[A-Z0-9][A-Z0-9 /_.-]*", credit_number):
                    return self._json({"error": "supplier credit note number and reason required"}, 400)
                if credit_amount <= 0 or credit_amount > balances["outstanding_pence"]:
                    return self._json({"error": "credit exceeds outstanding invoice"}, 409)
                if any(c.get("number") == credit_number for j in stage.get("jobs", [])
                       if j.get("assigned_to_party_id") == job.get("assigned_to_party_id")
                       for c in j.get("credit_notes", [])):
                    return self._json({"error": "duplicate supplier credit number"}, 409)

        if action == "accept":
            chk = self.credential_check(job, actor)
            if chk["ok"]:
                job["status"] = "in_progress"
                job["assigned_to"] = actor
                job["assigned_to_party_id"] = selected_party_id
                self.sync_case(stage, job["case_id"], "in_progress")
                self.post_msg(stage, job["case_id"], f"{actor} took this job and will get in touch to arrange access.", to=("tenant",))
                self.audit(stage, {"actor": actor, "action": "job_booked", "target": job["id"]})
            else:
                # human decision required before a cert-gated job can be booked
                job["status"] = "pending_verification"
                job["requested_by"] = actor
                job["requested_by_party_id"] = selected_party_id
                job["gate_reason"] = chk["reason"]
                self.audit(stage, {"actor": actor, "action": "job_booking_blocked_pending_verification",
                                   "target": job["id"], "note": chk["reason"]})
        elif action == "verify_approve" and job["status"] == "pending_verification":
            job["status"] = "in_progress"
            job["assigned_to"] = job.pop("requested_by", None)
            job["assigned_to_party_id"] = job.pop(
                "requested_by_party_id"
            )
            job.pop("gate_reason", None)
            job["override_by"] = "agent"
            self.sync_case(stage, job["case_id"], "in_progress")
            self.audit(stage, {"actor": "agent", "action": "booking_overridden", "target": job["id"]})
        elif action == "verify_decline" and job["status"] == "pending_verification":
            job["status"] = "open"
            job.pop("requested_by", None)
            job.pop("requested_by_party_id", None)
            job.pop("gate_reason", None)
            self.audit(stage, {"actor": "agent", "action": "booking_declined", "target": job["id"]})
        elif action == "release" and job["status"] in ("in_progress", "assigned", "quote_requested"):
            job["status"] = "triaged" if job.get("requires_prework_quote") else "open"
            if job.get("requires_prework_quote"):
                job.pop("work_authorised_at", None)
                job.pop("work_authorised_by", None)
                job.pop("approved_quote_pence", None)
                for quote in job.get("quotes", []):
                    if quote.get("status") == "approved":
                        quote["status"] = "superseded"
            job["assigned_to"] = None
            job.pop("assigned_to_party_id", None)
            job.pop("requested_by", None)
            job.pop("requested_by_party_id", None)
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
            job["assigned_to_party_id"] = selected_party_id
            c = self.post_msg(stage, job["case_id"], f"{who} has been put on this job by the agency.", to=("tenant", "trades"))
            self.audit(stage, {"actor": "agent", "action": "job_assigned", "target": job["id"], "note": who})
        elif action in ("request_quote",) and self.user["role"] == "agent" and job["status"] in ("triaged", "open", "assigned"):
            who = str(data.get("tradesperson", ""))[:100]
            known = {t["company"] for t in self.approved_trades(stage)}
            if who not in known:
                return self._json({"error": f"{who or 'nobody'} is not an approved tradesperson"}, 400)
            job["status"] = "quote_requested"
            job["assigned_to"] = who
            job["assigned_to_party_id"] = selected_party_id
            self.post_msg(stage, job["case_id"], f"Quote requested from {who} — the work starts once the agency approves a price.", to=("trades",))
            self.audit(stage, {"actor": "agent", "action": "quote_requested", "target": job["id"], "note": who})
        elif action == "submit_quote" and job["status"] == "quote_requested":
            try:
                quote_pence = int(data.get("quote_pence", 0))
            except (TypeError, ValueError):
                return self._json({"error": "quote must be a positive amount in pence"}, 400)
            if quote_pence <= 0:
                return self._json({"error": "quote must be greater than zero"}, 400)
            if "line_items" in data:
                try:
                    breakdown = self.money_lines(data["line_items"])
                except ValueError as exc:
                    return self._json({"error": str(exc)}, 400)
                if breakdown["gross_pence"] != quote_pence:
                    return self._json({"error": "quote items plus VAT must equal total quote"}, 409)
            else:
                breakdown = None  # existing clients remain compatible, flagged as legacy
            job["quotes"] = job.get("quotes", [])
            q = {"tradesperson": actor, "pence": quote_pence,
                 "version": len(job["quotes"]) + 1,
                 "pricing_format": "itemised" if breakdown else "legacy_lump_sum",
                 "line_items": breakdown["lines"] if breakdown else [],
                 "net_pence": breakdown["net_pence"] if breakdown else None,
                 "vat_pence": breakdown["vat_pence"] if breakdown else None,
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
            if job.get("requires_prework_quote"):
                if not self.verified_contractor_for_new_repair(
                        stage, job.get("assigned_to_party_id"), job.get("required_trade"), job.get("property_id")):
                    return self._json({"error": "contractor is no longer eligible for this repair"}, 409)
                mandate = self.repair_authority(stage, job.get("property_id"))
                if not mandate:
                    return self._json({"error": "signed, active management mandate with a spending limit required for this property"}, 409)
                limit = mandate["limit_pence"]
                if q["pence"] > limit:
                    prop = self.find_prop(stage, job.get("property_id"))
                    landlord_id = (prop or {}).get("landlord_party_id")
                    eligible = any(
                        p.get("id") == landlord_id
                        and p.get("status") == "active"
                        and "landlord" in p.get("roles", [])
                        and p.get("account_id")
                        for p in stage.get("parties", [])
                    )
                    if not eligible:
                        return self._json({"error": "active linked landlord account required for approval"}, 409)
                    q["status"] = "pending_landlord"
                    job["mandate_snapshot"] = dict(mandate)
                    job["approved_quote_pence"] = q["pence"]
                    job["approved_quote_version"] = q["version"]
                    job["status"] = "awaiting_prework_approval"
                    stage.setdefault("approvals", [])
                    stage["approvals"].append({
                        "id": "appr-" + str(len(stage["approvals"]) + 1),
                        "approval_type": "prework_quote",
                        "job_id": job["id"], "property_id": job["property_id"],
                        "landlord": prop.get("landlord", "Landlord"),
                        "landlord_party_id": landlord_id,
                        "landlord_party_ids": prop.get("landlord_party_ids", []),
                        "amount_pence": q["pence"], "reason": job.get("message", ""),
                        "quote_at": q["at"], "quote_version": q["version"],
                        "quote_lines": q.get("line_items", []), "quote_net_pence": q.get("net_pence"),
                        "quote_vat_pence": q.get("vat_pence"), "scope": q.get("note", ""),
                        "mandate_snapshot": dict(mandate),
                        "evidence": {"tradesperson": job.get("assigned_to"),
                                     "job_created": job.get("created_at")},
                        "status": "pending", "requested_at": now(),
                    })
                    self.sync_case(stage, job["case_id"], "awaiting_prework_approval")
                    self.post_msg(stage, job["case_id"],
                                  "Landlord quote approval is required before work starts.",
                                  to=("tenant", "landlord", "trades"))
                    self.audit(stage, {"actor": actor, "action": "prework_landlord_approval_requested",
                                       "target": job["id"], "note": str(q["pence"]) + "p"})
                else:
                    q["status"] = "approved"
                    job["mandate_snapshot"] = dict(mandate)
                    job["approved_quote_pence"] = q["pence"]
                    job["approved_quote_version"] = q["version"]
                    job["status"] = "assigned"
                    job["work_authorised_at"] = now()
                    job["work_authorised_by"] = actor
                    self.sync_case(stage, job["case_id"], "dispatched")
                    self.post_msg(stage, job["case_id"],
                                  f"Quote of £{q['pence']/100:.2f} authorised. The contractor can now arrange work.",
                                  to=("tenant", "trades"))
                    self.audit(stage, {"actor": actor, "action": "prework_quote_authorised",
                                       "target": job["id"], "note": str(q["pence"]) + "p"})
            else:
                q["status"] = "approved"
                job["approved_quote_pence"] = q["pence"]
                job["approved_quote_version"] = q["version"]
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
        elif action == "submit_variation":
            if not job.get("requires_prework_quote") or not job.get("work_authorised_at"):
                return self._json({"error": "approved original work required before proposing an extra"}, 409)
            if job.get("pending_variation"):
                return self._json({"error": "existing variation needs a decision first"}, 409)
            if not self.verified_contractor_for_new_repair(
                    stage, job.get("assigned_to_party_id"), job.get("required_trade"), job.get("property_id")):
                return self._json({"error": "contractor verification expired or revoked"}, 409)
            note = str(data.get("note") or "").strip()[:500]
            try:
                extra = int(data.get("extra_pence", 0))
            except (ValueError, TypeError):
                return self._json({"error": "a valid extra-work amount is required"}, 400)
            if not note or extra <= 0 or extra > 1000000000:
                return self._json({"error": "extra work needs a scope and positive gross amount"}, 400)
            if "line_items" in data:
                try:
                    breakdown = self.money_lines(data["line_items"])
                except ValueError as exc:
                    return self._json({"error": str(exc)}, 400)
                if breakdown["gross_pence"] != extra:
                    return self._json({"error": "variation items and VAT do not match the additional amount"}, 409)
            else:
                breakdown = None
            variation = {
                "id": f"variation-{len(job.get('variation_history', [])) + 1}",
                "extra_pence": extra, "base_authorised_pence": job["approved_quote_pence"],
                "scope": note, "status": "pending_agent",
                "line_items": breakdown["lines"] if breakdown else [],
                "net_pence": breakdown["net_pence"] if breakdown else None,
                "vat_pence": breakdown["vat_pence"] if breakdown else None,
                "requested_at": now(), "requested_by": actor,
            }
            job["pending_variation"] = variation
            job.setdefault("variation_history", []).append(variation)
            self.audit(stage, {"actor": actor, "action": "variation_requested",
                               "target": job["id"], "note": f"+{extra}p"})
            self.post_msg(stage, job["case_id"],
                          "Contractor requested approval for additional work. "
                          "No additional work is authorised until a decision is recorded.",
                          to=("tenant", "landlord", "trades"))
        elif action in ("approve_variation", "decline_variation"):
            variation = job.get("pending_variation")
            if not variation or variation.get("status") != "pending_agent":
                return self._json({"error": "no extra-work request awaiting agent"}, 409)
            if variation.get("base_authorised_pence") != job.get("approved_quote_pence"):
                return self._json({"error": "authorised cost changed; ask for a new variation"}, 409)
            if not job.get("work_authorised_at") or job.get("status") not in ("assigned", "in_progress"):
                return self._json({"error": "job not authorised for extra work"}, 409)
            if action == "decline_variation":
                reason = str(data.get("reason") or "").strip()[:500]
                if not reason:
                    return self._json({"error": "reason is required"}, 400)
                variation["status"] = "declined"
                variation["decision_reason"] = reason
                variation["decided_at"] = now()
                job.pop("pending_variation", None)
                self.audit(stage, {"actor": actor, "action": "variation_declined",
                                   "target": job["id"], "note": reason})
            else:
                if not self.verified_contractor_for_new_repair(
                        stage, job.get("assigned_to_party_id"), job.get("required_trade"), job.get("property_id")):
                    return self._json({"error": "contractor no longer approved"}, 409)
                mandate = self.repair_authority(stage, job.get("property_id"))
                if not mandate:
                    return self._json({"error": "active signed mandate required"}, 409)
                combined = job["approved_quote_pence"] + variation["extra_pence"]
                if combined > mandate["limit_pence"]:
                    prop = self.find_prop(stage, job["property_id"]) or {}
                    landlord_id = prop.get("landlord_party_id")
                    if not any(p.get("id") == landlord_id and p.get("status") == "active"
                               and "landlord" in p.get("roles", []) and p.get("account_id")
                               for p in stage.get("parties", [])):
                        return self._json({"error": "active linked landlord required"}, 409)
                    variation["status"] = "pending_landlord"
                    stage.setdefault("approvals", []).append({
                        "id": f"appr-{len(stage.get('approvals', [])) + 1}",
                        "approval_type": "variation_quote",
                        "job_id": job["id"], "property_id": job["property_id"],
                        "landlord_party_id": landlord_id,
                        "landlord_party_ids": prop.get("landlord_party_ids", []),
                        "amount_pence": combined, "extra_pence": variation["extra_pence"],
                        "variation_id": variation["id"],
                        "base_authorised_pence": variation["base_authorised_pence"],
                        "scope": variation["scope"], "line_items": variation["line_items"],
                        "mandate_snapshot": dict(mandate),
                        "status": "pending", "requested_at": now()
                    })
                    self.audit(stage, {"actor": actor, "action": "variation_landlord_approval_requested",
                                       "target": job["id"], "note": f"total {combined}p"})
                else:
                    self.approve_job_variation(stage, job, variation, actor)
        elif action == "send_to_landlord" and self.user["role"] == "agent":
            if job["status"] not in ("invoice_submitted", "invoice_approved") or not job.get("invoice_pence"):
                return self._json({"error": "a submitted invoice is required"}, 409)
            prop = self.find_prop(stage, job["property_id"]) or {}
            stage.setdefault("approvals", [])
            stage["approvals"].append({
                "id": f"appr-{len(stage['approvals']) + 1}", "job_id": job["id"],
                "property_id": job["property_id"], "landlord": prop.get("landlord", "Landlord"),
                    "landlord_party_id": prop.get("landlord_party_id"),
                    "landlord_party_ids": prop.get("landlord_party_ids", []),
                "amount_pence": job["invoice_pence"], "reason": job["message"],
                "evidence": {"tradesperson": job.get("assigned_to"), "job_created": job.get("created_at"),
                             "work_completed": job.get("completed_at")},
                "status": "pending", "requested_at": now(),
                "sent_by_agent": True})
            job["status"] = "awaiting_approval"
            # Invoice review must not overwrite the tenant's repair status.
            self.post_msg(stage, job["case_id"], "The agency has sent your invoice to the landlord for sign-off.", to=("trades",))
            self.audit(stage, {"actor": "agent", "action": "invoice_sent_to_landlord", "target": job["id"],
                               "note": f"£{job['invoice_pence']/100:.2f}"})
        elif action == "start" and job["status"] == "assigned":
            job["status"] = "in_progress"
            self.sync_case(stage, job["case_id"], "in_progress")
            self.audit(stage, {"actor": actor, "action": "job_started", "target": job["id"]})
        elif action == "complete" and job["status"] == "in_progress":
            job["invoice_pence"] = proposed_invoice
            job["invoice_number"] = invoice_number or None
            job["invoice_number_status"] = "supplied" if invoice_number else "legacy_missing"
            job["invoice_line_items"] = invoice_items["lines"] if invoice_items else []
            job["invoice_net_pence"] = invoice_items["net_pence"] if invoice_items else None
            job["invoice_vat_pence"] = invoice_items["vat_pence"] if invoice_items else None
            job["invoice_itemisation_status"] = "itemised" if invoice_items else "legacy_lump_sum"
            job["invoice_approved_quote_version"] = job.get("approved_quote_version")
            job["invoice_approved_gross_limit_pence"] = job.get("approved_quote_pence")
            job["payments"] = []
            job["credit_notes"] = []
            job["completed_at"] = now()
            limit = stage.get("authority", {}).get("standing_limit_pence", 15000)
            # New jobs were authorised at the quoted price BEFORE work.
            # Do not ask for a second landlord approval for that same cost;
            # an invoice still needs the agent's explicit review and payment.
            if job.get("requires_prework_quote"):
                job["status"] = "invoice_submitted"
                self.sync_case(stage, job["case_id"], "awaiting_confirmation")
                self.post_msg(stage, job["case_id"],
                              "Work submitted. Please confirm whether it is fixed; the agent is reviewing the invoice.",
                              to=("tenant", "trades"))
                self.audit(stage, {"actor": actor, "action": "invoice_submitted",
                                   "target": job["id"], "note": "Pre-approved amount; awaiting agent review"})
            elif job["invoice_pence"] > limit:
                prop = self.find_prop(stage, job["property_id"]) or {}
                stage.setdefault("approvals", [])
                appr = {
                    "id": f"appr-{len(stage['approvals']) + 1}",
                    "job_id": job["id"],
                    "property_id": job["property_id"],
                    "landlord": prop.get("landlord", "Landlord"),
                    "landlord_party_id": prop.get("landlord_party_id"),
                    "landlord_party_ids": prop.get("landlord_party_ids", []),
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
                self.sync_case(stage, job["case_id"], "awaiting_confirmation")
                self.post_msg(stage, job["case_id"], f"Work submitted. Invoice £{job['invoice_pence']/100:.2f} needs landlord review; payment has not been recorded.", to=("tenant", "landlord"))
                self.audit(stage, {"actor": job.get("assigned_to") or "trades", "action": "invoice_submitted",
                                   "target": job["id"], "note": f"£{job['invoice_pence']/100:.2f} above standing authority"})
            else:
                job["status"] = "invoice_submitted"
                self.sync_case(stage, job["case_id"], "awaiting_confirmation")
                self.post_msg(stage, job["case_id"],
                              "Work submitted for your confirmation. The invoice is awaiting the agent's review.",
                              to=("tenant", "trades"))
                self.audit(stage, {"actor": actor, "action": "invoice_submitted",
                                   "target": job["id"], "note": f"£{job['invoice_pence']/100:.2f} awaiting review"})
        elif action == "approve_invoice":
            job["status"] = "invoice_approved"
            job["invoice_approved_at"] = now()
            job["invoice_approved_by"] = actor
            self.post_msg(stage, job["case_id"],
                          "The agent approved the invoice. External payment has not been recorded.",
                          to=("trades", "landlord"))
            self.audit(stage, {"actor": actor, "action": "invoice_approved",
                               "target": job["id"], "note": f"£{job['invoice_pence']/100:.2f}"})
        elif action == "record_payment":
            payment = {
                "reference": reference, "date": parsed_date.isoformat(),
                "amount_pence": payment_amount, "recorded_at": now(),
                "recorded_by": (self.user or {}).get("username", "agent"),
                "evidence_type": "manual_external_reference",
            }
            job.setdefault("payments", []).append(payment)
            job["payment_reference"] = reference  # latest external reference, legacy UI compatibility
            job["payment_amount_pence"] = sum(p["amount_pence"] for p in job["payments"])
            job["payment_recorded_at"] = now()
            job["payment_recorded_by"] = actor
            job["payment_evidence_type"] = "manual_external_reference"
            balances = self.invoice_balance(job)
            job["status"] = "paid" if balances["outstanding_pence"] == 0 else "partially_paid"
            job["paid_at"] = parsed_date.isoformat() + "T00:00:00Z" if job["status"] == "paid" else None
            job["balance_due_pence"] = balances["outstanding_pence"]
            self.post_msg(stage, job["case_id"],
                          "The office recorded an external payment reference; remaining invoice balance "
                          f"£{balances['outstanding_pence']/100:.2f}. No payment was sent by Roger.",
                          to=("trades", "landlord"))
            self.audit(stage, {"actor": actor, "action": "external_payment_recorded",
                               "target": job["id"], "note": f"{reference}: {payment_amount}p"})
        elif action == "record_credit":
            credit = {
                "number": credit_number, "reason": credit_reason,
                "amount_pence": credit_amount, "recorded_at": now(),
                "recorded_by": (self.user or {}).get("username", "agent"),
                "evidence_type": "supplier_credit_recorded",
            }
            job.setdefault("credit_notes", []).append(credit)
            balances = self.invoice_balance(job)
            job["balance_due_pence"] = balances["outstanding_pence"]
            if balances["outstanding_pence"] == 0:
                job["status"] = "paid" if balances["paid_pence"] > 0 else "credited"
            else:
                job["status"] = "partially_paid"
            self.post_msg(stage, job["case_id"],
                          "The office recorded a supplier credit note; invoice balance "
                          f"£{balances['outstanding_pence']/100:.2f}. This is not a bank payment.",
                          to=("trades", "landlord"))
            self.audit(stage, {"actor": actor, "action": "supplier_credit_recorded",
                               "target": job["id"], "note": f"{credit_number}: {credit_amount}p"})
        else:
            return self._json({"error": f"invalid action {action} for status {job['status']}"}, 400)

        self.update_case_from_job(stage, job)
        save_stage(stage)
        self._json({"success": True, "job": job})

    # ---------- landlord: APPROVE / REJECT with reason ----------
    def handle_landlord_action(self, data):
        stage = load_stage()
        appr = next((a for a in stage.get("approvals", []) if a["id"] == data.get("id")), None)
        if not appr:
            return self._json({"error": "approval not found"}, 404)
        user = self.user or {}
        role = user.get("role")
        if role not in ("agent", "landlord"):
            return self._json({"error": "not authorised"}, 403)
        prework = appr.get("approval_type") == "prework_quote"
        variation_approval = appr.get("approval_type") == "variation_quote"
        # A costly quote must be explicitly approved by the correct landlord.
        if (prework or variation_approval) and role != "landlord":
            return self._json({"error": "landlord approval required before work starts"}, 403)
        if role == "landlord":
            ids = self.account_party_ids(stage, user, "landlord")
            prop = self.find_prop(stage, appr.get("property_id"))
            if (not prop
                    or not self.has_party_link(prop, "landlord", ids)
                    or not self.has_party_link(appr, "landlord", ids)):
                return self._json({"error": "not your approval"}, 403)
        if appr["status"] != "pending":
            return self._json({"error": "already decided"}, 409)
        action = data.get("action")
        if action not in ("approve", "reject"):
            return self._json({"error": "action must be approve|reject"}, 400)
        reason = str(data.get("reason", "")).strip()[:300]
        if action == "reject" and not reason:
            return self._json({"error": "a reason is required when rejecting"}, 400)
        job = next((j for j in stage.get("jobs", []) if j["id"] == appr["job_id"]), None)
        if prework:
            if not job or not self.verified_contractor_for_new_repair(
                    stage, job.get("assigned_to_party_id"), job.get("required_trade"), job.get("property_id")):
                return self._json({"error": "contractor is no longer approved for this repair"}, 409)
            current_mandate = self.repair_authority(stage, appr.get("property_id"))
            if not current_mandate or current_mandate != appr.get("mandate_snapshot"):
                return self._json({"error": "management authority changed; request a new approval"}, 409)
            if (not job or job.get("status") != "awaiting_prework_approval"
                    or job.get("approved_quote_pence") != appr.get("amount_pence")
                    or not any(
                        q.get("status") == "pending_landlord"
                        and q.get("pence") == appr.get("amount_pence")
                        and q.get("at") == appr.get("quote_at")
                        and q.get("version") == appr.get("quote_version")
                        and q.get("line_items", []) == appr.get("quote_lines", [])
                        for q in job.get("quotes", [])
                    )):
                return self._json({"error": "this quote approval is no longer valid"}, 409)
        if variation_approval:
            var = job.get("pending_variation") if job else None
            current_mandate = self.repair_authority(stage, appr.get("property_id"))
            if (not job or not var or var.get("status") != "pending_landlord"
                    or var.get("id") != appr.get("variation_id")
                    or var.get("scope") != appr.get("scope")
                    or var.get("line_items") != appr.get("line_items")
                    or var.get("base_authorised_pence") != appr.get("base_authorised_pence")
                    or job.get("approved_quote_pence") != appr.get("base_authorised_pence")
                    or job.get("approved_quote_pence", 0) + var.get("extra_pence", 0) != appr.get("amount_pence")
                    or job.get("status") not in ("assigned", "in_progress")
                    or not job.get("work_authorised_at")
                    or not current_mandate or current_mandate != appr.get("mandate_snapshot")):
                return self._json({"error": "variation or mandate changed; request new approval"}, 409)
            if not self.verified_contractor_for_new_repair(
                    stage, job.get("assigned_to_party_id"), job.get("required_trade"), job.get("property_id")):
                return self._json({"error": "contractor no longer approved for extra work"}, 409)
        appr["status"] = "approved" if action == "approve" else "rejected"
        appr["reason_given"] = reason if action == "reject" else None
        appr["decided_at"] = now()
        if job and prework:
            for quote in job.get("quotes", []):
                if quote.get("status") == "pending_landlord" and quote.get("at") == appr.get("quote_at"):
                    quote["status"] = "approved" if action == "approve" else "declined"
            if action == "approve":
                job["status"] = "assigned"
                job["work_authorised_at"] = now()
                job["work_authorised_by"] = user.get("username", "landlord")
                self.post_msg(stage, job["case_id"],
                              "The landlord approved the quoted cost BEFORE work. The contractor may now arrange a visit.",
                              to=("tenant", "landlord", "trades"))
            else:
                job["status"] = "quote_requested"
                job.pop("approved_quote_pence", None)
                self.post_msg(stage, job["case_id"],
                              "The landlord declined the quote. No work is authorised; the agent must arrange a new price.",
                              to=("tenant", "landlord", "trades"))
            self.sync_case(stage, job["case_id"], "dispatched")
        elif job and variation_approval:
            var = job["pending_variation"]
            if action == "approve":
                self.approve_job_variation(stage, job, var, user.get("username", "landlord"))
            else:
                var["status"] = "declined"
                var["decision_reason"] = reason
                var["decided_at"] = now()
                job.pop("pending_variation", None)
                self.audit(stage, {"actor": user.get("username", "landlord"),
                                   "action": "variation_declined", "target": job["id"], "note": reason})
                self.post_msg(stage, job["case_id"],
                              "Landlord declined the additional work; only the original authorised scope remains.",
                              to=("tenant", "landlord", "trades"))
        elif job:
            self.post_msg(stage, job["case_id"],
                          ("The landlord approved the invoice — " if action == "approve"
                           else "The landlord declined the invoice — ")
                          + f"£{appr['amount_pence']/100:.2f}"
                          + (f". Reason: {reason}" if reason else ".")
                          + " No payment is recorded by this decision.",
                          to=("tenant", "trades", "landlord"))
            if action == "approve":
                job["status"] = "invoice_approved"
                job["invoice_approved_at"] = now()
                job["invoice_approved_by"] = user.get("username", "landlord")
            else:
                job["status"] = "rejected"
                # Invoice rejection does not cancel the repair or confirm it failed.
                stage.setdefault("cases", []).append({
                    "id": stage.get("next_case_id", 490),
                    "type": "agent_task",
                    "property_id": appr.get("property_id"),
                    "role": "agent",
                    "name": "System",
                    "message": f"Landlord declined {job['id']} (£{appr['amount_pence']/100:.2f}): {reason}. Decide next step.",
                    "status": "new", "submitted_at": now(),
                })
                stage["next_case_id"] = stage.get("next_case_id", 490) + 1
        self.audit(stage, {
            "actor": user.get("display_name", "Landlord"),
            "action": ("prework_quote_" if prework else "variation_" if variation_approval else "invoice_") + appr["status"],
            "target": appr["id"], "note": reason or None
        })
        if job:
            self.update_case_from_job(stage, job)
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
            if job.get("property_id") not in property_ids:
                continue
            # Each independently recorded external payment belongs to its own period.
            # Supplier credits reduce invoices but are NOT cash paid and do not appear here.
            payments = job.get("payments")
            if not isinstance(payments, list):
                legacy_date = str(job.get("paid_at") or "")[:10]
                payments = ([{"date": legacy_date,
                              "amount_pence": int(job.get("payment_amount_pence")
                                                  or job.get("invoice_pence") or 0),
                              "reference": job.get("payment_reference") or "legacy-unverified"}]
                            if job.get("status") == "paid" and legacy_date else [])
            for payment in payments:
                paid_date = str(payment.get("date") or "")[:10]
                try:
                    paid_amount = int(payment.get("amount_pence") or 0)
                except (TypeError, ValueError):
                    continue
                if paid_amount <= 0 or not start_iso <= paid_date <= end_iso:
                    continue
                covered = any(a.get("landlord_party_id") == landlord_id
                              and job.get("property_id") in a.get("property_ids", [])
                              and a.get("status") in ("active", "ended")
                              and (not a.get("created_at") or str(a.get("created_at"))[:10] <= paid_date)
                              and (not a.get("ended_at") or a.get("ended_at") >= paid_date)
                              for a in stage.get("management_agreements", []))
                if covered:
                    maintenance_lines.append({
                        "job_id": job.get("id"), "property_id": job.get("property_id"),
                        "paid_date": paid_date, "amount_pence": paid_amount,
                        "external_reference": str(payment.get("reference") or "")[:120],
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
        agent_actions = {
            "close", "reopen", "add_tradesperson", "mark_read",
            "mark_unread", "note", "follow_up", "reply", "inform",
            "dispatch_repair", "set_next_action",
        }
        tenant_actions = {
            "reply", "inform", "confirm_resolution", "reopen_unresolved",
        }
        allowed = {
            "agent": agent_actions,
            "tenant": tenant_actions,
            "landlord": {"reply", "inform"},
            "trades": {"reply", "inform"},
        }
        role = u.get("role")
        known_actions = set().union(*allowed.values())

        if action not in known_actions:
            return self._json({"error": "unknown case action"}, 400)
        if action not in allowed.get(role, set()):
            return self._json({"error": "action not permitted"}, 403)

        if role in ("tenant", "landlord"):
            ids = self.account_party_ids(stage, u, role)
            prop = self.find_prop(stage, c.get("property_id"))
            if not prop or not self.has_party_link(prop, role, ids):
                return self._json({"error": "not your property"}, 403)
            if role == "tenant" and not self.has_party_link(
                    c, "tenant", ids):
                return self._json({"error": "not your case"}, 403)

        if role == "trades":
            ids = self.account_party_ids(stage, u, "trades")
            assigned = any(
                j.get("assigned_to_party_id") in ids
                and str(j.get("case_id")) == str(c.get("id"))
                for j in stage.get("jobs", [])
            )
            participating = self.has_party_link(c, "trades", ids)
            if not (assigned or participating):
                return self._json({"error": "not your case"}, 403)
        if action in ("reply", "inform"):
            to = data.get("to") or (
                ["agent"] if role == "tenant" else ["tenant"]
            )
            audiences = {"agent", "tenant", "landlord", "trades"}
            if (not isinstance(to, list) or not to
                    or any(not isinstance(x, str) or x not in audiences
                           for x in to)):
                return self._json({"error": "invalid audience"}, 400)
            if not str(data.get("text", "")).strip():
                return self._json({"error": "nothing to say"}, 400)
            self.post_msg(stage, c["id"], data.get("text"), to=to)
            self.audit(stage, {"actor": u.get("display_name", "?"), "action": f"case_{action}",
                               "target": c["id"], "note": "-> " + ",".join(to)})
        elif action == "set_next_action":
            if c.get("status") in ("closed", "declined"):
                return self._json({"error": "reopen the case before planning further action"}, 409)
            actor = data.get("next_actor")
            instruction = str(data.get("next_action") or "").strip()[:200]
            due_date = data.get("next_due_at")
            if actor not in ("agent", "tenant", "landlord", "trades") or not instruction:
                return self._json({"error": "one next actor and a clear next action are required"}, 400)
            if not isinstance(due_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due_date):
                return self._json({"error": "next due date must be YYYY-MM-DD"}, 400)
            try:
                parsed_due = datetime.strptime(due_date, "%Y-%m-%d").date()
            except ValueError:
                return self._json({"error": "invalid next due date"}, 400)
            if parsed_due < datetime.now(timezone.utc).date():
                return self._json({"error": "next due date cannot be in the past"}, 400)
            if actor in ("tenant", "landlord"):
                prop = self.find_prop(stage, c.get("property_id"))
                linked = set()
                if prop:
                    one = prop.get(actor + "_party_id")
                    many = prop.get(actor + "_party_ids")
                    if isinstance(one, str):
                        linked.add(one)
                    if isinstance(many, list):
                        linked.update(x for x in many if isinstance(x, str))
                if not any(p.get("id") in linked
                           and p.get("status") == "active"
                           and p.get("account_id")
                           and actor in p.get("roles", [])
                           for p in stage.get("parties", []) if isinstance(p, dict)):
                    return self._json({"error": "no linked " + actor + " available for this case"}, 409)
            if actor == "trades" and not any(
                    str(j.get("case_id")) == str(c.get("id"))
                    and j.get("assigned_to_party_id")
                    for j in stage.get("jobs", [])):
                return self._json({"error": "no assigned contractor for this case"}, 409)
            self.case_next(c, actor, instruction, due_date, u.get("username", "agent"))
            self.audit(stage, {"actor": u.get("display_name", "Agent"),
                               "action": "case_next_action_set", "target": c["id"],
                               "note": f"{actor} by {due_date}: {instruction}"})
        elif action == "dispatch_repair":
            if c.get("type") != "issue" or c.get("status") not in ("reported", "new"):
                return self._json({"error": "only an untriaged tenant issue can become a repair job"}, 409)
            prop = self.find_prop(stage, c.get("property_id"))
            if not prop:
                return self._json({"error": "case property is missing"}, 409)
            if any(str(j.get("case_id")) == str(c["id"]) for j in stage.get("jobs", [])):
                return self._json({"error": "this report already has a repair job"}, 409)
            triage = c.get("triage") if isinstance(c.get("triage"), dict) else {}
            reason = str(data.get("triage_note", "")).strip()[:500]
            if not reason:
                return self._json({"error": "record why the agent is dispatching this repair"}, 400)
            trade = str(data.get("required_trade") or triage.get("trade") or "").strip().lower()
            if not re.fullmatch(r"[a-z][a-z_]{0,39}", trade):
                return self._json({"error": "select a valid repair trade"}, 400)
            if trade == "other":
                trade = ""
            stage.setdefault("jobs", [])
            job_ids = [int(j["id"].split("-")[1])
                       for j in stage["jobs"]
                       if isinstance(j.get("id"), str) and re.fullmatch(r"job-\d+", j["id"])]
            jid = "job-" + str(max(job_ids, default=0) + 1)
            job = {
                "id": jid, "case_id": c["id"], "property_id": c["property_id"],
                "message": c.get("message", ""), "triage": triage,
                "required_trade": trade or None, "status": "triaged",
                "requires_prework_quote": True,
                "assigned_to": None, "invoice_pence": None,
                "created_at": now(), "triaged_at": now(),
                "triaged_by": u.get("username", "agent"), "triage_note": reason,
            }
            if c.get("document_ids"):
                job["evidence_document_ids"] = list(c["document_ids"])
            stage["jobs"].append(job)
            c["status"] = "dispatched"
            c["triaged_at"] = now()
            c["triaged_by"] = u.get("username", "agent")
            c["triage_note"] = reason
            self.case_next(c, "agent", "Request a vetted contractor quote for the repair",
                           self.internal_case_target(), u.get("username", "agent"))
            self.post_msg(stage, c["id"], "Your report has been reviewed by the agent; a repair job has been opened.", to=("tenant",))
            self.audit(stage, {"actor": u.get("display_name", "agent"), "action": "repair_dispatched",
                               "target": jid, "note": "Case #" + str(c["id"]) + ": " + reason})
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
            self.case_next(c, None, None, None, u.get("username", "agent"))
            c["closed_reason"] = reason
            c["actioned_at"] = now()
            self.post_msg(stage, c["id"], f"Case closed: {reason}", to=("tenant", "trades", "landlord"))
            self.audit(stage, {"actor": "agent", "action": "case_closed", "target": c["id"], "note": reason})
        elif action == "reopen":
            c["status"] = "new"
            self.case_next(c, "agent", "Review the reopened case",
                           self.internal_case_target(), u.get("username", "agent"))
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
            self.case_next(c, None, None, None, u.get("username", "tenant"))
            c["tenant_confirmed_at"] = now()
            self.post_msg(stage, c["id"], "Tenant confirmed the repair is resolved.", to=("agent", "landlord", "trades"))
            self.audit(stage, {"actor": u.get("display_name", "tenant"), "action": "tenant_confirmed_resolution",
                               "target": c["id"]})
        elif action == "reopen_unresolved":
            if (c.get("type") != "issue"
                    or c.get("status") not in ("resolved", "awaiting_confirmation", "closed")):
                return self._json({"error": "only a completed or closed repair may be disputed here"}, 409)
            reason = str(data.get("text", "")).strip()[:1000]
            if not reason:
                return self._json({"error": "explain what is still unresolved"}, 400)
            c["status"] = "reported"
            c["reopened_at"] = now()
            self.case_next(c, "agent", "Review tenant's unresolved repair and arrange follow-up",
                           self.internal_case_target(), u.get("username", "tenant"))
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
        """Authorise document reads using verified Party IDs."""
        if not isinstance(doc, dict):
            return False

        role = (u or {}).get("role")
        if role == "agent":
            return True

        if role not in ("tenant", "landlord", "trades"):
            return False

        allowed = doc.get("access_roles")
        if not isinstance(allowed, list) or role not in allowed:
            return False

        stage = load_stage()
        ids = self.account_party_ids(stage, u, role)
        if not ids:
            return False

        party_id = doc.get("party_id")
        if party_id and party_id not in ids:
            return False

        def related(collection, record_id):
            if record_id is None or record_id == "":
                return None
            return next(
                (
                    r for r in stage.get(collection, [])
                    if str(r.get("id")) == str(record_id)
                ),
                None,
            )

        case = related("cases", doc.get("case_id"))
        job = related("jobs", doc.get("job_id"))
        tenancy = related("tenancies", doc.get("tenancy_id"))

        for field, record in (
            ("case_id", case),
            ("job_id", job),
            ("tenancy_id", tenancy),
        ):
            if doc.get(field) and record is None:
                return False

        property_ids = [
            str(value)
            for value in (
                doc.get("property_id"),
                (case or {}).get("property_id"),
                (job or {}).get("property_id"),
                (tenancy or {}).get("property_id"),
            )
            if value is not None and value != ""
        ]

        # Contradictory document relationships fail closed.
        if len(set(property_ids)) > 1:
            return False

        if case and job and job.get("case_id") is not None:
            if str(job["case_id"]) != str(case["id"]):
                return False

        if not property_ids:
            # Only a document directly linked to this Party,
            # with no unresolved resource references, can
            # be accessed without a property relationship.
            return bool(
                party_id and party_id in ids
                and not any(
                    doc.get(field)
                    for field in ("case_id", "job_id", "tenancy_id")
                )
            )

        prop = self.find_prop(stage, property_ids[0])
        if not prop:
            return False

        if role == "tenant":
            if not self.has_party_link(prop, "tenant", ids):
                return False
            if case and not self.has_party_link(
                case, "tenant", ids
            ):
                return False
            if tenancy and not self.has_party_link(
                tenancy, "tenant", ids
            ):
                return False
            return True

        if role == "landlord":
            if not self.has_party_link(prop, "landlord", ids):
                return False
            if tenancy and not self.has_party_link(
                tenancy, "landlord", ids
            ):
                return False
            return True

        # A tradesperson requires an actual Party-linked job.
        # A public job listing never grants document access.
        owned_jobs = [
            j for j in stage.get("jobs", [])
            if j.get("assigned_to_party_id") in ids
            and str(j.get("property_id")) == str(prop["id"])
            and j.get("status") != "open"
        ]

        if job:
            return any(
                str(j.get("id")) == str(job["id"])
                for j in owned_jobs
            )

        if case:
            return any(
                str(j.get("case_id")) == str(case["id"])
                for j in owned_jobs
            )

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
        c = next((c for c in stage.get("cases", []) if str(c.get("id")) == str(case_id)), None)
        property_id = data.get("property_id")
        if not property_id and c:
            property_id = c.get("property_id")
        tenancy_id = str(data.get("tenancy_id", ""))[:100] or None
        tenancy = None
        if tenancy_id:
            tenancy = next((t for t in stage.get("tenancies", []) if t.get("id") == tenancy_id), None)
            if not tenancy:
                return self._json({"error": "tenancy not found"}, 404)
            property_id = property_id or tenancy.get("property_id")
        job_id = str(data.get("job_id", ""))[:100] or None
        job = None
        if job_id:
            job = next((j for j in stage.get("jobs", []) if j.get("id") == job_id), None)
            if not job:
                return self._json({"error": "job not found"}, 404)
            property_id = property_id or job.get("property_id")
        party_id = str(data.get("party_id", ""))[:100] or None
        if party_id and not any(p.get("id") == party_id for p in stage.get("parties", [])):
            return self._json({"error": "party not found"}, 404)
        prop = self.find_prop(stage, property_id)
        if not prop and not party_id:
            return self._json({"error": "property not found (pass property_id, tenancy_id, job_id, party_id or a valid case_id)"}, 404)
        dtype = str(data.get("document_type", "other"))[:40]
        if dtype not in self.DOCUMENT_TYPES:
            return self._json({"error": f"document_type must be one of {', '.join(self.DOCUMENT_TYPES)}"}, 400)
        access_roles = data.get("access_roles", ["agent"])
        allowed_roles = {"agent", "tenant", "landlord", "trades"}
        if isinstance(access_roles, str):
            access_roles = [x.strip() for x in access_roles.split(",") if x.strip()]
        if not isinstance(access_roles, list) or any(r not in allowed_roles for r in access_roles):
            return self._json({"error": "access_roles must contain supported portal roles"}, 400)
        access_roles = sorted(set(access_roles) | {"agent"})
        expiry_date = str(data.get("expiry_date", "")).strip()[:30] or None
        if expiry_date:
            try:
                datetime.strptime(expiry_date, "%Y-%m-%d")
            except ValueError:
                return self._json({"error": "expiry_date must be YYYY-MM-DD"}, 400)
        supersedes_id = str(data.get("supersedes_id", "")).strip()[:100] or None
        superseded = None
        if supersedes_id:
            superseded = next((d for d in stage.get("documents", []) if d.get("id") == supersedes_id), None)
            if not superseded:
                return self._json({"error": "superseded document not found"}, 404)
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
            "property_id": prop["id"] if prop else None,
            "party_id": party_id,
            "tenancy_id": tenancy_id,
            "job_id": job_id,
            "document_type": dtype,
            "title": str(data.get("title", ""))[:120],
            "description": str(data.get("description", ""))[:500],
            "file_name": fname,
            "content_type": str(data.get("content_type", "application/octet-stream"))[:80],
            "file_size": len(raw),
            "storage_key": storage_key,
            "expiry_date": expiry_date,
            "access_roles": access_roles,
            "version": int((superseded or {}).get("version", 0)) + 1 if superseded else 1,
            "supersedes_id": supersedes_id,
            "replaced_by_id": None,
            "uploaded_by": (self.user or {}).get("display_name", "Agent"),
            "uploaded_at": now(),
            "verified_by": None,
            "verified_at": None,
            "status": "pending",
            "notes": "",
        }
        if superseded:
            superseded["status"] = "superseded"
            superseded["replaced_by_id"] = doc_id
            superseded["superseded_at"] = now()
        flist.append(doc)
        if c:
            c.setdefault("document_ids", []).append(doc_id)
        if tenancy:
            tenancy.setdefault("document_ids", []).append(doc_id)
        if job:
            job.setdefault("document_ids", []).append(doc_id)
        self.audit(stage, {"actor": (self.user or {}).get("display_name", "?"),
                           "action": "document_uploaded", "target": doc_id,
                           "note": f"{dtype} / {fname} / {len(raw)}B"})
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

    # ---------- tasks ----------
    def handle_task_action(self, data):
        stage = load_stage()
        action = data.get("action") or "create"
        tasks = stage.setdefault("tasks", [])
        actor = (self.user or {}).get("display_name", "Agent")
        if action == "create":
            title = str(data.get("title", ""))[:160].strip()
            if not title:
                return self._json({"error": "title is required"}, 400)
            nums = [int(t["id"].split("-")[1]) for t in tasks if re.fullmatch(r"task-\d+", t.get("id", ""))]
            task = {
                "id": f"task-{(max(nums) + 1) if nums else 1}",
                "title": title,
                "description": str(data.get("description", ""))[:1000],
                "owner": str(data.get("owner") or actor)[:120],
                "priority": data.get("priority") if data.get("priority") in ("low", "normal", "high", "urgent") else "normal",
                "status": "open",
                "due_date": str(data.get("due_date", ""))[:40] or None,
                "reminder_at": str(data.get("reminder_at", ""))[:40] or None,
                "recurrence": data.get("recurrence") if data.get("recurrence") in ("none", "daily", "weekly", "monthly", "yearly") else "none",
                "property_id": data.get("property_id") or None,
                "party_id": data.get("party_id") or None,
                "tenancy_id": data.get("tenancy_id") or None,
                "case_id": data.get("case_id") or None,
                "job_id": data.get("job_id") or None,
                "created_by": actor,
                "created_at": now(),
                "updated_at": now(),
            }
            tasks.append(task)
            self.audit(stage, {"actor": actor, "action": "task_created", "target": task["id"], "note": task["title"]})
            save_stage(stage)
            return self._json({"success": True, "task": task})
        task = next((t for t in tasks if t.get("id") == data.get("id")), None)
        if not task:
            return self._json({"error": "task not found"}, 404)
        if action == "update":
            for field in ("title", "description", "owner", "due_date", "reminder_at", "property_id", "party_id", "tenancy_id", "case_id", "job_id"):
                if field in data:
                    task[field] = str(data.get(field, ""))[:1000] or None
            if data.get("priority") in ("low", "normal", "high", "urgent"):
                task["priority"] = data["priority"]
            if data.get("recurrence") in ("none", "daily", "weekly", "monthly", "yearly"):
                task["recurrence"] = data["recurrence"]
        elif action in ("complete", "reopen", "cancel"):
            task["status"] = {"complete": "completed", "reopen": "open", "cancel": "cancelled"}[action]
            if action == "complete":
                task["completed_at"] = now()
        else:
            return self._json({"error": "unsupported task action"}, 400)
        task["updated_at"] = now()
        self.audit(stage, {"actor": actor, "action": f"task_{action}", "target": task["id"], "note": task.get("title", "")})
        save_stage(stage)
        return self._json({"success": True, "task": task})

    # ---------- office policy and real contacts ----------
    @staticmethod
    def safe_office_settings(stage, user):
        record = stage.get("office_settings")
        if not isinstance(record, dict):
            return {"configured": False, "published": False,
                    "notice": "Office contact and out-of-hours arrangements not yet published. Refer to your signed tenancy paperwork."}
        visible = {k: record.get(k) for k in (
            "office_name", "phone", "email", "opening_hours", "out_of_hours_phone",
            "out_of_hours_instructions", "emergency_policy", "published_at",
        )}
        visible["configured"] = bool(record.get("phone") and record.get("email"))
        visible["published"] = bool(record.get("published"))
        if (user or {}).get("role") != "agent" and not visible["published"]:
            return {"configured": False, "published": False,
                    "notice": "Office contacts have not been confirmed. Please use the details in your tenancy paperwork."}
        if (user or {}).get("role") == "agent":
            visible["reviewed_by"] = record.get("reviewed_by")
            visible["reviewed_at"] = record.get("reviewed_at")
            visible["version"] = record.get("version", 0)
        return visible

    def handle_office_settings(self, data):
        if (self.user or {}).get("role") != "agent":
            return self._json({"error": "office settings require an agent"}, 403)
        if data.get("action") not in ("save_draft", "publish", "unpublish"):
            return self._json({"error": "action must be save_draft|publish|unpublish"}, 400)
        stage = load_stage()
        old = stage.get("office_settings")
        if not isinstance(old, dict):
            old = {}
        actor = (self.user or {}).get("username", "agent")
        if data["action"] == "unpublish":
            if not old.get("published"):
                return self._json({"error": "office policy is not published"}, 409)
            new = {**old, "published": False, "unpublished_at": now(),
                   "updated_at": now(), "version": old.get("version", 0)+1}
        else:
            fields = {
                "office_name": (3, 160), "phone": (7, 35), "email": (5, 254),
                "opening_hours": (5, 400), "out_of_hours_phone": (0, 35),
                "out_of_hours_instructions": (15, 800), "emergency_policy": (30, 1200),
            }
            new = {}
            for key, (minimum, maximum) in fields.items():
                val = data.get(key)
                if not isinstance(val, str) or not minimum <= len(val.strip()) <= maximum:
                    return self._json({"error": key+" has missing or invalid text"}, 400)
                new[key] = val.strip()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", new["email"]):
                return self._json({"error": "valid office email required"}, 400)
            if not re.fullmatch(r"\+?[0-9()\s-]{7,35}", new["phone"]):
                return self._json({"error": "valid office phone required"}, 400)
            if new["out_of_hours_phone"] and not re.fullmatch(
                    r"\+?[0-9()\s-]{7,35}", new["out_of_hours_phone"]):
                return self._json({"error": "invalid out-of-hours number"}, 400)
            if data["action"] == "publish":
                if data.get("checked_real_contacts") is not True or data.get("policy_reviewed") is not True:
                    return self._json({"error": "confirm real contacts and review emergency policy before publishing"}, 409)
                if not new["out_of_hours_phone"] and len(new["out_of_hours_instructions"]) < 25:
                    return self._json({"error": "clear out-of-hours instructions required"}, 409)
            new.update({"published": data["action"] == "publish",
                        "published_at": now() if data["action"] == "publish" else old.get("published_at"),
                        "reviewed_by": actor if data["action"] == "publish" else old.get("reviewed_by"),
                        "reviewed_at": now() if data["action"] == "publish" else old.get("reviewed_at"),
                        "updated_at": now(), "version": old.get("version", 0)+1})
        stage["office_settings"] = new
        self.audit(stage, {"actor": actor, "action": "office_policy_"+data["action"],
                           "target": "office_settings", "note": "version "+str(new["version"])})
        save_stage(stage)
        return self._json({"success": True, "office": self.safe_office_settings(stage, self.user)})

    # ---------- notifications ----------
    NOTIFICATION_TYPES = (
        "agent_alert", "landlord_approval_request", "tenant_appointment",
        "trades_job", "compliance_reminder", "rent_arrears_reminder",
        "reminder_email", "general",
    )

    def scoped_notifications(self, u):
        """Notifications are addressed to verified Party IDs."""
        stage = load_stage()
        notes = stage.get("notifications", [])
        role = (u or {}).get("role")

        if role == "agent":
            return notes

        if role not in ("tenant", "landlord", "trades"):
            return []

        ids = self.account_party_ids(stage, u, role)
        if not ids:
            return []

        return [
            n for n in notes
            if isinstance(n, dict)
            and n.get("recipient_role") == role
            and isinstance(n.get("recipient_party_id"), str)
            and n["recipient_party_id"] in ids
        ]

    def handle_notification_action(self, data):
        stage = load_stage()
        action = data.get("action") or "create"
        notes = stage.setdefault("notifications", [])
        actor = (self.user or {}).get("display_name", "Agent")
        if action == "create":
            if (self.user or {}).get("role") != "agent":
                return self._json({"error": "only agents can create notifications"}, 403)
            ntype = data.get("notification_type") if data.get("notification_type") in self.NOTIFICATION_TYPES else "general"
            title = str(data.get("title", ""))[:160].strip()
            message = str(data.get("message", ""))[:1200].strip()
            role = data.get("recipient_role") if data.get("recipient_role") in ("agent", "tenant", "landlord", "trades") else "agent"
            recipient_party_id = data.get("recipient_party_id")

            if role != "agent":
                if (not isinstance(recipient_party_id, str)
                        or not recipient_party_id.strip()):
                    return self._json({
                        "error": "recipient Party ID required"
                    }, 400)

                party = next(
                    (
                        p for p in stage.get("parties", [])
                        if p.get("id") == recipient_party_id
                    ),
                    None,
                )

                if (
                    not party
                    or party.get("status") != "active"
                    or role not in (party.get("roles") or [])
                ):
                    return self._json({
                        "error": "invalid recipient Party"
                    }, 400)
            elif recipient_party_id:
                return self._json({
                    "error": "agent notifications use agent role"
                }, 400)

            if not title or not message:
                return self._json({"error": "title and message are required"}, 400)
            nums = [int(n["id"].split("-")[1]) for n in notes if re.fullmatch(r"note-\d+", n.get("id", ""))]
            channels = data.get("channels") if isinstance(data.get("channels"), list) else ["in_app"]
            channels = [c for c in channels if c in ("in_app", "email")]
            if not channels:
                channels = ["in_app"]
            note = {
                "id": f"note-{(max(nums) + 1) if nums else 1}",
                "notification_type": ntype,
                "title": title,
                "message": message,
                "recipient_role": role,
                "recipient_name": str(data.get("recipient_name", ""))[:120] or None,
                "recipient_party_id": recipient_party_id if role != "agent" else None,
                "channels": channels,
                "email_to": str(data.get("email_to", ""))[:254] or None,
                "email_status": "queued" if "email" in channels else None,
                "status": "unread",
                "property_id": data.get("property_id") or None,
                "case_id": data.get("case_id") or None,
                "job_id": data.get("job_id") or None,
                "task_id": data.get("task_id") or None,
                "due_at": str(data.get("due_at", ""))[:40] or None,
                "created_by": actor,
                "created_at": now(),
                "read_at": None,
            }
            notes.append(note)
            self.audit(stage, {"actor": actor, "action": "notification_created", "target": note["id"], "note": title})
            save_stage(stage)
            return self._json({"success": True, "notification": note})
        note = next((n for n in notes if n.get("id") == data.get("id")), None)
        if not note:
            return self._json({"error": "notification not found"}, 404)
        if (self.user or {}).get("role") != "agent" and note not in self.scoped_notifications(self.user):
            return self._json({"error": "not your notification"}, 403)
        if action == "read":
            note["status"] = "read"
            note["read_at"] = now()
        elif action == "unread":
            note["status"] = "unread"
            note["read_at"] = None
        elif action == "sent":
            if (self.user or {}).get("role") != "agent":
                return self._json({"error": "only agents can mark email sent"}, 403)
            note["email_status"] = "sent"
            note["email_sent_at"] = now()
        else:
            return self._json({"error": "unsupported notification action"}, 400)
        self.audit(stage, {"actor": actor, "action": f"notification_{action}", "target": note["id"], "note": note.get("title", "")})
        save_stage(stage)
        return self._json({"success": True, "notification": note})

    # ---------- appointments ----------
    @staticmethod
    def appointment_datetime(value):
        """Require a real timezone-aware ISO datetime; never compare date strings."""
        if not isinstance(value, str) or not value or len(value) > 40:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        return parsed if parsed.tzinfo and parsed.utcoffset() is not None else None

    def appointment_eligible_parties(self, stage, prop, job=None):
        """Only real, active account-linked people on this property/job may attend."""
        by_role = {"tenant": set(), "landlord": set(), "trades": set()}
        for role in ("tenant", "landlord"):
            linked = prop.get(role + "_party_ids") or []
            linked = [linked] if isinstance(linked, str) else linked
            single = prop.get(role + "_party_id")
            if isinstance(single, str):
                linked = list(linked) + [single]
            by_role[role].update(pid for pid in linked if isinstance(pid, str))
        if job and isinstance(job.get("assigned_to_party_id"), str):
            by_role["trades"].add(job["assigned_to_party_id"])
        active = {}
        for party in stage.get("parties", []):
            if not isinstance(party, dict) or party.get("status") != "active" or not party.get("account_id"):
                continue
            for role, eligible in by_role.items():
                if party.get("id") in eligible and role in party.get("roles", []):
                    active.setdefault(role, set()).add(party["id"])
        return active

    def can_access_appointment(self, stage, user, appt):
        """A participant must have both an account-linked Party and the resource link."""
        role = user.get("role")
        if role == "agent":
            return True
        if role not in ("tenant", "landlord", "trades"):
            return False
        ids = self.account_party_ids(stage, user, role)
        if not ids or role not in (appt.get("participant_roles") or []):
            return False
        if not ids.intersection(set(appt.get("participant_party_ids") or [])):
            return False
        prop = self.find_prop(stage, appt.get("property_id"))
        if not prop:
            return False
        if role in ("tenant", "landlord"):
            return self.has_party_link(prop, role, ids)
        job = next((j for j in stage.get("jobs", [])
                    if j.get("id") == appt.get("job_id")), None)
        return bool(job and job.get("property_id") == prop.get("id")
                    and job.get("assigned_to_party_id") in ids)

    def appointment_for_role(self, appt, user):
        """Hide tenant access preferences until consent and visit confirmation."""
        result = dict(appt)
        role = user.get("role")
        if role == "landlord":
            result.pop("access_preference", None)
            result.pop("contact_consent", None)
        elif role == "trades" and (appt.get("status") != "confirmed"
                                  or not appt.get("contact_consent")):
            result.pop("access_preference", None)
            result.pop("contact_consent", None)
        return result

    def scoped_appointments(self, u):
        stage = load_stage()
        return [self.appointment_for_role(a, u)
                for a in stage.get("appointments", [])
                if self.can_access_appointment(stage, u, a)]

    def handle_appointment(self, data):
        """Agent can arrange linked diary items; authorised trade may propose a job visit."""
        stage = load_stage()
        u = self.user or {}
        role = u.get("role")
        if role not in ("agent", "trades"):
            return self._json({"error": "appointment creation is for the agent or assigned trade"}, 403)
        prop = self.find_prop(stage, data.get("property_id"))
        if not prop:
            return self._json({"error": "property not found"}, 404)
        job_id = data.get("job_id") or None
        case_id = data.get("case_id") or None
        job = next((j for j in stage.get("jobs", [])
                    if str(j.get("id")) == str(job_id)), None) if job_id else None
        case = next((c for c in stage.get("cases", [])
                     if str(c.get("id")) == str(case_id)), None) if case_id else None
        if job_id and not job:
            return self._json({"error": "job not found"}, 404)
        if case_id and not case:
            return self._json({"error": "case not found"}, 404)
        if job and job.get("property_id") != prop["id"]:
            return self._json({"error": "job belongs to another property"}, 409)
        if case and case.get("property_id") != prop["id"]:
            return self._json({"error": "case belongs to another property"}, 409)
        if job and case and str(job.get("case_id")) != str(case.get("id")):
            return self._json({"error": "case does not match job"}, 409)
        if job and not case_id:
            case_id = job.get("case_id")
            case = next((c for c in stage.get("cases", []) if str(c.get("id")) == str(case_id)), None)
        if case:
            case_id = case.get("id")
        if job:
            job_id = job.get("id")
        start = str(data.get("start_time") or "")
        end = str(data.get("end_time") or "")
        start_dt = self.appointment_datetime(start)
        end_dt = self.appointment_datetime(end) if end else None
        if not start_dt or (end and not end_dt) or (end_dt and end_dt <= start_dt):
            return self._json({"error": "valid timezone-aware start and later end required"}, 400)
        if start_dt.astimezone(timezone.utc) <= datetime.now(timezone.utc):
            return self._json({"error": "appointment must be in the future"}, 400)
        appt_type = data.get("appointment_type") or data.get("type") or "viewing"
        if appt_type not in self.APPOINTMENT_TYPES:
            return self._json({"error": "unsupported appointment_type"}, 400)
        if role == "trades" or appt_type == "contractor_visit":
            if not job or job.get("status") not in ("assigned", "in_progress"):
                return self._json({"error": "an assigned, authorised job is needed before offering a visit"}, 409)
            if job.get("requires_prework_quote") and not job.get("work_authorised_at"):
                return self._json({"error": "quote must be approved before proposing access"}, 409)
        if role == "trades":
            if appt_type != "contractor_visit":
                return self._json({"error": "trades can only propose contractor visits"}, 403)
            ids = self.account_party_ids(stage, u, "trades")
            if job.get("assigned_to_party_id") not in ids:
                return self._json({"error": "not your assigned job"}, 403)
        if appt_type == "contractor_visit":
            roles = ["agent", "tenant", "trades"]
        else:
            supplied = data.get("participant_roles")
            if not isinstance(supplied, list):
                invitee = data.get("invitee_role")
                supplied = [invitee] if invitee in ("tenant", "landlord", "trades") else ["tenant"]
            roles = sorted({"agent", *(r for r in supplied if r in ("tenant", "landlord", "trades"))})
        eligible = self.appointment_eligible_parties(stage, prop, job)
        selected = data.get("participant_party_ids")
        allowed_ids = set().union(*(eligible.get(r, set()) for r in roles if r != "agent"))
        if isinstance(selected, list) and selected:
            if any(not isinstance(pid, str) or pid not in allowed_ids for pid in selected):
                return self._json({"error": "appointment participant not linked to this property/job"}, 403)
            selected_ids = sorted(set(selected))
        else:
            selected_ids = sorted(allowed_ids)
        if appt_type == "contractor_visit":
            if not eligible["tenant"].intersection(selected_ids) or not eligible["trades"].intersection(selected_ids):
                return self._json({"error": "a linked tenant and assigned trade are required"}, 409)
        appts = stage.setdefault("appointments", [])
        if appt_type == "contractor_visit":
            if not case:
                return self._json({"error": "the assigned job must link to a real repair case"}, 409)
            if any(a.get("job_id") == job_id
                   and a.get("status") in ("proposed", "confirmed", "change_requested",
                                           "no_access", "parts_delay")
                   for a in appts):
                return self._json({"error": "an open visit already exists for this job; reschedule it"}, 409)
        nums = [int(a["id"].split("-")[1]) for a in appts
                if isinstance(a.get("id"), str) and re.fullmatch(r"appt-\d+", a["id"])]
        appt = {
            "id": f"appt-{max(nums, default=0) + 1}", "property_id": prop["id"],
            "case_id": case_id, "job_id": job_id, "appointment_type": appt_type,
            "title": str(data.get("title") or appt_type.replace("_", " ").title())[:120],
            "description": str(data.get("description") or "")[:1000],
            "start_time": start_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "end_time": end_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if end_dt else None,
            "location": str(data.get("location") or "At the property")[:200],
            "status": "proposed", "participant_roles": roles, "participant_party_ids": selected_ids,
            "invitee_role": "tenant" if "tenant" in roles else next((r for r in roles if r != "agent"), "agent"),
            "reminder_at": str(data.get("reminder_at") or "")[:40] or None,
            "reminder_minutes_before": 0,
            "created_by": u.get("display_name", "Agent"), "created_at": now(), "updated_at": now(),
            "notes": "", "outcome": None, "access_preference": None,
            "contact_consent": False, "history": [],
        }
        appts.append(appt)
        if case:
            case.setdefault("appointment_ids", [])
            if appt["id"] not in case["appointment_ids"]:
                case["appointment_ids"].append(appt["id"])
        if job:
            job.setdefault("appointment_ids", [])
            if appt["id"] not in job["appointment_ids"]:
                job["appointment_ids"].append(appt["id"])
        appt["history"].append({"at": now(), "role": role, "action": "proposed"})
        self.audit(stage, {"actor": u.get("display_name", "?"),
                           "action": "appointment_created", "target": appt["id"]})
        if case_id is not None:
            self.post_msg(stage, case_id,
                          "A visit has been proposed. The resident must confirm access before arrival.",
                          to=("tenant", "trades"))
        save_stage(stage)
        return self._json({"success": True, "appointment": self.appointment_for_role(appt, u)})

    def handle_appointment_action(self, data):
        """Server-controlled visit state machine; only the resident can consent to access."""
        stage = load_stage()
        appt = next((a for a in stage.get("appointments", [])
                     if a.get("id") == data.get("id")), None)
        if not appt:
            return self._json({"error": "appointment not found"}, 404)
        u = self.user or {}
        role = u.get("role")
        if not self.can_access_appointment(stage, u, appt):
            return self._json({"error": "not your appointment"}, 403)
        action = data.get("action")
        allowed = {
            "agent": {"confirm", "decline", "reschedule", "complete", "miss", "no_access", "parts_delay", "cancel"},
            "tenant": {"confirm", "decline"},
            "landlord": {"confirm", "decline"},
            "trades": {"reschedule", "complete", "miss", "no_access", "parts_delay"},
        }
        if action not in allowed.get(role, set()):
            return self._json({"error": "that appointment action is not permitted for your role"}, 403)
        contractor = appt.get("appointment_type") == "contractor_visit"
        if contractor and action in ("confirm", "decline") and role != "tenant":
            return self._json({"error": "only the linked tenant can agree contractor access"}, 403)
        current = appt.get("status")
        if contractor and action in ("confirm", "reschedule"):
            job = next((j for j in stage.get("jobs", [])
                        if j.get("id") == appt.get("job_id")), None)
            if (not job or job.get("property_id") != appt.get("property_id")
                    or job.get("status") not in ("assigned", "in_progress")
                    or (job.get("requires_prework_quote") and not job.get("work_authorised_at"))):
                return self._json({"error": "the repair is no longer authorised for a visit"}, 409)
        if action == "confirm" and current != "proposed":
            return self._json({"error": "only a proposed appointment can be confirmed"}, 409)
        if action == "decline" and current not in (
                ("proposed", "confirmed") if contractor else ("proposed",)):
            return self._json({"error": "this appointment cannot be changed by the invitee"}, 409)
        if action in ("complete", "miss", "no_access", "parts_delay") and current != "confirmed":
            return self._json({"error": "an unconfirmed visit cannot have an attendance outcome"}, 409)
        if action == "reschedule" and current not in (
                "proposed", "confirmed", "change_requested", "declined", "missed", "no_access", "parts_delay"):
            return self._json({"error": "appointment cannot be rescheduled in this state"}, 409)
        if action == "cancel" and current in ("completed", "cancelled"):
            return self._json({"error": "appointment already closed"}, 409)
        note = str(data.get("note") or "").strip()[:500]
        if action in ("miss", "no_access", "parts_delay") and not note:
            return self._json({"error": "record a reason for missed access or parts delay"}, 400)
        if action == "reschedule":
            start = str(data.get("start_time") or "")
            end = str(data.get("end_time") or "")
            start_dt = self.appointment_datetime(start)
            end_dt = self.appointment_datetime(end) if end else None
            if not start_dt or (end and not end_dt) or (end_dt and end_dt <= start_dt):
                return self._json({"error": "valid timezone-aware start and later end required"}, 400)
            if start_dt.astimezone(timezone.utc) <= datetime.now(timezone.utc):
                return self._json({"error": "new visit must be in the future"}, 400)
            appt["previous_start_time"] = appt.get("start_time")
            appt["previous_end_time"] = appt.get("end_time")
            appt["start_time"] = start_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            appt["end_time"] = end_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if end_dt else None
            appt["access_preference"] = None
            appt["contact_consent"] = False
        if action == "decline" and role == "tenant" and contractor:
            appt["access_preference"] = None
            appt["contact_consent"] = False
        if action == "confirm" and role == "tenant" and contractor:
            appt["access_preference"] = str(data.get("access_preference") or "").strip()[:160] or None
            # Consent is optional; a confirmed visit is not permission to disclose contact details.
            appt["contact_consent"] = data.get("contact_consent") is True
        status_map = {
            "confirm": "confirmed", "decline": "change_requested" if contractor else "declined", "reschedule": "proposed",
            "complete": "completed", "miss": "missed", "no_access": "no_access",
            "parts_delay": "parts_delay", "cancel": "cancelled",
        }
        appt["status"] = status_map[action]
        appt["updated_at"] = now()
        if note:
            appt["notes"] = note
        if action == "complete":
            appt["outcome"] = str(data.get("outcome") or "Visit completed; repair still requires separate confirmation")[:500]
        appt.setdefault("history", []).append({"at": now(), "role": role, "action": action,
                                                "note": note})
        self.audit(stage, {"actor": u.get("display_name", "?"),
                           "action": f"appointment_{action}", "target": appt["id"]})
        if appt.get("case_id") is not None:
            messages = {
                "confirm": "The resident confirmed the proposed visit.",
                "decline": "The visit time does not suit the resident. A new proposal is needed.",
                "reschedule": "A new visit time has been proposed and needs resident confirmation.",
                "no_access": "The contractor reported no access. The office must arrange a new visit.",
                "miss": "The visit was missed. The office must follow up.",
                "parts_delay": "The contractor reported a parts delay. The case remains open.",
                "complete": "Visit attendance completed; this does not confirm that the repair is fixed.",
                "cancel": "The office cancelled the appointment.",
            }
            self.post_msg(stage, appt["case_id"], messages[action],
                          to=("tenant", "trades", "landlord"))
        save_stage(stage)
        return self._json({"success": True, "appointment": self.appointment_for_role(appt, u)})

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
