#!/usr/bin/env python3
"""Offline lettings-only agency CSV migration planner.

No HTTP endpoint, no portal-account creation and no tenant-facing publication.
Dry-run by default. Every write requires explicit offline confirmation and
backs up the original snapshot before atomic replace.

INPUT: people.csv, properties.csv, tenancies.csv. See README.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

# Reuse canonical periodic tenancy rules without importing the HTTP server.
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"stage-clone"))
from tenancy_2026 import assured_periodic_terms


class MigrationError(ValueError):
    pass


def value(row, key, limit=200, required=False):
    item = row.get(key, "")
    if not isinstance(item, str):
        raise MigrationError(key + " must be text")
    item = item.strip()
    if len(item) > limit or (required and not item):
        raise MigrationError(key + " is missing or too long")
    return item


def csv_rows(text, kind, required, limit=10000):
    if not isinstance(text, str) or len(text) > 4000000:
        raise MigrationError(kind + " CSV is too large")
    try:
        reader=csv.DictReader(io.StringIO(text, newline=""), strict=True)
        columns=reader.fieldnames or []
        if not set(required).issubset(columns):
            raise MigrationError(kind + " must include " + ", ".join(required))
        if len(columns) != len(set(columns)) or None in columns or len(columns)>30:
            raise MigrationError(kind + " has duplicate or invalid headers")
        rows=[]
        for idx,row in enumerate(reader,2):
            if idx>limit+1:
                raise MigrationError(kind + " has too many rows")
            if None in row or any(v is None for v in row.values()):
                raise MigrationError(kind + " row " + str(idx) + " has extra/missing columns")
            rows.append(row)
        return rows
    except (csv.Error, UnicodeError) as exc:
        raise MigrationError(kind + " malformed CSV: " + str(exc)) from None


def stable_id(prefix, agency_id, external_id):
    digest=hashlib.sha256((agency_id+"\0"+prefix+"\0"+external_id).encode()).hexdigest()[:20]
    return "import-"+prefix+"-"+digest


def validate_uniques(rows, category):
    seen=set()
    for row in rows:
        external=value(row, "external_id", 100, True)
        if external in seen:
            raise MigrationError(category + " duplicate external_id: " + external[:60])
        seen.add(external)


def positive_money(row, key, allow_zero=True):
    text=value(row,key,15,not allow_zero)
    if not text and allow_zero:
        return 0
    if not text.isdigit() or len(text)>12:
        raise MigrationError(key+" must be a nonnegative integer in pence")
    result=int(text)
    if (not allow_zero and result<=0) or result>1000000000:
        raise MigrationError(key+" is outside allowed limits")
    return result


def plan(stage, people_csv, properties_csv, tenancies_csv):
    """Return a new deep-copied snapshot and a complete plan. No disk writes."""
    if not isinstance(stage,dict):
        raise MigrationError("Existing stage must be JSON object")
    agency=str(stage.get("agency_id") or "standalone")[:100]
    people=csv_rows(people_csv,"people",("external_id","display_name","role"))
    properties=csv_rows(properties_csv,"properties",("external_id","title","area","landlord_external_id"))
    tenancies=csv_rows(tenancies_csv,"tenancies",(
        "external_id","property_external_id","tenant_external_id",
        "landlord_external_id","start_date","rent_amount_pence","rent_frequency"
    ))
    for category, rows in [("people",people),("properties",properties),("tenancies",tenancies)]:
        validate_uniques(rows,category)
    state=json.loads(json.dumps(stage))
    state.setdefault("parties",[])
    state.setdefault("properties",[])
    state.setdefault("tenancies",[])
    existing={name:{r.get("id") for r in state[name]} for name in ("parties","properties","tenancies")}
    actor="offline_agency_csv_import"
    timestamp=datetime.now(timezone.utc).isoformat()
    batch=hashlib.sha256((
        people_csv+"\n"+properties_csv+"\n"+tenancies_csv).encode()).hexdigest()[:20]
    mapped={}
    summary={"batch":batch,"agency_id":agency,"created":{"people":0,"properties":0,"tenancies":0},
             "already_present":{"people":0,"properties":0,"tenancies":0},
             "warnings":["Import does not grant portal access or publish listings.",
                         "Imported tenancies require agreement, deposit, rent and identity verification."]}
    for row in people:
        ext=value(row,"external_id",100,True)
        role=value(row,"role",30,True)
        if role not in ("landlord","tenant","guarantor","trades"):
            raise MigrationError("Unsupported role in people.csv: " + role)
        rid=stable_id("party",agency,ext)
        mapped[ext]=(rid,role)
        if rid in existing["parties"]:
            prior=next(p for p in state["parties"] if p.get("id")==rid)
            if prior.get("import_external_id")!=ext or role not in prior.get("roles",[]):
                raise MigrationError("Existing Party conflicts with import: " + ext)
            summary["already_present"]["people"]+=1
            continue
        person={
            "id":rid,"kind":"person",
            "display_name":value(row,"display_name",160,True),
            "email":value(row,"email",254),
            "phone":value(row,"phone",40),
            "roles":[role],"status":"active",
            "account_id":None,"agency_id":agency,
            "created_at":timestamp,"import_external_id":ext,
            "import_batch":batch,"source":actor,
            "verification_status":"needs_agent_review",
        }
        state["parties"].append(person)
        existing["parties"].add(rid)
        summary["created"]["people"]+=1
    prop_map={}
    for row in properties:
        ext=value(row,"external_id",100,True)
        owner_ext=value(row,"landlord_external_id",100,True)
        if owner_ext not in mapped or mapped[owner_ext][1]!="landlord":
            raise MigrationError("Property references an unknown landlord: "+owner_ext)
        pid=stable_id("property",agency,ext)
        prop_map[ext]=pid
        if pid in existing["properties"]:
            prior=next(p for p in state["properties"] if p.get("id")==pid)
            if prior.get("import_external_id")!=ext:
                raise MigrationError("Existing property conflicts with import")
            summary["already_present"]["properties"]+=1
            continue
        # Never publish a migrated listing without agent and compliance review.
        property_record={
            "id":pid,"title":value(row,"title",160,True),
            "address":value(row,"address",200),
            "postcode":value(row,"postcode",20),
            "area":value(row,"area",120,True),
            "landlord_party_id":mapped[owner_ext][0],
            "lifecycle_status":"onboarding",
            "agency_id":agency,"source":actor,
            "import_external_id":ext,"import_batch":batch,"created_at":timestamp,
            "verification_status":"needs_agent_review",
        }
        state["properties"].append(property_record)
        existing["properties"].add(pid)
        summary["created"]["properties"]+=1
    for row in tenancies:
        ext=value(row,"external_id",100,True)
        prop_ext=value(row,"property_external_id",100,True)
        tenant_ext=value(row,"tenant_external_id",100,True)
        owner_ext=value(row,"landlord_external_id",100,True)
        if prop_ext not in prop_map:
            raise MigrationError("Tenancy references unknown property: "+prop_ext)
        if tenant_ext not in mapped or mapped[tenant_ext][1]!="tenant":
            raise MigrationError("Tenancy references unknown tenant: "+tenant_ext)
        if owner_ext not in mapped or mapped[owner_ext][1]!="landlord":
            raise MigrationError("Tenancy references unknown landlord: "+owner_ext)
        property_record=next(p for p in state["properties"] if p.get("id")==prop_map[prop_ext])
        if property_record.get("landlord_party_id")!=mapped[owner_ext][0]:
            raise MigrationError("Tenancy landlord does not match property owner")
        tid=stable_id("tenancy",agency,ext)
        if tid in existing["tenancies"]:
            prior=next(t for t in state["tenancies"] if t.get("id")==tid)
            if prior.get("import_external_id")!=ext:
                raise MigrationError("Existing tenancy conflicts with import")
            summary["already_present"]["tenancies"]+=1
            continue
        start=value(row,"start_date",10,True)
        rent=positive_money(row,"rent_amount_pence",False)
        deposit=positive_money(row,"deposit_amount_pence")
        period=value(row,"rent_frequency",20,True)
        try:
            terms=assured_periodic_terms(start,period,rent,deposit)
        except ValueError as exc:
            raise MigrationError("Tenancy " + ext + ": " + str(exc)) from None
        record={
            "id":tid,"property_id":prop_map[prop_ext],
            "tenant_party_ids":[mapped[tenant_ext][0]],
            "landlord_party_ids":[mapped[owner_ext][0]],
            "start_date":start,"end_date":None,**terms,
            "rent_amount_pence":rent,"rent_frequency":period,
            "deposit_amount_pence":deposit,"deposit_scheme":None,
            "deposit_reference":None,"agreement_status":"draft",
            "status":"application","move_in_date":None,"notice_date":None,
            "checkout_date":None,"document_ids":[],
            "created_at":timestamp,"updated_at":timestamp,
            "history":[{"event":"offline_csv_import","at":timestamp,"by":actor}],
            "agency_id":agency,"import_external_id":ext,"import_batch":batch,
            "source":actor,"verification_status":"needs_agent_review",
        }
        state["tenancies"].append(record)
        existing["tenancies"].add(tid)
        summary["created"]["tenancies"]+=1
    summary["total_created"]=sum(summary["created"].values())
    # Full rollback is simply restoring the pre-import file backup.
    return state,summary


def atomic_write(path, value):
    path=Path(path)
    encoded=json.dumps(value,indent=2,ensure_ascii=False).encode("utf-8")
    fd,name=tempfile.mkstemp(prefix=".roger-import-",dir=str(path.parent))
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(encoded);stream.flush();os.fsync(stream.fileno())
        os.chmod(name,0o600)
        os.replace(name,path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def safe_print(plan_result):
    print(json.dumps(plan_result,indent=2,sort_keys=True))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("data_dir","people","properties","tenancies"):
        parser.add_argument("--"+name.replace("_","-"),required=True)
    parser.add_argument("--apply",action="store_true",
                        help="Write the new snapshot after complete dry-run and backup")
    parser.add_argument("--confirm",default="",help="Type OFFLINE-IMPORT only for --apply")
    args=parser.parse_args(argv)
    folder=Path(args.data_dir).resolve()
    snapshot=folder/"stage.json"
    if not snapshot.is_file():
        parser.error("stage.json not found in the explicit offline data directory")
    if args.apply and (args.confirm!="OFFLINE-IMPORT" or
                       os.environ.get("ROGER_MIGRATION_OFFLINE")!="1"):
        parser.error("Refusing write: set ROGER_MIGRATION_OFFLINE=1 and --confirm OFFLINE-IMPORT")
    if args.apply and os.environ.get("ROGER_ENV") in ("production","staging"):
        parser.error("No write against running hosted production/staging data")
    texts={}
    for kind in ("people","properties","tenancies"):
        p=Path(getattr(args,kind))
        if p.stat().st_size>4_000_000:
            parser.error(kind+" file exceeds 4MB")
        texts[kind]=p.read_text(encoding="utf-8-sig")
    current=json.loads(snapshot.read_text(encoding="utf-8"))
    state,report=plan(current,texts["people"],texts["properties"],texts["tenancies"])
    safe_print(report)
    if not args.apply:
        print("DRY RUN ONLY: no changes written")
        return
    backup_dir=folder/"backups"
    backup_dir.mkdir(mode=0o700,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup=backup_dir/("before-agency-import-"+stamp+".json")
    with backup.open("xb") as out:
        os.chmod(backup,0o600)
        out.write_bytes(snapshot.read_bytes())
        out.flush();os.fsync(out.fileno())
    atomic_write(snapshot,state)
    print("OFFLINE IMPORT APPLIED; original snapshot backed up to "+str(backup))


if __name__=="__main__":
    main()
