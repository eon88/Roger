#!/usr/bin/env python3
"""Read-only, disposable restore rehearsal for Roger's file backend.

This does NOT back up a running server, check PostgreSQL, or replace any live data.
Input should be an already-quiesced offline *copy* of DATA_DIR containing
stage.json, users.json, and optionally files/<2 digits>/<SHA256>.
All private bytes are copied to a temporary 0700 directory and removed on exit.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile


def hash_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rehearsal(source):
    source = Path(source).resolve(strict=True)
    if not source.is_dir():
        raise ValueError("source must be an existing offline file-backend directory")
    paths = [Path("stage.json"), Path("users.json")]
    attachments = source / "files"
    if attachments.exists():
        if attachments.is_symlink():
            raise ValueError("backup includes a symlinked files directory")
        for folder, directories, files in os.walk(attachments, followlinks=False):
            for name in directories + files:
                if (Path(folder) / name).is_symlink():
                    raise ValueError("symlinks are not allowed in the restore snapshot")
            for name in files:
                paths.append((Path(folder) / name).relative_to(source))
    for item in paths:
        file_path = source / item
        if not file_path.is_file() or file_path.is_symlink():
            raise ValueError(f"required file missing or unsafe: {item}")
    with tempfile.TemporaryDirectory(prefix="roger-restore-rehearsal-") as temp:
        dst = Path(temp)
        os.chmod(dst, 0o700)
        for rel in paths:
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / rel, target)
            os.chmod(target, 0o600)
            if hash_file(source / rel) != hash_file(target):
                raise ValueError(f"restore copy failed checksum: {rel}")
        with (dst / "stage.json").open(encoding="utf-8") as f:
            stage = json.load(f)
        with (dst / "users.json").open(encoding="utf-8") as f:
            users = json.load(f)
        if not isinstance(stage, dict) or not isinstance(users, dict):
            raise ValueError("both state snapshots must be JSON objects")
        if not isinstance(users.get("users"), list) or not isinstance(users.get("sessions"), dict):
            raise ValueError("invalid users snapshot")
        if not isinstance(stage.get("cases", []), list) or not isinstance(stage.get("documents", []), list):
            raise ValueError("invalid Roger stage snapshot")
        for doc in stage.get("documents", []):
            key = doc.get("storage_key")
            if not key:
                continue  # historic base64-only records may require a separate migration
            if not isinstance(key, str) or len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
                raise ValueError("invalid document storage key")
            body = dst / "files" / key[:2] / key
            if not body.is_file() or hash_file(body) != key:
                raise ValueError("missing or damaged referenced document")
        return {"ok": True, "file_count": len(paths),
                "documents_checked": sum(bool(d.get("storage_key")) for d in stage.get("documents", [])),
                "cases_count": len(stage.get("cases", [])),
                "note": "Disposable offline file-backend copy only; not a production restore."}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("offline_data_dir", help="Path to quiesced copy of Roger file DATA_DIR, never live data")
    args = p.parse_args()
    print(json.dumps(rehearsal(args.offline_data_dir), indent=2))
