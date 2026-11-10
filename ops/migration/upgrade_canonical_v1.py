#!/usr/bin/env python3
"""Offline, reversible Roger canonical model v1 schema upgrade.

Dry-run by default; no network or application operation. Operate on a stopped,
isolated copy only. An upgrade preserves every existing record and creates
property_units / ownership_interests arrays; no owner guesses or account links.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"stage-clone"))
import canonical_records as model
import legacy_reconciliation as reconciliation


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic_replace(file, bytes_data):
    fd, temp = tempfile.mkstemp(prefix=".roger-v1-upgrade-", dir=str(file.parent))
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(bytes_data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp,0o600)
        os.replace(temp,file)
        try:
            dfd=os.open(str(file.parent),os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def backup_before(file, content):
    directory=file.parent/"backups"
    directory.mkdir(mode=0o700,exist_ok=True)
    name="before-canonical-v1-"+datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ")+".json"
    dest=directory/name
    with dest.open("xb") as stream:
        os.chmod(dest,0o600)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    return dest


def run(directory, *, apply=False, confirm="", rollback=None, offline=False,
        environment=None):
    directory=Path(directory).resolve()
    file=directory/"stage.json"
    if not file.is_file():
        raise ValueError("Stage snapshot not found in selected offline directory")
    if apply or rollback:
        if environment in ("production","staging") or not offline or confirm!="OFFLINE-SCHEMA":
            raise ValueError("Writes require OFFLINE-SCHEMA on a stopped isolated copy")
    content=file.read_bytes()
    current=json.loads(content)
    if rollback is not None:
        source=Path(rollback).resolve()
        parent=directory/"backups"
        if source.parent!=parent or source.suffix!=".json" or not source.name.startswith(
                "before-canonical-v1-"):
            raise ValueError("Restore source must be a canonical backup inside this instance")
        before=source.read_bytes()
        restored=json.loads(before)
        model.validate_for_save(restored)
        new_backup=backup_before(file,content)
        atomic_replace(file,before)
        if file.read_bytes()!=before:
            raise RuntimeError("Restored bytes do not match backup")
        return {"action":"rollback","source_sha256":sha(before),
                "current_before_sha256":sha(content),
                "emergency_backup":str(new_backup),"changed":True}
    upgraded,report=model.propose_upgrade(current)
    review=reconciliation.reconciliation_report(current)
    after=json.dumps(upgraded,ensure_ascii=False,indent=2).encode("utf-8")
    result={
        "action":"upgrade_preview" if not apply else "upgrade",
        "old_sha256":sha(content),"new_sha256":sha(after),
        "original_records_preserved":True,
        "legacy_link_warnings":review["issues"],
        "canonical_authorities":review["authoritative"],
        "model_version":upgraded["model_metadata"]["version"],
        "changed":False,
    }
    if apply:
        if review["issues"]:
            raise ValueError("Unresolved legacy links, invoice shadows or document pointers require review before apply")
        dest=backup_before(file,content)
        atomic_replace(file,after)
        if file.read_bytes()!=after:
            raise RuntimeError("Upgraded bytes do not match expected output")
        result["backup"]=str(dest)
        result["changed"]=after!=content
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir",required=True)
    p.add_argument("--apply",action="store_true")
    p.add_argument("--rollback",help="Full path of exact pre-upgrade backup")
    p.add_argument("--confirm",default="")
    args=p.parse_args(argv)
    if args.apply and args.rollback:
        p.error("Choose upgrade or rollback, not both")
    result=run(args.data_dir,apply=args.apply,confirm=args.confirm,
               rollback=args.rollback,
               offline=os.environ.get("ROGER_MIGRATION_OFFLINE")=="1",
               environment=os.environ.get("ROGER_ENV"))
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
