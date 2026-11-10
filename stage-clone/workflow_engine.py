"""Shared, audited state changes for Roger property and tenancy lifecycles.

This engine does not decide legal notices, payments, or possession. Handler
business checks must run BEFORE recording a state change. Client-supplied actor
and timestamps are never accepted.
"""
import hashlib
import json

PROPERTY_TRANSITIONS = {
    "prospect": ("onboarding", "offboarded"),
    "onboarding": ("ready_to_market", "offboarded"),
    "ready_to_market": ("onboarding", "advertised", "offboarded"),
    "advertised": ("application", "void", "offboarded"),
    "application": ("advertised", "let_agreed", "void"),
    "let_agreed": ("occupied", "void"),
    "occupied": ("notice_given", "offboarded"),
    "notice_given": ("occupied", "checkout"),
    "checkout": ("void",),
    "void": ("remarketing", "offboarded"),
    "remarketing": ("advertised", "onboarding", "offboarded"),
    "offboarded": (),
}
TENANCY_TRANSITIONS = {
    "application": ("referencing", "cancelled"),
    "referencing": ("approved", "cancelled"),
    "approved": ("offer", "cancelled"),
    "offer": ("agreement", "cancelled"),
    "agreement": ("deposit", "cancelled"),
    "deposit": ("move_in_scheduled", "cancelled"),
    "move_in_scheduled": ("active", "cancelled"),
    "active": ("renewal", "notice_given"),
    "renewal": ("active", "notice_given"),
    "notice_given": ("active", "checkout"),
    "checkout": ("deposit_resolution", "former_tenant"),
    "deposit_resolution": ("former_tenant",),
    "former_tenant": (),
    "cancelled": (),
}
GRAPHS = {"property": PROPERTY_TRANSITIONS, "tenancy": TENANCY_TRANSITIONS}


class InvalidTransition(ValueError):
    pass


class RequestReplayConflict(ValueError):
    pass


def validate_transition(kind, previous, target):
    graph = GRAPHS.get(kind)
    if graph is None or target not in graph:
        raise InvalidTransition("unknown " + str(kind) + " lifecycle status")
    if previous == target:
        return False
    if previous not in graph or target not in graph[previous]:
        raise InvalidTransition("invalid " + kind + " lifecycle transition")
    return True


def _request_id(value):
    if value is None or value == "":
        return None
    if not isinstance(value,str) or len(value) > 100 or len(value) < 8:
        raise InvalidTransition("request ID must be an 8-100 character string")
    return value


def guard_replay(record, history_field, request_id, target):
    token = _request_id(request_id)
    if token is None:
        return False
    for item in record.get(history_field, []):
        if item.get("request_id") == token:
            if item.get("to") != target:
                raise RequestReplayConflict("request ID already used for another transition")
            return True
    return False


def apply_transition(record, *, kind, target, actor, at,
                     history_field="history", state_field="status",
                     request_id=None, reason=None, effective_date=None):
    """Mutate record once, after permission/legal checks by its own handler.

    Returns True for a new change, False for unchanged/replayed. The event is
    stored with the record and is committed with the enclosing stage snapshot.
    """
    if not isinstance(record,dict):
        raise InvalidTransition("transition needs a record")
    if not isinstance(actor,str) or not actor.strip():
        raise InvalidTransition("transition actor must be authenticated")
    if not isinstance(at,str) or not at:
        raise InvalidTransition("transition must use a server timestamp")
    if reason is not None and (not isinstance(reason,str) or len(reason)>500):
        raise InvalidTransition("transition reason must be text, max 500 characters")
    current=record.get(state_field)
    token=_request_id(request_id)
    if guard_replay(record,history_field,token,target):
        return False
    if not validate_transition(kind,current,target):
        return False
    event={"from":current,"to":target,"at":at,"by":actor}
    if token is not None:
        event["request_id"]=token
    if reason:
        event["reason"]=reason.strip()
    if effective_date:
        event["effective_date"]=effective_date
    record[state_field]=target
    record.setdefault(history_field,[]).append(event)
    return True



def _action_fingerprint(payload):
    """Hash the JSON request, excluding the retry token itself."""
    if not isinstance(payload, dict):
        raise InvalidTransition("workflow request must be an object")
    try:
        packed = json.dumps(
            {key: value for key, value in payload.items() if key != "request_id"},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
    except (TypeError, ValueError) as exc:
        raise InvalidTransition("workflow request must be JSON-compatible") from exc
    return hashlib.sha256(packed.encode("utf-8")).hexdigest()


def check_action_replay(record, *, request_id, action, actor, payload):
    """Check idempotency for sensitive case/job/approval/financial actions.

    The caller must verify the server-authenticated actor's permission to see
    and operate this record BEFORE calling this function. Returning True means
    this exact actor's identical request has already committed; do not repeat
    financial adjustments, approvals, messages, or other side effects.
    """
    token = _request_id(request_id)
    if token is None:
        return False
    fingerprint = _action_fingerprint(payload)
    for item in record.get("workflow_requests", []):
        if item.get("request_id") == token:
            if (item.get("action") != action or item.get("by") != actor
                    or item.get("payload_sha256") != fingerprint):
                raise RequestReplayConflict("request ID already used with a different action, actor or payload")
            return True
    return False


def remember_action_request(record, *, request_id, action, actor, role, at, payload):
    """Record a successfully applied action in the same snapshot transaction."""
    token = _request_id(request_id)
    if token is None:
        return False
    if not isinstance(record, dict) or not isinstance(actor, str) or not actor:
        raise InvalidTransition("authenticated actor and record are required")
    if role not in ("agent", "tenant", "landlord", "trades", "system"):
        raise InvalidTransition("invalid actor role")
    if not isinstance(at, str) or not at:
        raise InvalidTransition("server timestamp required")
    if check_action_replay(record, request_id=token, action=action, actor=actor, payload=payload):
        raise RequestReplayConflict("cannot record the same action twice")
    record.setdefault("workflow_requests", []).append({
        "request_id": token, "action": action, "by": actor,
        "role": role, "at": at, "payload_sha256": _action_fingerprint(payload),
    })
    return True


# A shared, defensive contract for repair/job/approval status transitions.
# Handler-level evidence checks (contractor credential, quote authority, bank
# reference, ownership) remain mandatory and run before commit. This layer
# prevents handler branches from silently skipping the recorded workflow.
JOB_ACTION_ROLES = {
    "accept": frozenset({"trades"}), "start": frozenset({"trades"}),
    "complete": frozenset({"trades"}), "release": frozenset({"trades"}),
    "submit_quote": frozenset({"trades"}),
    "submit_variation": frozenset({"trades"}),
    "assign": frozenset({"agent"}), "request_quote": frozenset({"agent"}),
    "approve_quote": frozenset({"agent"}), "decline_quote": frozenset({"agent"}),
    "verify_approve": frozenset({"agent"}), "verify_decline": frozenset({"agent"}),
    "approve_variation": frozenset({"agent"}),
    "decline_variation": frozenset({"agent"}),
    "send_to_landlord": frozenset({"agent"}),
    "approve_invoice": frozenset({"agent"}),
    "record_payment": frozenset({"agent"}),
    "record_credit": frozenset({"agent"}),
}
# Each entry: permitted starting states and permitted destination states.
# No-op actions deliberately require the status to remain unchanged.
JOB_ACTION_STATES = {
    "accept": ({"open"}, {"in_progress", "pending_verification"}),
    "verify_approve": ({"pending_verification"}, {"in_progress"}),
    "verify_decline": ({"pending_verification"}, {"open"}),
    "release": ({"in_progress", "assigned", "quote_requested"}, {"triaged", "open"}),
    "assign": ({"open", "quote_requested", "quoted", "pending_verification"}, {"assigned"}),
    "request_quote": ({"triaged", "open", "assigned"}, {"quote_requested"}),
    "submit_quote": ({"quote_requested"}, {"quoted"}),
    "approve_quote": ({"quoted"}, {"assigned", "in_progress", "awaiting_prework_approval"}),
    "decline_quote": ({"quoted"}, {"quote_requested"}),
    "submit_variation": ({"assigned", "in_progress"}, {"assigned", "in_progress"}),
    "approve_variation": ({"assigned", "in_progress"}, {"assigned", "in_progress"}),
    "decline_variation": ({"assigned", "in_progress"}, {"assigned", "in_progress"}),
    "send_to_landlord": ({"invoice_submitted", "invoice_approved"}, {"awaiting_approval"}),
    "start": ({"assigned"}, {"in_progress"}),
    "complete": ({"in_progress"}, {"invoice_submitted", "awaiting_approval"}),
    "approve_invoice": ({"invoice_submitted"}, {"invoice_approved"}),
    "record_payment": ({"invoice_approved", "partially_paid"}, {"partially_paid", "paid"}),
    "record_credit": ({"invoice_approved", "partially_paid"}, {"partially_paid", "paid", "credited"}),
}
APPROVAL_STATES = {
    "approve": ("pending", "approved"),
    "reject": ("pending", "rejected"),
}
LANDLORD_JOB_STATES = {
    "prework_quote": {
        "approve": ("awaiting_prework_approval", "assigned"),
        "reject": ("awaiting_prework_approval", "quote_requested"),
    },
    "variation_quote": {
        "approve": ("assigned", "assigned"),
        "reject": ("assigned", "assigned"),
    },
    "invoice": {
        "approve": ("awaiting_approval", "invoice_approved"),
        "reject": ("awaiting_approval", "rejected"),
    },
}


def validate_domain_action(kind, *, action, previous, target, role,
                           approval_type=None):
    """Check that a committed change is an allowed action/role/status move.

    Server's authenticated role, NOT the request body, supplies role. Call after
    the detailed business checks but before save_stage() while holding the lock.
    Unknown action/status fails closed; existing unversioned data can be read
    but cannot create an invalid new transition.
    """
    if kind == "job":
        if action not in JOB_ACTION_ROLES or role not in JOB_ACTION_ROLES[action]:
            raise InvalidTransition("job action is not permitted for this role")
        start, ends = JOB_ACTION_STATES[action]
        if previous not in start or target not in ends:
            raise InvalidTransition("invalid job action transition")
    elif kind == "approval":
        if action not in APPROVAL_STATES or role not in {"agent", "landlord"}:
            raise InvalidTransition("approval action is not permitted")
        start, end = APPROVAL_STATES[action]
        if previous != start or target != end:
            raise InvalidTransition("invalid approval action transition")
        if approval_type in {"prework_quote", "variation_quote"} and role != "landlord":
            raise InvalidTransition("landlord approval required")
    elif kind == "landlord_job":
        category = approval_type if approval_type in ("prework_quote", "variation_quote") else "invoice"
        pair = LANDLORD_JOB_STATES.get(category, {}).get(action)
        if pair is None or previous != pair[0] or target != pair[1]:
            # Variations also apply to jobs already in progress.
            if not (category == "variation_quote" and action in ("approve", "reject")
                    and previous == target == "in_progress"):
                raise InvalidTransition("approval does not match current job state")
        if category in ("prework_quote", "variation_quote") and role != "landlord":
            raise InvalidTransition("landlord approval required")
    else:
        raise InvalidTransition("unknown workflow domain")
    return True


def record_status_change(record, previous, *, action, actor, at, role):
    """One shared event shape for case, job, invoice-status and approval moves.

    The existing domain handler is responsible for validating the requested
    action, role, monetary authority, evidence and contractor eligibility.
    This only records a successful state change, never authorises one.
    """
    current=record.get("status")
    if current==previous:
        return False
    if not isinstance(actor,str) or not actor:
        raise InvalidTransition("A named authenticated actor is needed")
    if not isinstance(action,str) or not action or len(action)>100:
        raise InvalidTransition("Unknown action for workflow history")
    if role not in ("agent","tenant","landlord","trades","system"):
        raise InvalidTransition("Unknown actor role for workflow history")
    if not isinstance(at,str) or not at:
        raise InvalidTransition("Workflow event needs a server time")
    record.setdefault("workflow_history",[]).append({
        "from":previous,"to":current,"action":action,"at":at,
        "by":actor,"role":role,
    })
    return True
