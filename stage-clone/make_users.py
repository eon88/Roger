#!/usr/bin/env python3
"""Seed users.json for the Stage clone portal. Prints plaintext passwords ONCE.
users.json itself only ever stores scrypt hashes + sessions stay in it too."""
import hashlib, json, os, secrets, string

ROOT = os.path.dirname(os.path.abspath(__file__))
FP = os.path.join(ROOT, "users.json")

def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex()
    return salt, h

def rpw(n=12):
    abc = string.ascii_letters + string.digits
    return "".join(secrets.choice(abc) for _ in range(n))

users = [
    ("agent",    "agent",    "Stefan — the agency desk", None),
    ("dev",      "agent",    "AI developer (full access)", None),
    ("tenant",   "tenant",   "Daniel Mensah", None),
    ("landlord", "landlord", "T. Blackwood", None),
    ("trades",   "trades",   "R. Doyle Gas & Heat", None),
]
data = {"users": [], "sessions": {}}
printed = []
for username, role, display, pw in users:
    pw = pw or rpw()
    salt, h = hash_pw(pw)
    data["users"].append({"username": username, "role": role, "display_name": display,
                          "salt": salt, "hash": h, "created": __import__("datetime").datetime.utcnow().isoformat() + "Z"})
    printed.append((username, role, pw))

with open(FP, "w") as f:
    json.dump(data, f, indent=2)
os.chmod(FP, 0o600)
print(f"wrote {FP}\n")
print("USERNAME      ROLE       PASSWORD")
for u, r, p in printed:
    print(f"{u:<14}{r:<11}{p}")
