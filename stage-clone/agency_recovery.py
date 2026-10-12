#!/usr/bin/env python3
"""Operator-only recovery of a single, verified SaaS agency administrator.

Run only INSIDE the intended agency app container after verifying the
requesting business owner out-of-band. Never run from an HTTP request.
Creates a private, one-time handoff file without logging the password.
"""
import argparse
import hashlib
import os
from pathlib import Path
import secrets
import stat

import serve

# Must be a Docker tmpfs mount. Never write recovery secrets to /data.
RECOVERY_TMPFS_DIR = Path("/run/roger-recovery")


def recover_admin(output, expected_agency):
    configured = os.environ.get("ROGER_AGENCY_ID")
    if (os.environ.get("ROGER_SAAS_MODE") != "1"
            or os.environ.get("ROGER_STORAGE_BACKEND") != "postgres"
            or not configured or expected_agency != configured):
        raise RuntimeError("recovery is restricted to the explicitly selected SaaS agency")
    path = Path(output)
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise ValueError("use a new, absolute credential file path")
    parent = path.parent
    if parent != RECOVERY_TMPFS_DIR or not parent.is_mount():
        raise ValueError("recovery credentials must be written to the dedicated ephemeral tmpfs mount")
    if (not parent.is_dir() or parent.is_symlink()
            or stat.S_IMODE(parent.stat().st_mode) & 0o077
            or parent.stat().st_uid != os.getuid()):
        raise ValueError("credential output directory must exist, be private (0700) and owned by the operator")

    with serve.storage_write_lock():
        stage = serve.load_stage()
        if stage.get("agency_id") != expected_agency:
            raise RuntimeError("agency database does not match the selected customer")
        users = serve.load_users()
        matching = [user for user in users.get("users", [])
                    if user.get("username") == "agency-admin"
                    and user.get("role") == "agent" and not user.get("disabled_at")]
        if len(matching) != 1:
            raise RuntimeError("exactly one active agency-admin agent is required")

        password = secrets.token_urlsafe(32)
        salt = secrets.token_hex(16)
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                               n=2**14, r=8, p=1).hex()
        # Write the one-time credential first. If it cannot be handed off
        # securely, do not lock the customer out by resetting the database.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write("AGENCY=" + expected_agency + "\n")
                handle.write("USERNAME=agency-admin\n")
                handle.write("TEMPORARY_PASSWORD=" + password + "\n")
                handle.write("One-time credential. Verify recipient; delete after secure handoff.\n")
                handle.flush()
                os.fsync(handle.fileno())

            account = matching[0]
            account["salt"] = salt
            account["hash"] = digest
            account["password_change_required"] = True
            old_sessions = users.get("sessions", {})
            users["sessions"] = {
                token: session for token, session in old_sessions.items()
                if session.get("username") != "agency-admin"
            }
            serve.save_users(users)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return {"agency_id": expected_agency, "credential_file": str(path),
                "revoked_sessions": len(old_sessions) - len(users["sessions"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agency", required=True,
                        help="Must exactly equal this container's ROGER_AGENCY_ID")
    parser.add_argument("--output", required=True,
                        help="New file in the agency app's private /run/roger-recovery tmpfs directory")
    args = parser.parse_args()
    result = recover_admin(args.output, args.agency)
    print("Recovery credential file:", result["credential_file"])
    print("Agency:", result["agency_id"])
    print("Sessions revoked:", result["revoked_sessions"])
    print("Temporary password deliberately not printed. Securely hand off, then delete file.")


if __name__ == "__main__":
    main()
