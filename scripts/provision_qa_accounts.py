#!/usr/bin/env python3
"""Offline, fail-closed provisioner for four isolated Roger QA accounts.

Run --apply ONLY while the Roger application is stopped. Passwords are written
once to a private recovery folder; never publish them to GitHub or chat.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
import uuid

ACCOUNTS = (
    ("agent-qa", "agent", "QA Agent (TEST ONLY)"),
    ("tenant-qa", "tenant", "QA Tenant (TEST ONLY)"),
    ("landlord-qa", "landlord", "QA Landlord (TEST ONLY)"),
    ("trades-qa", "trades", "QA Trades (TEST ONLY)"),
)


def timestamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read(data):
    users = json.loads((data / "users.json").read_text(encoding="utf-8"))
    stage = json.loads((data / "stage.json").read_text(encoding="utf-8"))
    if not isinstance(users, dict) or not isinstance(users.get("users"), list):
        raise ValueError("Invalid user database")
    if not isinstance(users.get("sessions"), dict):
        raise ValueError("Invalid sessions")
    if not isinstance(stage, dict) or not isinstance(stage.get("parties"), list):
        raise ValueError("Invalid Party database")
    if not isinstance(stage.get("audit_log"), list):
        raise ValueError("Invalid audit database")
    if not isinstance(stage.get("next_party_id"), int) or stage["next_party_id"] < 1:
        raise ValueError("Invalid Party counter")
    original = users["users"]
    if (len(original) != 1 or original[0].get("username") != "agent"
            or original[0].get("role") != "agent"
            or not original[0].get("account_id")):
        raise ValueError("Expected one clean administrator account; STOP")
    party_ids = {p.get("id") for p in stage["parties"]}
    for number in range(stage["next_party_id"], stage["next_party_id"] + 4):
        if f"party-{number}" in party_ids:
            raise ValueError("Party ID collision; STOP")
    return users, stage


def prepare(users, stage):
    users, stage = copy.deepcopy(users), copy.deepcopy(stage)
    credentials = []
    for username, role, display in ACCOUNTS:
        password = secrets.token_urlsafe(24)
        salt = secrets.token_hex(16)
        account_id = str(uuid.uuid4())
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                                n=2**14, r=8, p=1).hex()
        users["users"].append({
            "username": username, "role": role, "display_name": display,
            "account_id": account_id, "salt": salt, "hash": digest,
            "created": timestamp(),
        })
        party_id = f"party-{stage['next_party_id']}"
        stage["next_party_id"] += 1
        stage["parties"].append({
            "id": party_id, "kind": "person", "display_name": display,
            "legal_name": None, "email": None, "phone": None, "address": None,
            "roles": [role], "status": "active",
            "notes": "TEST ONLY - NOT A REAL CLIENT", "account_id": account_id,
            "created_at": timestamp(), "created_by": "qa-provisioner",
        })
        stage["audit_log"].append({
            "at": timestamp(), "actor": "qa-provisioner",
            "action": "qa_account_created", "target": party_id,
            "note": f"QA {role} account {username}",
        })
        credentials.append((username, role, password))
    return users, stage, credentials


def atomic_json(path, value):
    fd, temporary = tempfile.mkstemp(prefix=".roger-qa-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(value, file, indent=2, ensure_ascii=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def private_file(path, value):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        file.write(value)
        file.flush()
        os.fsync(file.fileno())


def provision(data_dir, recovery_parent, apply):
    original_users, original_stage = read(data_dir)
    if not apply:
        return None
    if not recovery_parent or not recovery_parent.is_dir():
        raise ValueError("An existing --recovery-parent is required")
    if recovery_parent.resolve() == data_dir.resolve():
        raise ValueError("Recovery location cannot be the live volume")
    backup = Path(tempfile.mkdtemp(prefix="roger-qa-", dir=recovery_parent))
    os.chmod(backup, 0o700)
    touched = False
    try:
        for name in ("users.json", "stage.json"):
            shutil.copyfile(data_dir / name, backup / name)
            os.chmod(backup / name, 0o600)
        sources = {name: hashlib.sha256((data_dir / name).read_bytes()).hexdigest()
                   for name in ("users.json", "stage.json")}
        private_file(backup / "source-sha256.json", json.dumps(sources, indent=2))
        users, stage, passwords = prepare(original_users, original_stage)
        creds = ("ROGER QA TEST ACCOUNTS - PRIVATE - " + timestamp() + "\n"
                 "These test accounts exist on the live server.\n"
                 "WARNING: agent-qa has FULL ADMINISTRATOR access.\n"
                 "Never paste these passwords into chat. Delete accounts after QA.\n\n"
                 + "".join(f"Username: {u}\nRole: {r}\nPassword: {p}\n\n"
                           for u, r, p in passwords))
        private_file(backup / "qa-credentials.txt", creds)
        # The service MUST be stopped to prevent concurrent writes.
        # Write Party links first; enable logins only after links are ready.
        touched = True
        atomic_json(data_dir / "stage.json", stage)
        atomic_json(data_dir / "users.json", users)
        if (json.loads((data_dir / "stage.json").read_text()) != stage
                or json.loads((data_dir / "users.json").read_text()) != users):
            raise RuntimeError("Post-write validation failed")
        return backup
    except Exception:
        if touched:
            for name in ("stage.json", "users.json"):
                atomic_json(data_dir / name,
                            json.loads((backup / name).read_text(encoding="utf-8")))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--recovery-parent", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        folder = provision(args.data_dir, args.recovery_parent, args.apply)
        if folder is None:
            print("PRECHECK PASSED - four isolated QA accounts can be provisioned")
        else:
            print("QA ACCOUNTS CREATED: agent-qa, tenant-qa, landlord-qa, trades-qa")
            print("Private credentials:", folder / "qa-credentials.txt")
            print("Data backups:", folder)
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as exc:
        print("PROVISIONING FAILED:", exc, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
