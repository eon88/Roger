"""Structured, append-only property inventory and condition record management.

This is not an e-signature or professional independent inventory service.
All amendments to a signed-off inventory require a *new inventory*.
"""
from datetime import date


TYPES = {"check_in", "mid_term", "check_out"}
STATUSES = {"draft", "issued", "acknowledged", "disputed"}


def clean_text(value, limit, field, required=False):
    if not isinstance(value, str):
        raise ValueError(field + " must be text")
    value = " ".join(value.split()).strip()
    if len(value) > limit or (required and not value):
        raise ValueError("Invalid " + field)
    return value


def valid_date(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("inspection_date must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("inspection_date is not a real date") from None
    if parsed.isoformat() != value:
        raise ValueError("inspection_date must be YYYY-MM-DD")
    return value


def create_inventory(data, tenancy, created_at, actor, sequence):
    kind = data.get("kind")
    if kind not in TYPES:
        raise ValueError("Inspection must be check_in, mid_term or check_out")
    description = clean_text(data.get("summary", ""), 1000, "summary")
    return {
        "id": "inventory-" + str(sequence),
        "model_version": 1,
        "property_id": tenancy["property_id"],
        "tenancy_id": tenancy["id"],
        "kind": kind,
        "inspection_date": valid_date(data.get("inspection_date")),
        "summary": description,
        "status": "draft",
        "rooms": [],
        "meter_readings": {},
        "keys": [],
        "created_at": created_at,
        "created_by": actor,
        "revisions": [],
        "tenant_feedback": [],
        "issued_at": None,
    }


def validate_document_links(stage, document_ids, property_id, tenancy_id):
    if not isinstance(document_ids, list) or len(document_ids) > 12:
        raise ValueError("Use at most 12 linked evidence documents")
    if len(document_ids) != len(set(str(x) for x in document_ids)):
        raise ValueError("Duplicate linked document")
    selected=[]
    for doc_id in document_ids:
        if not isinstance(doc_id,str) or not doc_id or len(doc_id)>100:
            raise ValueError("Invalid document reference")
        doc=next((d for d in stage.get("documents", []) if d.get("id")==doc_id),None)
        if not doc:
            raise ValueError("Evidence document not found: " + doc_id[:40])
        if doc.get("property_id") != property_id:
            raise ValueError("Document is not linked to the inspection property")
        if doc.get("tenancy_id") not in (None, "", tenancy_id):
            raise ValueError("Document is linked to another tenancy")
        if doc.get("status") in ("rejected", "superseded", "deleted"):
            raise ValueError("Rejected or superseded evidence cannot be attached")
        selected.append(doc_id)
    return selected


def add_room(stage, inventory, data, at, actor):
    if inventory["status"] != "draft":
        raise ValueError("Issued inventory is immutable; create a new inventory")
    if len(inventory.get("rooms", [])) >= 50:
        raise ValueError("Inventory has reached its 50-room limit")
    label=clean_text(data.get("room"),100,"room",required=True)
    condition=clean_text(data.get("condition"),1000,"condition",required=True)
    evidence=validate_document_links(
        stage, data.get("document_ids", []),
        inventory["property_id"], inventory["tenancy_id"])
    room={
        "id": "room-" + str(len(inventory.get("rooms", []))+1),
        "name": label, "condition": condition,
        "document_ids": evidence,
        "recorded_at": at, "recorded_by": actor,
    }
    inventory.setdefault("rooms",[]).append(room)
    inventory.setdefault("revisions",[]).append({
        "event":"room_recorded","room_id":room["id"],"at":at,"by":actor})
    return room


def add_meter(inventory, data, at, actor):
    if inventory["status"] != "draft":
        raise ValueError("Issued inventory is immutable")
    kind=data.get("meter")
    if kind not in ("gas","electricity","water","heat","other"):
        raise ValueError("Unsupported meter type")
    reading=clean_text(data.get("reading"),80,"meter reading",required=True)
    serial=clean_text(data.get("serial",""),90,"meter serial")
    previous=inventory.setdefault("meter_readings",{}).get(kind)
    inventory["meter_readings"][kind]={"reading":reading,"serial":serial}
    inventory.setdefault("revisions",[]).append({
        "event":"meter_recorded","meter":kind,"previous":previous,
        "at":at,"by":actor})


def add_keys(inventory, data, at, actor):
    if inventory["status"] != "draft":
        raise ValueError("Issued inventory is immutable")
    description=clean_text(data.get("description"),160,"key description",required=True)
    count=data.get("count")
    if not isinstance(count,int) or isinstance(count,bool) or not 0<=count<=100:
        raise ValueError("Key count must be 0-100")
    inventory.setdefault("keys",[]).append({"description":description,"count":count,
                                            "recorded_at":at,"recorded_by":actor})


def issue(inventory, at, actor):
    if inventory["status"] != "draft":
        raise ValueError("Inventory has already been issued")
    if not inventory.get("rooms"):
        raise ValueError("Record at least one room before issuing an inventory")
    inventory["status"]="issued"
    inventory["issued_at"]=at
    inventory["issued_by"]=actor
    inventory.setdefault("revisions",[]).append({"event":"issued","at":at,"by":actor})


def tenant_respond(inventory, actor_id, comment, accepted, at):
    if inventory["status"] not in ("issued","acknowledged","disputed"):
        raise ValueError("Only issued inventories can receive tenant responses")
    if not isinstance(accepted,bool):
        raise ValueError("accepted must be true or false")
    note=clean_text(comment,1000,"tenant comment")
    if not accepted and len(note)<5:
        raise ValueError("Please explain what you disagree with")
    previous=next((x for x in inventory.get("tenant_feedback",[])
                   if x.get("account_id")==actor_id), None)
    if previous:
        raise ValueError("One acknowledgement per tenant account; contact agent for corrections")
    feedback={"account_id":actor_id,"accepted":accepted,"comment":note,"at":at}
    inventory.setdefault("tenant_feedback",[]).append(feedback)
    if not accepted:
        inventory["status"]="disputed"
    elif inventory["status"]!="disputed":
        inventory["status"]="acknowledged"
    return feedback


def scoped_inventory(inventory, role, documents):
    """Hide internal/private evidence identifiers, actor identity and revisions."""
    copy={k: inventory.get(k) for k in (
        "id","property_id","tenancy_id","kind","inspection_date",
        "summary","status","rooms","meter_readings","keys","issued_at")}
    if role=="agent":
        return inventory
    if inventory.get("status")=="draft":
        return None
    allowed=set(d.get("id") for d in documents
                if d.get("status")=="verified"
                and role in (d.get("access_roles") or [])
                and d.get("property_id")==inventory.get("property_id"))
    copy["rooms"]=[{
        "name":r.get("name"),"condition":r.get("condition"),
        "document_ids":[x for x in r.get("document_ids",[]) if x in allowed],
    } for r in inventory.get("rooms",[])]
    copy["tenant_feedback"]=[{"accepted":f.get("accepted"),
                              "comment":f.get("comment"),"at":f.get("at")}
                             for f in inventory.get("tenant_feedback",[])]
    return copy
