#!/usr/bin/env python3
"""Upload and verify one harmless test document in disposable Oak ONLY.

Requires the already completed two-agency login isolation test.
Never touches live Roger, Birch, DNS or production files.
"""
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path("/root/roger-staging/stg-oak")
EXPECTED_AGENCY = "stg-oak"
EXPECTED_PORT = 29101
PROPERTY = "ci-invite-home-1"
TITLE = "Oak synthetic file backup test"
FILENAME = "oak-synthetic-restore-check.txt"
BODY = b"Roger staging document recovery test. Fictional content only.\n"


def require_healthy(name):
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Health.Status}}", name],
        text=True, capture_output=True, check=True, timeout=10)
    if result.stdout.strip() != "healthy":
        raise RuntimeError(name + " is not healthy")


def request(base, path, *, payload=None, cookie=None, origin=None, raw=False):
    headers = {}
    if origin:
        headers["Origin"] = "https://" + origin
    if cookie:
        headers["Cookie"] = cookie
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = Request(base + path, data=json.dumps(payload).encode() if payload is not None else None,
                  headers=headers, method="POST" if payload is not None else "GET")
    try:
        with urlopen(req, timeout=15) as response:
            data = response.read()
            return response.status, data if raw else json.loads(data), response.headers.get("Set-Cookie", "")
    except HTTPError as exc:
        raise RuntimeError("Oak API request " + path.split("?")[0] + " returned HTTP " + str(exc.code)) from None


def main():
    meta = json.loads((ROOT / "agency.json").read_text())
    if meta.get("agency_id") != EXPECTED_AGENCY or meta.get("port") != EXPECTED_PORT:
        raise RuntimeError("agency identity or localhost port mismatch")
    for name in ("roger", "roger-postgres", "roger-stg-oak-app-1",
                 "roger-stg-oak-postgres-1", "roger-stg-birch-app-1",
                 "roger-stg-birch-postgres-1"):
        require_healthy(name)
    base = "http://127.0.0.1:" + str(EXPECTED_PORT)
    _, login, set_cookie = request(base, "/login", payload={
        "username": "agency-admin",
        "password": "new-unique-agency-password-stg-oak",
    }, origin=meta["hostname"])
    if login.get("role") != "agent" or login.get("password_change_required"):
        raise RuntimeError("Oak staging admin credentials not in expected test state")
    cookie = set_cookie.split(";", 1)[0]
    if not cookie:
        raise RuntimeError("no session cookie returned")
    _, stage, _ = request(base, "/api/stage", cookie=cookie)
    if stage.get("agency_id") != EXPECTED_AGENCY:
        raise RuntimeError("Oak database agency mismatch")
    if not any(p.get("id") == PROPERTY for p in stage.get("properties", [])):
        raise RuntimeError("expected synthetic Oak property is missing")

    key = hashlib.sha256(BODY).hexdigest()
    previous = [d for d in stage.get("documents", [])
                if d.get("title") == TITLE]
    if previous:
        if len(previous) != 1 or previous[0].get("storage_key") != key:
            raise RuntimeError("existing test document differs; refusing overwrite")
        doc_id = previous[0]["id"]
        print("PASS: existing synthetic Oak document recognised; no duplicate created")
    else:
        _, created, _ = request(base, "/api/document", payload={
            "property_id": PROPERTY,
            "document_type": "property_document",
            "title": TITLE,
            "file_name": FILENAME,
            "content_type": "text/plain",
            "access_roles": ["agent"],
            "content_b64": base64.b64encode(BODY).decode(),
        }, cookie=cookie, origin=meta["hostname"])
        if created.get("success") is not True:
            raise RuntimeError("Oak synthetic document upload failed")
        document = created.get("document", {})
        if document.get("storage_key") != key or not re.fullmatch(r"doc-[0-9]+", document.get("id", "")):
            raise RuntimeError("returned document metadata invalid")
        doc_id = document["id"]
        print("PASS: fictional document uploaded through Oak's real document API")
    status, downloaded, _ = request(base, "/api/document/" + doc_id + "/file",
                                    cookie=cookie, raw=True)
    if status != 200 or downloaded != BODY or hashlib.sha256(downloaded).hexdigest() != key:
        raise RuntimeError("uploaded document bytes did not match download")
    print("PASS: downloaded document bytes verified against SHA-256")
    print("PASS: only synthetic Oak staging data changed; next step is file backup and restore")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        # Do not print credentials, headers or data.
        print("STOP: Oak synthetic file test:", str(exc)[:170], file=sys.stderr)
        sys.exit(1)
