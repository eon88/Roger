"""Roger B03 agency onboarding/configuration rules.

An agency is one independently deployed stack. Nothing here charges money,
approves a legal obligation, deploys containers or authorises tenant access.
"""
import copy
import re
from datetime import datetime, timezone

SLUG = re.compile(r"^[a-z][a-z0-9-]{1,28}[a-z0-9]$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE = re.compile(r"^\+?[0-9()\s-]{7,35}$")
COLOUR = re.compile(r"^#[0-9A-Fa-f]{6}$")
OFFICE_KEYS = {
    "display_name": (3, 100),
    "legal_name": (0, 160),
    "office_address": (0, 400),
    "office_phone": (0, 35),
    "office_email": (0, 254),
    "opening_hours": (0, 400),
    "emergency_phone": (0, 35),
    "emergency_instructions": (0, 1200),
    "brand_colour": (7, 7),
}
STATUS = {"prepared", "active", "suspended", "cancelled"}
BILLING = {"manual-trial-not-active", "manual-trial", "manual-invoice-due",
           "manual-invoice-recorded", "manual-overdue", "manual-cancelled"}
PLANS = {"unassigned", "pilot", "standard", "portfolio"}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def initial_profile(slug, name, hostname):
    """Never create imaginary office contacts or a paid subscription."""
    if not SLUG.fullmatch(slug):
        raise ValueError("invalid agency identifier")
    if not isinstance(name, str) or not 3 <= len(name.strip()) <= 100:
        raise ValueError("invalid display name")
    if (not isinstance(hostname, str) or hostname.lower() != hostname
            or len(hostname) > 200 or "/" in hostname or "." not in hostname):
        raise ValueError("invalid agency hostname")
    return {
        "agency_id": slug, "hostname": hostname, "display_name": name.strip(),
        "legal_name": "", "office_address": "", "office_phone": "",
        "office_email": "", "opening_hours": "", "emergency_phone": "",
        "emergency_instructions": "", "brand_colour": "#163A5F",
        "branches": [], "plan": "unassigned",
        "property_limit": 0, "staff_limit": 0,
        "subscription_status": "manual-trial-not-active",
        "operational_status": "prepared", "version": 1,
        "created_at": utcnow(), "updated_at": utcnow(),
    }


def _text(value, key, minimum, maximum):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise ValueError(key + " has an invalid length")
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in value):
        raise ValueError(key + " contains control characters")
    return value.strip()


def _contact_fields(item):
    if item.get("office_email") and not EMAIL.fullmatch(item["office_email"]):
        raise ValueError("office_email is invalid")
    for key in ("office_phone", "emergency_phone"):
        if item.get(key) and not PHONE.fullmatch(item[key]):
            raise ValueError(key + " is invalid")
    if not COLOUR.fullmatch(item["brand_colour"]):
        raise ValueError("brand_colour must be a six-digit hex colour")


def _branches(value):
    if not isinstance(value, list) or len(value) > 25:
        raise ValueError("branches must be a list of at most 25")
    seen = set()
    result = []
    for branch in value:
        if not isinstance(branch, dict) or set(branch) != {"id", "name", "address", "phone", "email"}:
            raise ValueError("branch requires id, name, address, phone and email")
        ident = branch["id"]
        if not isinstance(ident, str) or not SLUG.fullmatch(ident) or ident in seen:
            raise ValueError("branch IDs must be distinct safe slugs")
        seen.add(ident)
        clean = {"id": ident,
                 "name": _text(branch["name"], "branch name", 3, 120),
                 "address": _text(branch["address"], "branch address", 0, 400),
                 "phone": _text(branch["phone"], "branch phone", 0, 35),
                 "email": _text(branch["email"], "branch email", 0, 254)}
        if clean["email"] and not EMAIL.fullmatch(clean["email"]):
            raise ValueError("branch email is invalid")
        if clean["phone"] and not PHONE.fullmatch(clean["phone"]):
            raise ValueError("branch phone is invalid")
        result.append(clean)
    return result


def update_settings(profile, data):
    """Update descriptive settings only. Billing/limits/status are operator-owned."""
    if not isinstance(profile, dict) or not isinstance(data, dict):
        raise ValueError("agency settings must be objects")
    if type(data.get("expected_version")) is not int or data["expected_version"] != profile.get("version"):
        raise ValueError("agency settings were updated; reload before saving")
    allowed = set(OFFICE_KEYS) | {"branches", "expected_version"}
    if set(data) - allowed:
        raise ValueError("unsupported or privileged agency settings")
    if not (set(data) - {"expected_version"}):
        raise ValueError("no agency settings supplied")
    edited = copy.deepcopy(profile)
    for key, (minimum, maximum) in OFFICE_KEYS.items():
        if key in data:
            edited[key] = _text(data[key], key, minimum, maximum)
    if "branches" in data:
        edited["branches"] = _branches(data["branches"])
    _contact_fields(edited)
    edited["version"] = profile["version"] + 1
    edited["updated_at"] = utcnow()
    return edited


def operator_transition(profile, action, *, reason, evidence=None, plan=None,
                        property_limit=None, staff_limit=None):
    """Host operator's reviewed status/billing change. Never delete customer data."""
    if not isinstance(profile, dict) or action not in (
            "activate", "suspend", "reactivate", "cancel", "record_invoice",
            "mark_overdue", "set_plan"):
        raise ValueError("unsupported operator action")
    if not isinstance(reason, str) or not 12 <= len(reason.strip()) <= 500:
        raise ValueError("a written operator reason is required")
    new = copy.deepcopy(profile)
    old = new.get("operational_status")
    if action == "activate" and old == "prepared":
        new["operational_status"] = "active"
        new["subscription_status"] = "manual-trial"
    elif action == "suspend" and old == "active":
        new["operational_status"] = "suspended"
    elif action == "reactivate" and old == "suspended":
        new["operational_status"] = "active"
    elif action == "cancel" and old in {"active", "suspended", "prepared"}:
        new["operational_status"] = "cancelled"
        new["subscription_status"] = "manual-cancelled"
    elif action == "record_invoice" and old == "active":
        if not isinstance(evidence, str) or not 8 <= len(evidence.strip()) <= 160:
            raise ValueError("invoice reference must be verified by the operator")
        new["subscription_status"] = "manual-invoice-recorded"
        new["last_invoice_reference"] = evidence.strip()
    elif action == "mark_overdue" and old == "active":
        new["subscription_status"] = "manual-overdue"
    elif action == "set_plan" and old in {"prepared", "active", "suspended"}:
        if plan not in PLANS or type(property_limit) is not int or not 0 <= property_limit <= 100000:
            raise ValueError("invalid plan or property limit")
        if type(staff_limit) is not int or not 0 <= staff_limit <= 1000:
            raise ValueError("invalid staff limit")
        new.update(plan=plan, property_limit=property_limit, staff_limit=staff_limit)
    else:
        raise ValueError("invalid state transition")
    new["version"] = profile["version"] + 1
    new["updated_at"] = utcnow()
    event = {"action": action, "reason": reason.strip(),
             "created_at": new["updated_at"], "previous_status": old,
             "new_status": new["operational_status"]}
    if evidence is not None and action == "record_invoice":
        event["evidence_reference"] = evidence.strip()
    return new, event


def public_brand(profile):
    """Public allowlist. Never include billing, emergency, branch or staff data."""
    return {
        "name": profile["display_name"],
        "brand_colour": profile["brand_colour"],
        "agency_id": profile["agency_id"],
    }
