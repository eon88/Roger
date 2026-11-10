"""Shared, audited state changes for Roger property and tenancy lifecycles.

This engine does not decide legal notices, payments, or possession. Handler
business checks must run BEFORE recording a state change. Client-supplied actor
and timestamps are never accepted.
"""
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
