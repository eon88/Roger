#!/usr/bin/env python3
"""Local dev server for the Stage clone. Maps clean URLs to saved files.

v2 (post-audit): status-sync between cases/jobs/approvals, credential gating
on trades jobs, structured registrations, evidence on approvals, validation.
"""
from http.server import SimpleHTTPRequestHandler, HTTPServer
import hashlib
import hmac
import http.cookies
import json
import os
import re
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone

import jev_client

ROOT = os.path.dirname(os.path.abspath(__file__))
STAGE_FILE = os.path.join(ROOT, "stage.json")
USERS_FILE = os.path.join(ROOT, "users.json")
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

def load_users():
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(data):
    with open(USERS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(USERS_FILE, 0o600)

def load_stage():
    with open(STAGE_FILE, "r") as f:
        return json.load(f)

def save_stage(data):
    with open(STAGE_FILE, "w") as f:
        json.dump(data, f, indent=2)

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
                "/api/landlord-action": {"landlord", "agent"}, "/api/registration-action": {"agent"},
                "/api/case-action": {"agent", "tenant", "landlord", "trades"}}

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
        if path == "/api/whoami":
            u = self.session_user()
            return self._json({"authenticated": False} if not u else
                              {"username": u["username"], "role": u["role"], "display_name": u["display_name"]})
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
                c["thread"] = [t for t in (c.get("thread") or []) if "tenant" in (t.get("to") or []) or t.get("role") == "tenant"]
            d = {"properties": myprops, "cases": mycases, "jobs": myjobs,
                 "authority": d.get("authority"), "role": "tenant"}
        elif u["role"] == "landlord":
            myprops = [p for p in props if p.get("landlord") == me]
            pids = {p["id"] for p in myprops}
            mycases = [c for c in d.get("cases", []) if c.get("property_id") in pids]
            for c in mycases:
                c["thread"] = [t for t in (c.get("thread") or []) if "landlord" in (t.get("to") or [])]
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
                if c["id"] in mycase_ids and (c.get("thread") or me in (c.get("participants") or [])):
                    threads[c["id"]] = [t for t in c.get("thread", []) if "trades" in (t.get("to") or [])]
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
            "/api/tenant/issue": self.handle_tenant_issue,
            "/api/job-action": self.handle_job_action,
            "/api/landlord-action": self.handle_landlord_action,
            "/api/registration-action": self.handle_registration_action,
            "/api/case-action": self.handle_case_action,
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

    def approved_trades(self, stage):
        """Companies an agent may put on a case: seeded profiles + approved registrations."""
        out = []
        for name, prof in TRADE_PROFILES.items():
            out.append({"company": name, "trades": prof["trades"], "gas_safe": bool(prof.get("gas_safe"))})
        for r in stage.get("registrations", []):
            if r.get("role") == "trades" and r.get("status") == "approved":
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
        t = self.triage(message)
        case = {
            "id": stage.get("next_case_id", 490),
            "type": "issue",
            "property_id": prop["id"] if prop else None,
            "role": "tenant",
            "name": str(data.get("name", "Tenant"))[:100],
            "email": str(data.get("email", ""))[:254],
            "message": message,
            "status": "reported",
            "triage": t,
            "submitted_at": now(),
        }
        stage["next_case_id"] = case["id"] + 1
        stage.setdefault("cases", []).append(case)
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
            stage["jobs"].append(job)
            case["status"] = "dispatched"
        self.audit(stage, {"actor": "system", "action": "case_created", "target": case["id"],
                           "note": f"{t['category']}/{t.get('trade','-')} urgency {t['urgency']}"})
        save_stage(stage)
        self._json({"success": True, "case_id": case["id"], "triage": t, "job_id": job["id"] if job else None})

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
        actor = (self.user or {}).get("display_name") or str(data.get("tradesperson", "Unknown"))[:100]

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
        elif action == "release" and job["status"] == "in_progress":
            job["status"] = "open"
            job["assigned_to"] = None
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
    def handle_case_action(self, data):
        stage = load_stage()
        c = next((c for c in stage.get("cases", []) if c["id"] == data.get("id")), None)
        if not c:
            return self._json({"error": "case not found"}, 404)
        action = data.get("action")
        u = getattr(self, "user", None) or {}
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
        else:
            return self._json({"error": f"unknown action {action}"}, 400)
        save_stage(stage)
        self._json({"success": True})


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
    HTTPServer(("127.0.0.1", 8901), H).serve_forever()
