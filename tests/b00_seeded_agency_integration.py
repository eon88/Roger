#!/usr/bin/env python3
"""B00 real Docker/PostgreSQL seeded two-agency proof, CI runner only.

Run *after* the existing SaaS account/role/invitation tests, against fresh
disposable Oak/Birch stacks. Writes only synthetic records to those stacks.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))
from v1_two_agency_data import build, validate


IN_CONTAINER = r"""
import copy, json, sys, serve, canonical_records, legacy_reconciliation
incoming=json.load(sys.stdin)
agency_id=incoming.pop("agency_id")
assert legacy_reconciliation.reconciliation_report(incoming)["ready_for_canonical_linking"], (
    "synthetic B01 fixture has unresolved canonical links or invoice identities")
with serve.storage_write_lock():
    stage=serve.load_stage()
    assert stage["agency_id"] == agency_id
    for group, rows in incoming.items():
        assert isinstance(rows,list)
        current=stage.setdefault(group,[])
        old_ids={x.get("id") for x in current}
        assert all(x["id"] not in old_ids for x in rows), group+" duplicate IDs"
        assert all(x["agency_id"]==agency_id for x in rows)
        current.extend(rows)
    serve.save_stage(stage)
    first=serve.load_stage()
    stale=json.loads(json.dumps(first))
    first["b01_snapshot_guard"]="first_writer_wins"
    serve.save_stage(first)
    try:
        serve.save_stage(stale)
    except serve.StaleStageWrite:
        pass
    else:
        raise AssertionError("stale PostgreSQL writer silently overwrote a newer snapshot")
    again=serve.load_stage()
    assert again["b01_snapshot_guard"]=="first_writer_wins"
    assert again["_stage_revision"]>=2
    assert again["agency_id"]==agency_id
    assert len(again.get("deposit_records",[])) >= 1
    assert len(again.get("documents",[])) >= 1
    assert len(again.get("rent_ledger_entries",[])) >= 1
    original=json.loads(json.dumps(again))
    # The same real PostgreSQL stage writer must reject contradictory synthetic
    # document/tenancy links, not just report them in a standalone unit test.
    wrong_doc=copy.deepcopy(original)
    d=next(d for d in wrong_doc["documents"]
           if str(d.get("id","")).startswith("ci-"+agency_id))
    other_property=next(p["id"] for p in wrong_doc["properties"]
                        if p["id"] != d["property_id"] and
                        str(p["id"]).startswith("ci-"+agency_id))
    d["property_id"]=other_property
    d["model_version"]=1
    try:
        serve.save_stage(wrong_doc)
    except canonical_records.RecordIntegrityError:
        pass
    else:
        raise AssertionError("PostgreSQL accepted cross-property document/tenancy link")
    foreign_job=copy.deepcopy(original)
    j=next(j for j in foreign_job["jobs"]
           if str(j.get("id","")).startswith("ci-"+agency_id))
    j["model_version"]=1
    j["agency_id"]="foreign-agency"
    try:
        serve.save_stage(foreign_job)
    except (canonical_records.RecordIntegrityError, ValueError):
        pass
    else:
        raise AssertionError("PostgreSQL accepted foreign agency job identity")
    assert serve.load_stage()==original, "failed security writes mutated PostgreSQL"
print("PASS: synthetic fixture, relationship denial, agency boundary and stale PostgreSQL writer guard")
"""


def agency(root):
    return json.loads((root / "agency.json").read_text(encoding="utf-8"))


def compose_command(root):
    return [
        "docker", "compose", "-f", str(root / "compose.yaml"),
        "-f", str(ROOT / "ops" / "saas" / "staging-limits.yaml"),
        "--env-file", str(root / ".env"),
        "exec", "-T", "app", "python", "-c", IN_CONTAINER,
    ]


def request(base, path, payload=None, cookie=None, host=None):
    headers = {}
    if host:
        headers["Origin"] = "https://" + host
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if cookie:
        headers["Cookie"] = cookie
    req = Request(
        base + path,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers=headers, method="POST" if payload is not None else "GET")
    try:
        with urlopen(req, timeout=18) as response:
            return response.status, json.loads(response.read()), response.headers.get("Set-Cookie", "")
    except HTTPError as error:
        return error.code, json.loads(error.read()), ""


def login(info):
    base="http://127.0.0.1:"+str(info["port"])
    username=info.get("admin_username")
    if not username:
        # Read the per-agency synthetic initial-credentials manifest for the username only.
        # Never log or reuse the initial one-time password after rotation.
        username=info.get("slug","agency-admin")
    password="new-unique-agency-password-"+info["agency_id"]
    code, body, cookie = request(
        base, "/login", {"username": username, "password": password},
        host=info["hostname"])
    assert code==200 and body.get("role")=="agent" and cookie, (code, body)
    return base, cookie.split(";",1)[0]


def main(a, b):
    fixtures = {}
    clients = {}
    for root in (a, b):
        info=agency(root)
        fixture=build(info["agency_id"])
        validate(fixture)
        proc=subprocess.run(compose_command(root), input=json.dumps(fixture),
                            capture_output=True, text=True, timeout=60, check=False)
        if proc.returncode:
            raise AssertionError("Fixture seeding failed for "+info["agency_id"]+
                                 ": "+proc.stderr[-1200:])
        assert "PASS: synthetic fixture, relationship denial" in proc.stdout, proc.stdout
        base,cookie=login(info)
        status,stage,_=request(base,"/api/stage",cookie=cookie)
        assert status==200, (status,stage)
        for group,rows in fixture.items():
            if group=="agency_id":
                continue
            ids={x["id"] for x in stage.get(group,[])}
            assert {x["id"] for x in rows}<=ids, group+" did not persist"
        clients[info["agency_id"]]=(base,cookie)
        fixtures[info["agency_id"]]=fixture
        print("PASS:",info["agency_id"],"has independently stored people, homes, tenancies, repair, invoice, deposit and document metadata")
    ids=list(clients)
    assert len(ids)==2 and ids[0]!=ids[1]
    for source,target in ((ids[0],ids[1]),(ids[1],ids[0])):
        base, _=clients[target]
        _, foreign_cookie=clients[source]
        status,body,_=request(base,"/api/stage",cookie=foreign_cookie)
        assert status==401, ("cross-agency cookie accepted",source,target,status)
        _,own_cookie=clients[target]
        status,stage,_=request(base,"/api/stage",cookie=own_cookie)
        assert status==200 and stage.get("agency_id")==target
        other_ids={r["id"] for group in fixtures[source].values()
                   if isinstance(group,list) for r in group}
        seen_ids={r.get("id") for group in stage.values()
                  if isinstance(group,list) for r in group if isinstance(r,dict)}
        assert not (other_ids & seen_ids), "Foreign synthetic record visible in "+target
    print("PASS: seeded multi-record, two-agency PostgreSQL separation and stolen-cookie denial")


if __name__=="__main__":
    if len(sys.argv)!=3:
        raise SystemExit("Usage: b00_seeded_agency_integration.py OAK_ROOT BIRCH_ROOT")
    main(Path(sys.argv[1]),Path(sys.argv[2]))
