#!/usr/bin/env python3
"""E2E isolation: two independent local Roger SaaS stacks, no live services."""
import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

A, B = [Path(arg) for arg in sys.argv[1:3]]


def manifest(root):
    return json.loads((root / "agency.json").read_text())


def get_credentials(root):
    result = {}
    for line in (root / "initial-admin-credentials.txt").read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def request(base, path, body=None, cookie=None, hostname=None):
    method = "POST" if body is not None else "GET"
    headers = {}
    if hostname:
        headers["Origin"] = "https://" + hostname
    if body is not None:
        headers["Content-Type"] = "application/json"
    if cookie:
        headers["Cookie"] = cookie
    req = Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                  headers=headers, method=method)
    try:
        with urlopen(req, timeout=15) as response:
            data = json.loads(response.read())
            return response.status, data, response.headers.get("Set-Cookie", "")
    except HTTPError as exc:
        return exc.code, json.loads(exc.read()), ""


def agency_client(root):
    m = manifest(root)
    creds = get_credentials(root)
    base = "http://127.0.0.1:" + str(m["port"])
    status, who, _ = request(base, "/api/whoami")
    assert status == 200 and who.get("authenticated") is False, (status, who)
    code, payload, set_cookie = request(base, "/login", {
        "username": creds["USERNAME"], "password": creds["PASSWORD"]
    }, hostname=m["hostname"])
    assert code == 200 and payload.get("role") == "agent", (code, payload)
    # Cookies are Secure in production. This test passes their value directly
    # because only the GH runner's loopback HTTP diagnostic port is used.
    assert "Secure" in set_cookie
    cookie = set_cookie.split(";", 1)[0]
    status, stage, _ = request(base, "/api/stage", cookie=cookie)
    assert status == 200 and stage.get("agency_id") == m["agency_id"], (status, stage)
    assert not stage["properties"] and not stage["cases"] and not stage["registrations"]
    return m, base, cookie


def main():
    ma, base_a, cookie_a = agency_client(A)
    mb, base_b, cookie_b = agency_client(B)
    assert ma["agency_id"] != mb["agency_id"]
    assert ma["port"] != mb["port"]
    print("PASS: two agency admins can access only their own fresh stages")

    code, body, _ = request(base_b, "/api/stage", cookie=cookie_a)
    assert code == 401, (code, body)
    code, body, _ = request(base_a, "/api/stage", cookie=cookie_b)
    assert code == 401, (code, body)
    print("PASS: an agency session cookie is refused by the other agency")

    status, case_a, _ = request(base_a, "/api/prospect-intake", {
        "kind": "tenant", "name": "Oak Preview", "email": "oak@example.test",
        "area": "Leeds", "message": "Want to rent", "consent": True
    }, hostname=ma["hostname"])
    assert status == 200 and case_a.get("success"), (status, case_a)
    code, stage_a, _ = request(base_a, "/api/stage", cookie=cookie_a)
    assert code == 200 and len(stage_a["cases"]) == 1, (code, stage_a)
    assert stage_a["cases"][0]["agency_id"] == ma["agency_id"]
    assert stage_a["cases"][0]["name"] == "Oak Preview"
    code, stage_b, _ = request(base_b, "/api/stage", cookie=cookie_b)
    assert code == 200 and not stage_b["cases"], (code, stage_b)
    print("PASS: A's prospect writes only to A's PostgreSQL, never B")

    code, case_b, _ = request(base_b, "/api/prospect-intake", {
        "kind": "landlord", "name": "Birch Preview", "email": "birch@example.test",
        "area": "York", "message": "Need management", "consent": True
    }, hostname=mb["hostname"])
    assert code == 200 and case_b.get("success"), (code, case_b)
    _, fresh_a, _ = request(base_a, "/api/stage", cookie=cookie_a)
    _, fresh_b, _ = request(base_b, "/api/stage", cookie=cookie_b)
    assert len(fresh_a["cases"]) == 1 and not fresh_a["registrations"]
    assert not fresh_b["cases"] and len(fresh_b["registrations"]) == 1
    assert fresh_b["registrations"][0]["agency_id"] == mb["agency_id"]
    print("PASS: B's landlord prospect writes only to B; records carry agency ID")
    print("TWO ISOLATED AGENCIES ACCEPTANCE PASSED")


if __name__ == "__main__":
    main()
