"""Independent MVP platform-owner login. No agency session grants owner access."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

COOKIE = "roger_hq_owner"
TTL = 12 * 3600

def configured():
    return bool(os.environ.get("ROGER_HQ_OWNER_USERNAME") and
                os.environ.get("ROGER_HQ_OWNER_PASSWORD_HASH") and
                os.environ.get("ROGER_HQ_SESSION_SECRET"))

def password_matches(username, password):
    if not configured() or not isinstance(username, str) or not isinstance(password, str):
        return False
    if len(username) > 100 or len(password) > 200:
        return False
    expected_user = os.environ["ROGER_HQ_OWNER_USERNAME"]
    if not hmac.compare_digest(username, expected_user):
        return False
    try:
        salt, digest = os.environ["ROGER_HQ_OWNER_PASSWORD_HASH"].split(":", 1)
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                                n=2**14, r=8, p=1).hex()
        return hmac.compare_digest(actual, digest)
    except (ValueError, TypeError):
        return False

def issue_token():
    payload = {"exp": int(time.time()) + TTL, "nonce": secrets.token_hex(16)}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(os.environ["ROGER_HQ_SESSION_SECRET"].encode(), body.encode(), hashlib.sha256).hexdigest()
    return body + "." + sig

def valid_token(token):
    if not configured() or not isinstance(token, str) or len(token) > 500:
        return False
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(os.environ["ROGER_HQ_SESSION_SECRET"].encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return isinstance(data.get("exp"), int) and int(time.time()) < data["exp"]
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False
