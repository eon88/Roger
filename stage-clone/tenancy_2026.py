"""England assured-periodic tenancy workflow constraints from 1 May 2026.

This module does not issue notices, decide possession claims or certify compliance.
It records agent-reviewed actions and tenant requests, preserving audit history.
"""
from datetime import date
import calendar
from fractions import Fraction


def parse_date(value, field):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError(field + " must use YYYY-MM-DD")
    try:
        result = date.fromisoformat(value)
    except ValueError:
        raise ValueError(field + " must be a real calendar date") from None
    if result.isoformat() != value:
        raise ValueError(field + " must use YYYY-MM-DD")
    return result


def add_months(day, months):
    index = day.year * 12 + (day.month - 1) + months
    year, month_zero = divmod(index, 12)
    month = month_zero + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def assured_periodic_terms(start_date, rent_frequency, rent_pence, deposit_pence):
    start = parse_date(start_date, "start_date")
    if rent_frequency not in ("weekly", "fortnightly", "monthly"):
        raise ValueError("New England assured periodic tenancies use rent periods of at most one month")
    if isinstance(rent_pence, bool) or isinstance(deposit_pence, bool):
        raise ValueError("Rent and deposit must be integer pence")
    if not isinstance(rent_pence, int) or not isinstance(deposit_pence, int):
        raise ValueError("Rent and deposit must be integer pence")
    if rent_pence <= 0 or deposit_pence < 0:
        raise ValueError("Rent must be positive and deposit cannot be negative")
    yearly = {
        "weekly": Fraction(rent_pence * 52),
        "fortnightly": Fraction(rent_pence * 26),
        "monthly": Fraction(rent_pence * 12),
    }[rent_frequency]
    weeks = 6 if yearly >= 5000000 else 5
    limit = yearly * weeks / 52
    if deposit_pence > limit:
        raise ValueError("Tenancy deposit exceeds the standard " + str(weeks)
                         + "-week Tenant Fees Act cap; check any statutory exemption separately")
    return {
        "tenancy_type": "assured_periodic",
        "legal_jurisdiction": "england",
        "periodic_from": "2026-05-01" if start < date(2026, 5, 1) else start.isoformat(),
        "fixed_term_end_date": None,
        "rental_period": rent_frequency,
        "tenancy_rules_effective_from": "2026-05-01",
        "deposit_limit_pence": limit.numerator // limit.denominator,
    }


def rent_increase_proposal(tenancy, amount_pence, notice_served_on, effective_on, today=None):
    """Validate an *unserved draft* form 4A record; agent must serve offline."""
    today = today or date.today()
    if tenancy.get("tenancy_type") != "assured_periodic":
        raise ValueError("This workflow only handles assured periodic tenancies")
    if tenancy.get("status") not in ("active", "notice_given"):
        raise ValueError("An active tenancy is required")
    if not isinstance(amount_pence, int) or isinstance(amount_pence, bool) or amount_pence <= 0:
        raise ValueError("New rent must be positive integer pence")
    if amount_pence <= int(tenancy.get("rent_amount_pence") or 0):
        raise ValueError("This workflow handles increases only")
    notice = parse_date(notice_served_on, "notice_served_on")
    effective = parse_date(effective_on, "effective_on")
    start = parse_date(tenancy["start_date"], "start_date")
    if notice > today:
        raise ValueError("Do not record a future date as already served")
    if effective < add_months(notice, 2):
        raise ValueError("A full two-month notice period must elapse")
    if effective < add_months(start, 12):
        raise ValueError("Rent cannot increase in the first 12 months")
    last = tenancy.get("last_rent_increase_effective_at")
    if last and effective < add_months(parse_date(last, "last_rent_increase_effective_at"), 12):
        raise ValueError("Rent increases must be at least 12 months apart")
    if tenancy.get("pending_rent_increase"):
        raise ValueError("Resolve the previous proposed rent increase before creating another")
    return {
        "notice_form": "Form 4A (Section 13)",
        "notice_served_on": notice.isoformat(),
        "effective_on": effective.isoformat(),
        "proposed_rent_pence": amount_pence,
        "status": "awaiting_agent_confirmation",
        "actual_service_verified": False,
        "tenant_objection_status": "not_recorded",
    }


def confirm_rent_increase(tenancy, effective_today=None):
    effective_today = effective_today or date.today()
    proposed = tenancy.get("pending_rent_increase")
    if not isinstance(proposed, dict):
        raise ValueError("No proposed rent increase exists")
    if proposed.get("status") != "awaiting_agent_confirmation":
        raise ValueError("Rent increase is not pending")
    if parse_date(proposed["effective_on"], "effective_on") > effective_today:
        raise ValueError("Cannot make rent increase effective before the recorded date")
    if proposed.get("tenant_objection_status") == "disputed":
        raise ValueError("Resolve the disputed rent increase outside this workflow")
    return int(proposed["proposed_rent_pence"]), proposed["effective_on"]


def pet_request(pet_description, submitted_at):
    if not isinstance(pet_description, str):
        raise ValueError("Describe the animal in text")
    description = " ".join(pet_description.split()).strip()
    if not 2 <= len(description) <= 500:
        raise ValueError("Describe the requested pet in 2 to 500 characters")
    return {"description": description, "status": "pending_agent_review",
            "submitted_at": submitted_at, "decision": None}


def pet_decision(record, decision, reason, at):
    if record.get("status") != "pending_agent_review":
        raise ValueError("Pet request was already decided")
    if decision not in ("approved", "refused", "request_information"):
        raise ValueError("Invalid pet decision")
    if not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 1000:
        raise ValueError("A written human reason is required")
    return {"status": decision, "decision": decision,
            "reason": reason.strip(), "decided_at": at}
