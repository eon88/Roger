"""Roger B02 auth helpers: fail-closed session binding, TOTP and safe projections.

No external network or provider dependency. MFA enrolment must be deliberate,
and all user/recovery secrets are excluded from portal and log responses.
"""
import base64
import hashlib
import hmac
import re
import struct
import time
from datetime import datetime, timezone

ALLOWED_ROLES = frozenset({"agent", "tenant", "landlord", "trades"})
SESSION_AUTH_VERSION = 2
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'; base-uri 'self'; object-src 'none'",
}


def session_principal(user):
    """Bind session to the *same* credential, role, account and agency."""
    return {
        "auth_version": SESSION_AUTH_VERSION,
        "role": user.get("role"),
        "account_id": user.get("account_id"),
        "password_fingerprint": hashlib.sha256(
            str(user.get("hash", "")).encode()).hexdigest(),
        "agency_id": user.get("agency_id"),
    }


def current_session(session, user, agency_id=None):
    if (not isinstance(session, dict) or not isinstance(user, dict)
            or user.get("disabled_at") or user.get("role") not in ALLOWED_ROLES
            or user.get("role") != session.get("role")
            or session.get("auth_version") != SESSION_AUTH_VERSION):
        return False
    principal = session_principal(user)
    if any(session.get(field) != principal[field] for field in (
            "account_id", "password_fingerprint", "agency_id")):
        return False
    if agency_id and user.get("agency_id") not in (None, agency_id):
        return False
    try:
        expiry = datetime.fromisoformat(str(session["exp"]).replace("Z", "+00:00"))
        return expiry.tzinfo is not None and expiry > datetime.now(timezone.utc)
    except (TypeError, ValueError, KeyError):
        return False


def totp_key(secret):
    if not isinstance(secret, str) or not re.fullmatch(r"[A-Z2-7]{32}", secret):
        raise ValueError("invalid TOTP secret")
    return base64.b32decode(secret, casefold=False)


def new_totp_secret(random_bytes):
    if not isinstance(random_bytes, bytes) or len(random_bytes) != 20:
        raise ValueError("TOTP requires 20 cryptographically random bytes")
    return base64.b32encode(random_bytes).decode("ascii").rstrip("=")


def totp_at(secret, step):
    key = totp_key(secret)
    msg = struct.pack(">Q", int(step))
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 15
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7fffffff
    return str(number % 1000000).zfill(6)


def verify_totp(secret, code, *, now=None, last_step=-1):
    """Return accepted step, or None; never accept a step used previously."""
    if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code):
        return None
    step = int(time.time() if now is None else now) // 30
    for candidate in (step, step - 1, step + 1):
        if candidate < 0 or candidate <= last_step:
            continue
        if hmac.compare_digest(totp_at(secret, candidate), code):
            return candidate
    return None


def password_matches(user, supplied):
    if not isinstance(supplied, str) or len(supplied.encode("utf-8")) > 512:
        return False
    try:
        salt = bytes.fromhex(user["salt"])
        digest = hashlib.scrypt(supplied.encode(), salt=salt,
                                n=2**14, r=8, p=1).hex()
        return hmac.compare_digest(digest, user["hash"])
    except (KeyError, TypeError, ValueError):
        return False


def public_error(error):
    """Do not return raw traceback, SQL, SMTP/IMAP or local filesystem data."""
    if error in {"authentication required", "not permitted", "not found",
                 "request rejected", "try again later"}:
        return error
    return "request rejected"
