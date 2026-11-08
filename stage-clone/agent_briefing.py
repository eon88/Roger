"""Read-only, deterministic Agent Desk operational briefing.

All cards are evidence-linked to existing stage records. This is a rules engine,
NOT an LLM result, risk certification, accounting reconciliation or emergency
response system. Agents decide actions; this module never changes stage.
"""
from datetime import date, datetime, timedelta
import prs_register


CLOSED_CASES = {"closed", "resolved", "cancelled"}
CLOSED_TASKS = {"completed", "cancelled", "done"}
PRIORITY = {"urgent": 0, "high": 1, "normal": 2, "low": 3}


def _day(value):
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _short(value, max_len=130):
    return str(value or "").strip()[:max_len]


def _add(entries, category, record, title, detail, priority, view, reason, due=None):
    identifier = _short(record.get("id"), 80)
    if not identifier:
        return
    entries.append({
        "key": category + ":" + identifier,
        "category": category,
        "record_id": identifier,
        "property_id": _short(record.get("property_id"), 100) or None,
        "title": _short(title, 150),
        "detail": _short(detail, 200),
        "priority": priority,
        "view": view,
        "reason": _short(reason, 160),
        "due_date": due.isoformat() if isinstance(due, date) else None,
    })


def make_briefing(stage, today=None):
    if not isinstance(stage, dict):
        raise ValueError("Expected a stage object")
    today = today if isinstance(today, date) else date.today()
    cards = []
    horizon = today + timedelta(days=30)

    # Each active case appears once: the highest applicable reason wins.
    for case in stage.get("cases", []):
        if not isinstance(case, dict) or case.get("status") in CLOSED_CASES:
            continue
        number = case.get("id")
        triage = case.get("triage") or {}
        dossier = case.get("diagnostic_dossier") or {}
        flags = (triage.get("safety_flags") or []) + (dossier.get("safety_flags") or [])
        urgency = triage.get("urgency")
        emergency = bool(flags) or isinstance(urgency, (int, float)) and urgency >= 2
        due = _day(case.get("next_due_at"))
        actor = _short(case.get("next_actor"), 50)
        reason = _short(case.get("next_action"), 150) or "Review the case and set a next step"
        record_title = "Repair case #" + str(number)
        if emergency:
            _add(cards, "case", case, record_title + " — possible danger",
                 "Urgent human review required; not an emergency response service",
                 "urgent", "cases", "Rule/model indicates possible safety risk", due)
        elif due and due < today:
            _add(cards, "case", case, record_title + " — overdue",
                 actor + ": " + reason, "high", "cases",
                 "Case's internal next-action date has passed", due)
        elif actor == "agent" or not actor:
            _add(cards, "case", case, record_title + " — agent review",
                 reason, "normal", "cases",
                 "Agent is the recorded next actor or no next actor is set", due)

    for task in stage.get("tasks", []):
        if not isinstance(task, dict) or task.get("status") in CLOSED_TASKS:
            continue
        due = _day(task.get("due_date"))
        priority = task.get("priority")
        if due and due < today:
            p, reason = "high", "Task due date has passed"
        elif priority == "urgent":
            p, reason = "high", "Task marked urgent by agent"
        elif due and due <= today:
            p, reason = "normal", "Task due today"
        elif due and due <= horizon:
            p, reason = "low", "Task due within 30 days"
        else:
            continue
        _add(cards, "task", task, "Task — " + _short(task.get("title"), 100),
             "Assigned: " + _short(task.get("owner"), 80), p, "tasks", reason, due)

    for approval in stage.get("approvals", []):
        if not isinstance(approval, dict) or approval.get("status") != "pending":
            continue
        _add(cards, "approval", approval, "Approval waiting — " + str(approval.get("id")),
             "Check approval type, owner authority and the exact quote version",
             "normal", "jobs", "Pending landlord/agent approval; do not bypass")

    for record in stage.get("compliance_records", []):
        if not isinstance(record, dict) or record.get("superseded_by"):
            continue
        expiry = _day(record.get("expiry_date"))
        reminder = _day(record.get("reminder_date"))
        name = _short(record.get("requirement_type"), 90).replace("_", " ")
        if record.get("record_status") == "missing":
            _add(cards, "compliance", record, name + " — missing record",
                 "Review required evidence and jurisdiction rules",
                 "high", "compliance", "Record explicitly marked missing")
        elif expiry and expiry < today:
            _add(cards, "compliance", record, name + " — expired",
                 "The tracked document's expiry date has passed",
                 "high", "compliance", "Recorded expiry date", expiry)
        elif expiry and expiry <= horizon:
            _add(cards, "compliance", record, name + " — expires soon",
                 "Review renewal date and recorded evidence",
                 "normal", "compliance", "Recorded expiry within 30 days", expiry)
        elif reminder and reminder <= today:
            _add(cards, "compliance", record, name + " — reminder due",
                 "Review renewal even if no expiry has been recorded",
                 "normal", "compliance", "Recorded reminder date", reminder)

    # Government registration rollout applies to occupied England properties;
    # this is a reminder, not a statement that a property violates any law.
    for prop in stage.get("properties", []):
        if not isinstance(prop, dict):
            continue
        candidate = prs_register.due_for_review(prop, today)
        if not candidate:
            continue
        priority, detail, deadline = candidate
        _add(cards, "prs-registration", prop,
             "PRS landlord registration — " + _short(prop.get("title"), 100),
             detail, priority, "compliance",
             "Agent-supplied region/evidence; verify council and government record",
             deadline)

    for reg in stage.get("registrations", []):
        if not isinstance(reg, dict) or reg.get("role") != "trades":
            continue
        if reg.get("status") == "pending":
            _add(cards, "trades", reg,
                 "Contractor registration pending — " + _short(reg.get("name")),
                 "Review submitted evidence and verification status",
                 "normal", "registrations", "Contractor application awaiting review")
            continue
        if reg.get("status") != "approved":
            continue
        verification = reg.get("contractor_verification") or {}
        expiry = _day(verification.get("valid_until"))
        if expiry and expiry < today:
            _add(cards, "trades", reg, "Contractor verification expired",
                 _short(reg.get("name")) + " — new regulated assignments require current proof",
                 "high", "registrations", "Verification review date has passed", expiry)
        elif expiry and expiry <= horizon:
            _add(cards, "trades", reg, "Contractor verification due",
                 _short(reg.get("name")) + " — renew verified records",
                 "normal", "registrations", "Verification expires within 30 days", expiry)

    for tenancy in stage.get("tenancies", []):
        if not isinstance(tenancy, dict):
            continue
        if tenancy.get("status") not in ("active", "renewal", "notice_given"):
            continue
        end = _day(tenancy.get("end_date"))
        if end and end <= horizon:
            _add(cards, "tenancy", tenancy, "Tenancy term review",
                 "Review the record and applicable tenancy rules; do not assume automatic termination",
                 "high" if end < today else "normal", "people",
                 "Recorded end date is due/past; human review needed", end)

    cards.sort(key=lambda c: (
        PRIORITY.get(c["priority"], 10),
        c["due_date"] or "9999-12-31", c["category"], c["record_id"],
    ))
    counts = {key: sum(x["priority"] == key for x in cards)
              for key in ("urgent", "high", "normal", "low")}
    return {
        "as_of": today.isoformat(),
        "engine": "deterministic-rules",
        "read_only": True,
        "total_actions": len(cards),
        "priority_counts": counts,
        "cards": cards[:100],
        "truncated": len(cards) > 100,
        "limitations": (
            "Only recorded data is reviewed. Missing records may hide work. "
            "These internal priorities are not professional safety, legal or accounting judgments."
        ),
    }
