#!/usr/bin/env python3
"""jev_client.py — standalone Jev (TypeSafe System One) client for the portal.

Same HTTP contract as /opt/data/mcp-servers/jev_sidecar.py, without the MCP
wrapper, so the plain-stdlib dev server can call it directly.

triage(message) -> dict with category/urgency/safety/confidence/engine.
Falls back to a keyword stub if the API is unreachable (engine='stub').
"""
import json
import os
import re
import urllib.error
import urllib.request

API_URL = "https://openrouter.ai/api/v1/systemone"
MODEL = "typesafe/jev-1.13"
TIMEOUT_S = 15
ENV_FILE = os.environ.get("HERMES_ENV_FILE", "/opt/data/.env")

def _load_env():
    try:
        with open(ENV_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except OSError:
        pass

def _key():
    _load_env()
    for var in ("OPENROUTER_API_KEY", "TYPESAFE_API_KEY"):
        v = os.environ.get(var, "").strip()
        if v and not (v.startswith("${") and v.endswith("}")):
            return v
    raise RuntimeError("no API key in environment or " + ENV_FILE)

def call_jev(state, questions):
    body = json.dumps({"state": state, "model": MODEL, "questions": questions}).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, method="POST",
                                 headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))

# One batched judgment per report: category (choice) + urgency (score) + safety risk (noul).
TRIAGE_QUESTIONS = {
    "category": {
        "type": "choice",
        "instructions": "Classify this property-rental message into one lane.",
        "criteria": {
            "maintenance": "Something in the building is broken, leaking, cold, blocked or unsafe and needs a trade.",
            "viewing": "Someone wants to see or move into a property.",
            "finance": "Rent, deposit, invoices, money owed or refunds.",
            "other": "Anything else — questions, admin, compliments.",
        },
    },
    "urgency": {
        "type": "score",
        "instructions": "Rate how fast this needs action in a tenanted property.",
        "criteria": ["routine", "soon", "emergency"],
    },
    "safety": {
        "type": "noul",
        "instructions": "Is there a plausible risk to a person's health or safety if this is not acted on quickly? (gas, fire, electric, water ingress, heat in winter, vulnerable occupants, security of the home)",
    },
    "trade": {
        "type": "choice",
        "instructions": "Which trade or skill is needed to fix or handle this? For non-maintenance messages pick closest.",
        "criteria": {
            "gas": "Boiler, gas fire, gas supply, flue — Gas Safe work.",
            "plumbing": "Taps, leaks, drains, toilets, water pipes, radiators.",
            "electric": "Sockets, lights, wiring, consumer unit.",
            "locksmith": "Locks, keys, entry problems.",
            "damp": "Mould, damp, condensation, roof leaks.",
            "general": "Minor repairs any handy person can do.",
            "other": "No trade needed — admin, viewings, money.",
        },
    },
}

def _stub(message):
    msg = message.lower()
    has = lambda ws: any(re.search(r"\b" + w + r"\b", msg) for w in ws)
    if has(["gas", "boiler", "flue"]): trade = "gas"
    elif has(["lock", "key", "locked"]): trade = "locksmith"
    elif has(["electric", "socket", "wiring"]): trade = "electric"
    elif has(["mould", "damp", "condensation"]): trade = "damp"
    elif has(["repair","fix","broken","leak","drip","tap","radiator","drain","toilet","sink"]): trade = "plumbing"
    else: trade = "other"
    return {
        "category": "maintenance" if trade != "other" else "other",
        "trade": trade,
        "urgency": 2 if has(["emergency","urgent","danger","boiler","heating","newborn","baby","flood","no hot water"]) else 1,
        "safety": 0.9 if has(["danger","safety","gas","fire","electrical","newborn","baby","child","flood","leak"]) else 0.3,
        "confidence": 50,
        "engine": "stub",
    }

def triage(message):
    """Ask Jev. On any API failure fall back to the keyword stub so the portal never blocks."""
    try:
        r = call_jev(message, TRIAGE_QUESTIONS)
        a = r.get("answers", {})
        cat = (a.get("category") or {}).get("choice", "other")
        trade = (a.get("trade") or {}).get("choice", "other")
        urg = (a.get("urgency") or {}).get("score")
        saf = (a.get("safety") or {}).get("noul")
        conf = (a.get("category") or {}).get("confidence")
        if cat is None or urg is None:
            raise RuntimeError("unexpected answer shape: " + json.dumps(a)[:200])
        cost = (r.get("usage") or {}).get("cost")
        return {
            "category": cat,
            "trade": trade,
            "urgency": max(0, min(2, int(round(urg)))),     # int 0..2 (score index)
            "urgency_raw": round(float(urg), 2),
            "safety": round(float(saf), 2) if saf is not None else 0.3,
            "confidence": int(round((conf or 0) * 100)) if conf is not None and conf <= 1 else int(round((conf or 0) if conf is not None else 0)),
            "engine": "jev",
            "cost_usd": round(float(cost), 5) if cost else None,
        }
    except Exception as e:
        out = _stub(message)
        out["fallback_reason"] = str(e)[:160]
        return out
