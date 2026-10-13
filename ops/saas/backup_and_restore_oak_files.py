#!/usr/bin/env python3
"""Back up and restore SYNTHETIC Oak files AND its PostgreSQL snapshot.

Only the disposable stg-oak agent is read; live Roger and Birch are untouched.
A fresh backup is retained on the VPS and a separate test-only restore copy
is removed after checking every byte. This is NOT an off-server backup.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile

import verify_oak_restore as database_restore

ROOT = Path("/root/roger-staging")
SOURCE_APP = "roger-stg-oak-app-1"
SOURCE_DB = "roger-stg-oak-postgres-1"
DOC_TITLE = "Oak synthetic file backup test"
DOC_BODY = b"Roger staging document recovery test. Fictional content only.\n"
DOC_HASH = hashlib.sha256(DOC_BODY).hexdigest()
SQL = "SELECT payload FROM roger_stage_snapshot WHERE singleton_id=1;"


def safe_run(argv, *, output=None, timeout=90):
    try:
        result = subprocess.run(argv, stdout=output if output is not None else subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True, timeout=timeout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        # Do not print argv/stderr: SQL statements or secrets could appear in them.
        raise RuntimeError("safe Docker backup operation failed") from None
    return result.stdout


def synthetic_document_metadata():
    data = safe_run(["docker", "exec", SOURCE_DB, "psql",
                     "-X", "-U", "roger", "-d", "roger", "-At", "-c", SQL])
    stage = json.loads(data.decode())
    if stage.get("agency_id") != "stg-oak":
        raise ValueError("source is not the Oak staging agency")
    docs = [d for d in stage.get("documents", [])
            if d.get("title") == DOC_TITLE]
    if len(docs) != 1:
        raise ValueError("expected exactly one synthetic Oak file record")
    doc = docs[0]
    if doc.get("storage_key") != DOC_HASH or doc.get("file_size") != len(DOC_BODY):
        raise ValueError("synthetic document metadata does not match test bytes")
    return doc


def file_manifest(files):
    """Allow only content-addressed regular files; never follow symbolic links."""
    found = {}
    if files.is_symlink() or not files.is_dir():
        raise ValueError("backup files directory is missing or a symlink")
    for p in files.rglob("*"):
        if p.is_symlink():
            raise ValueError("refusing symlink in staged files backup")
        if p.is_dir():
            continue
        if not p.is_file():
            raise ValueError("unexpected special file in backup")
        rel = p.relative_to(files).as_posix()
        if not re.fullmatch(r"[a-f0-9]{2}/[a-f0-9]{64}", rel):
            raise ValueError("unexpected storage path in backup")
        expected = p.name
        if expected[:2] != p.parent.name:
            raise ValueError("incorrect content-addressed directory")
        digest = hashlib.sha256()
        with p.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        actual = digest.hexdigest()
        if actual != expected:
            raise ValueError("backup contains corrupted file")
        found[rel] = actual
    return found


def create_matching_backup(doc):
    if ROOT.is_symlink() or not ROOT.is_dir():
        raise ValueError("staging directory missing or invalid")
    previous = os.umask(0o077)
    try:
        backup = ROOT / ("backup-oak-" + secrets.token_hex(8))
        backup.mkdir(mode=0o700)
        dump = backup / "oak-postgres.dump"
        with dump.open("xb") as stream:
            safe_run(["docker", "exec", SOURCE_DB,
                      "pg_dump", "-U", "roger", "-d", "roger", "-Fc"],
                     output=stream, timeout=120)
        if dump.stat().st_size == 0:
            raise RuntimeError("empty database backup")
        digest = hashlib.sha256(dump.read_bytes()).hexdigest()
        (backup / "oak-postgres.dump.sha256").write_text(
            digest + "  " + str(dump) + "\n")
        files = backup / "files"
        files.mkdir(mode=0o700)
        safe_run(["docker", "cp", SOURCE_APP + ":/data/files/.", str(files)])
        manifest = file_manifest(files)
        target_rel = DOC_HASH[:2] + "/" + DOC_HASH
        if manifest.get(target_rel) != DOC_HASH:
            raise ValueError("synthetic document not in file backup")
        if (files / target_rel).read_bytes() != DOC_BODY:
            raise ValueError("test document in backup differs from original")
        (backup / "files.sha256.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        print("PASS: fresh matching database and files backup created", flush=True)
        print("PASS: synthetic document file and SHA-256 manifest verified", flush=True)
        return backup, manifest
    finally:
        os.umask(previous)


def restore_and_compare(backup, manifest):
    dump = database_restore.checked_backup(str(backup))
    database_restore.restore(dump, database_restore.rows(SOURCE_DB))
    print("PASS: restored database matches Oak including document records", flush=True)
    with tempfile.TemporaryDirectory(prefix="roger-stg-files-restore-", dir=ROOT) as path:
        restored = Path(path) / "restored_files"
        shutil.copytree(backup / "files", restored, symlinks=False)
        recovered_manifest = file_manifest(restored)
        if recovered_manifest != manifest:
            raise ValueError("recovered files do not match backup manifest")
        doc_path = restored / DOC_HASH[:2] / DOC_HASH
        if doc_path.read_bytes() != DOC_BODY:
            raise ValueError("recovered synthetic document differs")
        print("PASS: restored file bytes match backed-up document", flush=True)
    print("PASS: isolated restored file directory removed", flush=True)


def main():
    try:
        original = database_restore.preflight()
        print("PASS: live and staging containers healthy; resources available", flush=True)
        document = synthetic_document_metadata()
        print("PASS: Oak's synthetic document record exists in PostgreSQL", flush=True)
        backup, manifest = create_matching_backup(document)
        if original.split("|", 1)[0] != "stg-oak":
            raise ValueError("agency changed unexpectedly")
        restore_and_compare(backup, manifest)
        for name in database_restore.LIVE:
            status = database_restore.call(
                "docker", "inspect", "-f", "{{.State.Health.Status}}", name).strip()
            if status != "healthy":
                raise ValueError("live " + name + " no longer healthy")
        print("FILE AND DATABASE RECOVERY PASSED — live Roger unaffected", flush=True)
        print("Private staging backup retained: " + str(backup), flush=True)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        # Errors from Docker never include full commands, SQL or credentials.
        print("STOP: combined recovery test not passed: " + str(exc)[:180],
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
