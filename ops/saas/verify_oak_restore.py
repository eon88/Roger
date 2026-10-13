#!/usr/bin/env python3
"""Restore an Oak SYNTHETIC staging dump into a disposable offline Postgres.

Never touches production containers, networks, DNS, volumes, or Oak/Birch data.
Explicitly refuses non-staging source names and backup paths.
"""
import hashlib
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time

BACKUP_ROOT = Path("/root/roger-staging")
SOURCE = "roger-stg-oak-postgres-1"
RESTORE = "roger-stg-restore-check"
IMAGE = "postgres:16-alpine"
GIB = 1024 ** 3
MIN_AVAILABLE = int(1.5 * GIB)
LIVE = ("roger", "roger-postgres")
STAGING = (
    "roger-stg-oak-app-1", SOURCE,
    "roger-stg-birch-app-1", "roger-stg-birch-postgres-1",
)
SQL = """SELECT
    (SELECT payload->>'agency_id' FROM roger_stage_snapshot),
    (SELECT md5(payload::text) FROM roger_stage_snapshot),
    (SELECT md5(payload::text) FROM roger_users_snapshot),
    (SELECT count(*) FROM roger_properties),
    (SELECT count(*) FROM roger_parties),
    (SELECT count(*) FROM roger_cases),
    (SELECT count(*) FROM roger_documents);"""


def call(*argv, timeout=20, stdin=None):
    return subprocess.run(argv, stdin=stdin, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=stdin is None,
                          timeout=timeout, check=True).stdout


def safe_restore_failure(exc):
    """Show only PostgreSQL's error headline, not SQL statements or secrets."""
    err = exc.stderr or b""
    if isinstance(err, bytes):
        err = err.decode("utf-8", errors="replace")
    headlines = []
    for line in err.splitlines():
        line = line.strip()
        if line.startswith("pg_restore: error:"):
            # Hide subsequent command/SQL/detail lines, which may include data.
            headlines.append(line.split("Command was:", 1)[0][:250])
    return " | ".join(headlines[:2]) or "pg_restore exited unsuccessfully (stderr hidden)"


def read_available_memory():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise ValueError("MemAvailable missing")


def checked_backup(arg):
    raw = Path(arg)
    root = BACKUP_ROOT.resolve(strict=True)
    if raw.is_symlink():
        raise ValueError("backup directory cannot be a symlink")
    folder = raw.resolve(strict=True)
    if folder.parent != root or not re.fullmatch(r"backup-oak-[A-Za-z0-9]+", folder.name):
        raise ValueError("only an Oak backup directly under /root/roger-staging is allowed")
    data = folder / "oak-postgres.dump"
    checksum = folder / "oak-postgres.dump.sha256"
    if any(f.is_symlink() or not f.is_file() for f in (data, checksum)):
        raise ValueError("regular dump and checksum files required")
    contents = checksum.read_text().strip()
    expected, _, target = contents.partition("  ")
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or Path(target) != data:
        raise ValueError("checksum entry does not match expected backup file")
    digest = hashlib.sha256()
    with data.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError("backup checksum mismatch")
    return data


def rows(name):
    return call("docker", "exec", name,
                "psql", "-X", "-U", "roger", "-d", "roger",
                "-At", "-F", "|", "-c", SQL, timeout=25).strip()


def preflight():
    if read_available_memory() < MIN_AVAILABLE:
        raise ValueError("available RAM below 1.5 GiB; no restore started")
    load = os.getloadavg()[0]
    if load > 0.65 * (os.cpu_count() or 1):
        raise ValueError("CPU load too high for this rehearsal")
    names = set(call("docker", "ps", "-a", "--format", "{{.Names}}").splitlines())
    if RESTORE in names:
        raise ValueError("restore container already exists; refusing to modify it")
    for name in LIVE + STAGING:
        if name not in names:
            raise ValueError("required container missing: " + name)
        status = call("docker", "inspect", "-f", "{{.State.Health.Status}}", name).strip()
        if status != "healthy":
            raise ValueError(name + " is not healthy")
    if not call("docker", "image", "inspect", "--format", "{{.Id}}", IMAGE).strip():
        raise ValueError("Postgres 16 Alpine image not available")
    original = rows(SOURCE)
    if original.split("|", 1)[0] != "stg-oak":
        raise ValueError("source database is not the Oak staging agency")
    return original


def restored_database_ready():
    """Check the actual target database can run SQL, not just pg_isready.

    During PostgreSQL first boot, pg_isready can return success while initdb
    is still creating the requested database. Restoring at that point fails
    with "database roger does not exist".
    """
    probe = subprocess.run(
        ["docker", "exec", RESTORE, "psql", "-X", "-U", "roger",
         "-d", "roger", "-At", "-c", "SELECT 1"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, timeout=5, check=False)
    return probe.returncode == 0 and probe.stdout.strip() == "1"


def restore(dump, original):
    created = False
    try:
        call("docker", "run", "-d", "--rm", "--pull=never",
             "--name", RESTORE, "--network", "none",
             "--memory", "256m", "--cpus", "0.12",
             "--pids-limit", "64", "--restart", "no",
             "-e", "POSTGRES_USER=roger",
             "-e", "POSTGRES_DB=roger",
             "-e", "POSTGRES_PASSWORD=" + secrets.token_hex(24),
             IMAGE, timeout=30)
        created = True
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                if restored_database_ready():
                    break
            except subprocess.TimeoutExpired:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("temporary roger database did not accept SQL in time")
        print("PASS: temporary roger database accepts SQL queries")
        with dump.open("rb") as stream:
            try:
                call("docker", "exec", "-i", RESTORE, "pg_restore",
                     "-U", "roger", "-d", "roger",
                     "--no-owner", "--no-acl", "--exit-on-error",
                     stdin=stream, timeout=120)
            except subprocess.CalledProcessError as exc:
                raise RuntimeError("Database import step: " + safe_restore_failure(exc)) from None
        try:
            recovered = rows(RESTORE)
        except subprocess.CalledProcessError:
            raise RuntimeError("Restored database verification query failed") from None
        if recovered != original:
            raise ValueError("restored database does not match original")
        print("PASS: restored Oak database matches source records and users")
    finally:
        if created:
            subprocess.run(["docker", "rm", "-f", RESTORE],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=20, check=True)
            print("PASS: temporary restore database container removed")


def main():
    if len(sys.argv) != 2:
        print("Usage: verify_oak_restore.py /root/roger-staging/backup-oak-XXXXXXXX", file=sys.stderr)
        return 2
    try:
        dump = checked_backup(sys.argv[1])
        print("PASS: backup checksum verified")
        original = preflight()
        print("PASS: production and test containers healthy; restore resources available")
        restore(dump, original)
        for name in LIVE:
            status = call("docker", "inspect", "-f", "{{.State.Health.Status}}", name).strip()
            if status != "healthy":
                raise ValueError("live " + name + " became unhealthy after restore")
        print("RESTORE TEST PASSED — live Roger unaffected")
        return 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # Never print Docker argv: the disposable container creation argv
        # contains its randomly generated PostgreSQL password.
        print("STOP: restore subprocess failed:", type(exc).__name__,
              file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError) as exc:
        print("STOP: restore test not passed:", str(exc)[:180], file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
