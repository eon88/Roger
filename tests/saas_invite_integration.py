#!/usr/bin/env python3
"""Real two-agency HTTP/PostgreSQL acceptance: one-use tenant/staff access."""
import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

A, B = [Path(value) for value in sys.argv[1:3]]


def manifest(path):
    return json.loads((path / "agency.json").read_text())


def api(base, path, body=None, cookie=None, origin=None):
    headers = {}
    if origin:
        headers["Origin"] = "https://" + origin
    if cookie:
        headers["Cookie"] = cookie
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(base + path,
                  data=json.dumps(body).encode() if body is not None else None,
                  headers=headers, method="POST" if body is not None else "GET")
    try:
        with urlopen(req, timeout=20) as response:
            content = response.read()
            return response.status, json.loads(content), response.headers.get("Set-Cookie", "")
    except HTTPError as err:
        content = err.read()
        return err.code, json.loads(content), ""


def get_page(base, path):
    with urlopen(base + path, timeout=20) as response:
        return response.status, response.read().decode()


def main():
    a = manifest(A)
    b = manifest(B)
    aa = "http://127.0.0.1:" + str(a["port"])
    bb = "http://127.0.0.1:" + str(b["port"])
    admin_secret = "new-unique-agency-password-" + a["agency_id"]
    code, login, cookie_header = api(aa, "/login", {
        "username": "agency-admin", "password": admin_secret
    }, origin=a["hostname"])
    assert code == 200 and login["role"] == "agent", (code, login)
    admin_cookie = cookie_header.split(";", 1)[0]

    code, minted, _ = api(aa, "/api/invitation", {
        "property_id": "ci-invite-home-1",
        "party_id": "ci-invite-tenant-1",
        "role": "tenant",
        "email": "newtenant@example.test",
    }, cookie=admin_cookie, origin=a["hostname"])
    assert code == 200 and minted.get("success"), (code, minted)
    token = minted["invite_url"].split("#token=", 1)[1]
    assert "/invite#token=" in minted["invite_url"]
    assert "@" not in minted["invite_url"]

    status, page = get_page(aa, "/invite")
    assert status == 200 and "Create portal login" in page
    status, js = get_page(aa, "/invite.js")
    assert status == 200 and "/api/invite/accept" in js
    print("PASS: actual invitation landing page and script are reachable")

    code, visible, _ = api(aa, "/api/invite/validate", {"token": token}, origin=a["hostname"])
    assert code == 200 and visible.get("valid") is True, (code, visible)
    code, foreign, _ = api(bb, "/api/invite/validate", {"token": token}, origin=b["hostname"])
    assert code == 200 and foreign.get("valid") is False, (code, foreign)
    print("PASS: B cannot validate A's invitation token")

    code, rejected, _ = api(aa, "/api/invite/accept", {
        "token": token, "username": "ciinvited", "password": "short"
    }, origin=a["hostname"])
    assert code == 400, (code, rejected)

    password = "unique-invite-ci-passphrase-2026"
    code, created, _ = api(aa, "/api/invite/accept", {
        "token": token, "username": "ciinvited", "password": password
    }, origin=a["hostname"])
    assert code == 200 and created.get("success"), (code, created)
    code, reused, _ = api(aa, "/api/invite/accept", {
        "token": token, "username": "ciinvitedagain", "password": password
    }, origin=a["hostname"])
    assert code == 400, (code, reused)
    print("PASS: invitation can be used once, then expires for account creation")

    code, logged, cookie_header = api(aa, "/login", {
        "username": "ciinvited", "password": password
    }, origin=a["hostname"])
    assert code == 200 and logged.get("role") == "tenant", (code, logged)
    tenant_cookie = cookie_header.split(";", 1)[0]

    code, stage, _ = api(aa, "/api/stage", cookie=tenant_cookie)
    assert code == 200 and stage["role"] == "tenant", (code, stage)
    assert [prop["id"] for prop in stage["properties"]] == ["ci-invite-home-1"], stage
    assert "parties" not in stage and "invitations" not in stage
    print("PASS: invited account sees only the pre-authorised Party property")

    code, foreign, _ = api(bb, "/api/stage", cookie=tenant_cookie)
    assert code == 401, (code, foreign)
    code, foreign_login, _ = api(bb, "/login", {
        "username": "ciinvited", "password": password
    }, origin=b["hostname"])
    assert code == 401, (code, foreign_login)
    code, forbidden, _ = api(aa, "/api/invitation", {
        "property_id": "ci-invite-home-1", "party_id": "ci-invite-tenant-1",
        "role": "tenant", "email": "newtenant@example.test"
    }, cookie=tenant_cookie, origin=a["hostname"])
    assert code == 403, (code, forbidden)
    print("PASS: tenant account cannot use B's records or issue more invitations")
    # B02: privileged agency staff enrolment is administrator-only.
    code, staff_invite, _ = api(aa, "/api/security/staff/invite", {
        "current_password": admin_secret,
        "email": "ci-staff@example.test", "display_name": "CI Agency Staff",
    }, cookie=admin_cookie, origin=a["hostname"])
    assert code == 200 and staff_invite.get("success"), (code, staff_invite)
    staff_token = staff_invite["invite_url"].split("#token=", 1)[1]
    code, bad_staff, _ = api(bb, "/api/invite/validate", {
        "token": staff_token,
    }, origin=b["hostname"])
    assert code == 200 and not bad_staff["valid"], (code, bad_staff)
    code, denied_staff, _ = api(bb, "/api/invite/accept", {
        "token": staff_token, "username": "cistaff",
        "password": "verified-staff-strong-passphrase",
    }, origin=b["hostname"])
    assert code == 400, (code, denied_staff)
    code, created_staff, _ = api(aa, "/api/invite/accept", {
        "token": staff_token, "username": "cistaff",
        "password": "verified-staff-strong-passphrase",
    }, origin=a["hostname"])
    assert code == 200 and created_staff.get("success"), (code, created_staff)
    code, duplicated_staff, _ = api(aa, "/api/invite/accept", {
        "token": staff_token, "username": "ciotherstaff",
        "password": "a-different-safe-staff-password",
    }, origin=a["hostname"])
    assert code == 400, (code, duplicated_staff)
    code, staff_login, staff_cookie_hdr = api(aa, "/login", {
        "username": "cistaff", "password": "verified-staff-strong-passphrase",
    }, origin=a["hostname"])
    assert code == 200 and staff_login["role"] == "agent", (code, staff_login)
    staff_cookie = staff_cookie_hdr.split(";", 1)[0]
    code, denied_privilege, _ = api(aa, "/api/security/staff/invite", {
        "current_password": "verified-staff-strong-passphrase",
        "email": "another@example.test", "display_name": "Unauthorised Staff",
    }, cookie=staff_cookie, origin=a["hostname"])
    assert code == 403, (code, denied_privilege)
    code, denied_foreign, _ = api(bb, "/api/stage", cookie=staff_cookie)
    assert code == 401, (code, denied_foreign)
    print("PASS: privileged staff invite, single-use redemption and cross-agency denial")

    # Password recovery links are one-use and preserve separate MFA factors.
    code, issued, _ = api(aa, "/api/security/staff/reset", {
        "current_password": admin_secret, "username": "cistaff",
        "reason": "Verified staff account recovery during isolated CI security test",
    }, cookie=admin_cookie, origin=a["hostname"])
    assert code == 200 and issued.get("success"), (code, issued)
    reset_token = issued["reset_url"].split("#token=", 1)[1]
    code, foreign_reset, _ = api(bb, "/api/security/staff/reset/accept", {
        "token": reset_token, "new_password": "brand-new-staff-password-2026",
    }, origin=b["hostname"])
    assert code == 400, (code, foreign_reset)
    code, reset, _ = api(aa, "/api/security/staff/reset/accept", {
        "token": reset_token, "new_password": "brand-new-staff-password-2026",
    }, origin=a["hostname"])
    assert code == 200 and reset.get("success"), (code, reset)
    code, replay_reset, _ = api(aa, "/api/security/staff/reset/accept", {
        "token": reset_token, "new_password": "another-new-staff-password",
    }, origin=a["hostname"])
    assert code == 400, (code, replay_reset)
    code, former, _ = api(aa, "/api/stage", cookie=staff_cookie)
    assert code == 401, (code, former)
    code, former_password, _ = api(aa, "/login", {
        "username": "cistaff", "password": "verified-staff-strong-passphrase",
    }, origin=a["hostname"])
    assert code == 401, (code, former_password)
    code, updated, staff_cookie_hdr = api(aa, "/login", {
        "username": "cistaff", "password": "brand-new-staff-password-2026",
    }, origin=a["hostname"])
    assert code == 200 and updated["role"] == "agent", (code, updated)
    staff_cookie = staff_cookie_hdr.split(";", 1)[0]
    print("PASS: staff reset one-use, invalidated sessions and new password")

    # A non-admin must never suspend another staff account.
    code, denied_suspend, _ = api(aa, "/api/security/staff/suspend", {
        "current_password": "brand-new-staff-password-2026",
        "username": "agency-admin", "reason": "Attempt to remove agency owner privileges",
    }, cookie=staff_cookie, origin=a["hostname"])
    assert code == 403, (code, denied_suspend)
    code, suspended, _ = api(aa, "/api/security/staff/suspend", {
        "current_password": admin_secret, "username": "cistaff",
        "reason": "Isolated CI account test complete; revoke staff access",
    }, cookie=admin_cookie, origin=a["hostname"])
    assert code == 200 and suspended["sessions_revoked"] >= 1, (code, suspended)
    code, dead_cookie, _ = api(aa, "/api/stage", cookie=staff_cookie)
    assert code == 401, (code, dead_cookie)
    code, dead_login, _ = api(aa, "/login", {
        "username": "cistaff", "password": "brand-new-staff-password-2026",
    }, origin=a["hostname"])
    assert code == 401, (code, dead_login)
    code, tenant_still_active, _ = api(aa, "/api/stage", cookie=tenant_cookie)
    assert code == 200 and tenant_still_active["role"] == "tenant", (code, tenant_still_active)
    print("PASS: admin suspension kills staff sessions without affecting tenant access")
    print("TWO-AGENCY INVITATION ACCEPTANCE PASSED")


if __name__ == "__main__":
    main()
