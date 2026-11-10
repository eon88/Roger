"""Roger B01 canonical record identities, links, versioned opt-in and safe upgrades.

Never merge individuals using names/emails. Legacy records are inspected but
not silently rewritten; new v1-tagged records must satisfy strict relationships.
This module makes no database writes and is safe to run on backup copies.
"""
import copy
from datetime import date, timedelta

MODEL_VERSION = 1
ENTITY_COLLECTIONS = (
    "properties", "property_units", "ownership_interests", "parties",
    "tenancies", "cases", "jobs", "documents", "inventories",
    "deposit_records", "rent_ledger_entries", "landlord_statements",
    "registrations", "approvals", "appointments",
    "management_agreements", "tasks", "compliance_records",
    "property_submissions", "invitations",
)
# Accepted property/tenancy state maps remain in the server workflow engine.
PROPERTY_STATES = {
    "prospect", "onboarding", "ready_to_market", "advertised",
    "application", "let_agreed", "occupied", "notice_given",
    "checkout", "void", "remarketing", "offboarded",
}
TENANCY_STATES = {
    "application", "referencing", "approved", "offer", "agreement",
    "deposit", "move_in_scheduled", "active", "renewal",
    "notice_given", "checkout", "deposit_resolution",
    "former_tenant", "cancelled",
}

# Optional links must point to exactly one entity of the specified collection.
# Legacy rows can contain free-text, missing or unlinked values; those are
# *reported*, and audited correction happens in B01/B04, never guessed here.
REFS = {
    "property_units": {"property_id": "properties"},
    "ownership_interests": {"property_id": "properties",
                            "landlord_party_id": "parties"},
    "tenancies": {"property_id": "properties",
                  "unit_id": "property_units"},
    "cases": {"property_id": "properties"},
    "jobs": {"property_id": "properties", "case_id": "cases"},
    "documents": {"property_id": "properties", "tenancy_id": "tenancies",
                  "case_id": "cases", "job_id": "jobs", "party_id": "parties"},
    "inventories": {"property_id": "properties", "tenancy_id": "tenancies"},
    "deposit_records": {"property_id": "properties", "tenancy_id": "tenancies"},
    "rent_ledger_entries": {"property_id": "properties", "tenancy_id": "tenancies"},
    "management_agreements": {"landlord_party_id": "parties"},
}


class RecordIntegrityError(ValueError):
    """A record is unsafe or inconsistent; never persist its modification."""


def _key(identifier):
    if isinstance(identifier, bool) or not isinstance(identifier, (str, int)):
        return None
    if isinstance(identifier, str) and (not identifier.strip() or len(identifier) > 128):
        return None
    return str(identifier)


def _day(value, field):
    if not isinstance(value, str) or len(value) != 10:
        raise RecordIntegrityError(field + " must be a YYYY-MM-DD date")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise RecordIntegrityError(field + " is not a real date") from None
    return value


def entity_indexes(snapshot):
    indexes = {}
    for name in ENTITY_COLLECTIONS:
        collection = snapshot.get(name, [])
        if not isinstance(collection, list):
            raise RecordIntegrityError(name + " collection must be a list")
        seen = {}
        for offset, record in enumerate(collection):
            if not isinstance(record, dict):
                raise RecordIntegrityError(name + " has a malformed row")
            identity = record.get("id")
            if identity is None:
                # Some historic prospect/compliance records have no ID. An
                # ID is mandatory on v1 records but legacy migration is manual.
                if record.get("model_version") == MODEL_VERSION:
                    raise RecordIntegrityError(name + " v1 row is missing an ID")
                continue
            key = _key(identity)
            if key is None:
                raise RecordIntegrityError(name + " has an invalid record ID")
            if key in seen:
                raise RecordIntegrityError(name + " contains duplicate ID " + key)
            seen[key] = record
        indexes[name] = seen
    return indexes


def _strict_record(snapshot, record):
    return record.get("model_version") == MODEL_VERSION


def inspect(snapshot):
    """Return deterministic, non-mutating legacy warnings and identity counts."""
    if not isinstance(snapshot, dict):
        raise RecordIntegrityError("stage must be an object")
    indexes = entity_indexes(snapshot)
    warnings = []
    for collection, refs in REFS.items():
        for record in snapshot.get(collection, []):
            for field, target in refs.items():
                key = _key(record.get(field))
                if key is None:
                    continue
                if key not in indexes[target]:
                    warnings.append({
                        "collection": collection, "id": str(record.get("id", "")),
                        "field": field, "issue": "missing_related_" + target,
                    })
    # Legacy links are diagnostic, never silently rewritten. A matching ID can
    # still refer to the wrong property or tenant; existence checks alone miss it.
    property_links = {
        "tenancies": (("unit_id", "property_units"),),
        "jobs": (("case_id", "cases"),),
        "documents": (("tenancy_id", "tenancies"), ("case_id", "cases"),
                      ("job_id", "jobs")),
        "inventories": (("tenancy_id", "tenancies"),),
        "deposit_records": (("tenancy_id", "tenancies"),),
        "rent_ledger_entries": (("tenancy_id", "tenancies"),),
        "approvals": (("job_id", "jobs"),),
    }
    for collection, fields in property_links.items():
        for record in snapshot.get(collection, []):
            record_property = _key(record.get("property_id"))
            for field, target in fields:
                linked = indexes[target].get(_key(record.get(field)))
                if not linked:
                    continue  # A missing parent has its own warning above.
                parent_property = _key(linked.get("property_id"))
                if record_property and parent_property and record_property != parent_property:
                    warnings.append({
                        "collection": collection, "id": str(record.get("id", "")),
                        "field": field, "issue": "property_mismatch",
                    })
                if (record.get("agency_id") and linked.get("agency_id")
                        and record["agency_id"] != linked["agency_id"]):
                    warnings.append({
                        "collection": collection, "id": str(record.get("id", "")),
                        "field": field, "issue": "foreign_agency_reference",
                    })
    for job in snapshot.get("jobs", []):
        linked_case = indexes["cases"].get(_key(job.get("case_id")))
        if linked_case and job.get("case_id") is not None and job.get("property_id") is None:
            warnings.append({
                "collection": "jobs", "id": str(job.get("id", "")),
                "field": "property_id", "issue": "unclassified_job_property",
            })
    for document in snapshot.get("documents", []):
        linked_job = indexes["jobs"].get(_key(document.get("job_id")))
        linked_case = _key(document.get("case_id"))
        if (linked_job and linked_case
                and _key(linked_job.get("case_id")) != linked_case):
            warnings.append({
                "collection": "documents", "id": str(document.get("id", "")),
                "field": "job_id", "issue": "job_case_mismatch",
            })
    # These exact external keys are stronger evidence than matching names or
    # contact details, but even collisions still require human review.
    for collection in ENTITY_COLLECTIONS:
        source_keys = {}
        for record in snapshot.get(collection, []):
            system = _key(record.get("source_system"))
            identifier = _key(record.get("source_id"))
            if not (system and identifier):
                continue
            pair = (system, identifier)
            if pair in source_keys:
                warnings.append({
                    "collection": collection, "id": str(record.get("id", "")),
                    "field": "source_id", "issue": "duplicate_external_identity",
                })
            else:
                source_keys[pair] = record.get("id")

    return {
        "version": snapshot.get("model_metadata", {}).get("version", 0)
            if isinstance(snapshot.get("model_metadata"), dict) else 0,
        "counts": {name: len(snapshot.get(name, [])) for name in ENTITY_COLLECTIONS},
        "warnings": warnings,
    }


def validate_for_save(snapshot):
    """Fail on duplicate identities or bad new v1 references; tolerate legacy links.

    Every strict record is never allowed to refer to a foreign/unknown entity.
    Existing incomplete records are not silently removed, re-parented or
    marked as verified. A professional migration must reconcile them first.
    """
    result = inspect(snapshot)
    indexes = entity_indexes(snapshot)
    # Historical inconsistencies remain visible to a reviewing agent; new
    # canonical rows cannot introduce those same contradictions.
    strict_issues = {
        "property_mismatch", "foreign_agency_reference",
        "job_case_mismatch", "duplicate_external_identity",
    }
    for warning in result["warnings"]:
        record = indexes[warning["collection"]].get(warning["id"])
        if record and record.get("model_version") == MODEL_VERSION and warning["issue"] in strict_issues:
            raise RecordIntegrityError(
                warning["collection"] + "." + warning["field"] +
                " has " + warning["issue"])
    agency_id = snapshot.get("agency_id")
    for collection in ENTITY_COLLECTIONS:
        for record in snapshot.get(collection, []):
            if not _strict_record(snapshot, record):
                continue
            _validate_strict_record(collection, record, indexes, agency_id)
    _validate_ownership_allocations(snapshot)
    return result


def _validate_ownership_allocations(snapshot):
    """Reject overlapping historical/current joint ownership over-allocation."""
    by_property = {}
    for row in snapshot.get("ownership_interests", []):
        if row.get("model_version") != MODEL_VERSION:
            continue
        pid = _key(row.get("property_id"))
        start = date.fromisoformat(row["effective_from"])
        end = date.fromisoformat(row["effective_to"]) if row.get("effective_to") else None
        by_property.setdefault(pid, []).append((start, end, row["share_basis_points"]))
    for pid, rows in by_property.items():
        checkpoints = {start for start, _, _ in rows}
        for _, end, _ in rows:
            if end and end < date.max:
                checkpoints.add(end + timedelta(days=1))
        for checkpoint in checkpoints:
            share = sum(pct for start, end, pct in rows
                        if start <= checkpoint and (end is None or checkpoint <= end))
            if share > 10000:
                raise RecordIntegrityError(
                    "Joint ownership shares exceed 100% at " +
                    checkpoint.isoformat() + " for " + str(pid))


def _validate_strict_record(collection, record, indexes, agency_id):
    if _key(record.get("id")) is None:
        raise RecordIntegrityError("v1 " + collection + " record needs a real ID")
    if agency_id and record.get("agency_id") not in (None, agency_id):
        raise RecordIntegrityError("foreign agency reference in " + collection)
    for field, parent_collection in REFS.get(collection, {}).items():
        key = _key(record.get(field))
        if key is None:
            if field in ("property_id",) and collection not in ("documents",):
                raise RecordIntegrityError(collection + " must link its property")
            continue
        if key not in indexes[parent_collection]:
            raise RecordIntegrityError(collection + "." + field +
                                       " points to missing " + parent_collection)
    property_id = _key(record.get("property_id"))
    if collection == "tenancies":
        unit_id = _key(record.get("unit_id"))
        if unit_id and _key(indexes["property_units"][unit_id].get("property_id")) != property_id:
            raise RecordIntegrityError("Tenancy unit belongs to another property")
        for role, field in (("tenant", "tenant_party_ids"),
                            ("landlord", "landlord_party_ids")):
            members = record.get(field, [])
            if not isinstance(members, list) or not members or len(members) != len(set(map(str, members))):
                raise RecordIntegrityError("Invalid tenancy " + field)
            for member in members:
                linked = indexes["parties"].get(_key(member))
                if not linked or role not in linked.get("roles", []):
                    raise RecordIntegrityError("Tenancy has unknown or wrong-role Party in " + field)
        if record.get("tenancy_type") == "assured_periodic" and record.get("fixed_term_end_date"):
            raise RecordIntegrityError("Assured periodic tenancy cannot contain a fixed end")
    if collection == "ownership_interests":
        linked = indexes["parties"].get(_key(record.get("landlord_party_id")))
        if not linked or "landlord" not in linked.get("roles", []):
            raise RecordIntegrityError("Ownership must be held by a landlord Party")
        share = record.get("share_basis_points")
        if not isinstance(share, int) or isinstance(share, bool) or not 1 <= share <= 10000:
            raise RecordIntegrityError("Ownership share must be 1 to 10000 basis points")
        start = _day(record.get("effective_from"), "effective_from")
        end = record.get("effective_to")
        if end and _day(end, "effective_to") < start:
            raise RecordIntegrityError("Ownership end precedes start")
    if collection == "property_units":
        label = record.get("label")
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 100:
            raise RecordIntegrityError("Unit must have a meaningful label")
    if collection == "inventories":
        tenure = indexes["tenancies"].get(_key(record.get("tenancy_id")))
        if not tenure or _key(tenure.get("property_id")) != property_id:
            raise RecordIntegrityError("Inventory property does not match tenancy")
    if collection == "deposit_records":
        tenure = indexes["tenancies"].get(_key(record.get("tenancy_id")))
        if not tenure or _key(tenure.get("property_id")) != property_id:
            raise RecordIntegrityError("Deposit property does not match tenancy")
    if collection == "documents":
        for collection_name, field in (
            ("tenancies", "tenancy_id"), ("cases", "case_id"), ("jobs", "job_id")
        ):
            linked = indexes[collection_name].get(_key(record.get(field)))
            if linked and property_id and _key(linked.get("property_id")) != property_id:
                raise RecordIntegrityError("Document belongs to unrelated " + collection_name)


def propose_upgrade(snapshot):
    """Copy-only, non-destructive v1 migration plan.

    No passwords, accounts, foreign keys or ownership percentages are guessed.
    Original legacy records are preserved exactly as supplied. For automatic
    rollback, keep the original backup or restore before any actual apply.
    """
    if not isinstance(snapshot, dict):
        raise RecordIntegrityError("stage must be an object")
    report = inspect(snapshot)
    upgraded = copy.deepcopy(snapshot)
    old_metadata = upgraded.get("model_metadata") or {}
    if old_metadata and (not isinstance(old_metadata, dict) or
                         old_metadata.get("version") not in (None, MODEL_VERSION)):
        raise RecordIntegrityError("Unknown future model version; refusing downgrade")
    upgraded.setdefault("property_units", [])
    upgraded.setdefault("ownership_interests", [])
    upgraded["model_metadata"] = {
        "version": MODEL_VERSION,
        "compatibility": "preserve_legacy_without_auto_merging",
    }
    validate_for_save(upgraded)
    return upgraded, report


def new_unit(stage, property_id, identifier, label, agency_id=None):
    row = {
        "id": identifier, "property_id": property_id, "label": label,
        "status": "active", "model_version": MODEL_VERSION,
    }
    if agency_id:
        row["agency_id"] = agency_id
    proposal = copy.deepcopy(stage)
    proposal.setdefault("property_units", []).append(row)
    validate_for_save(proposal)
    return row


def new_ownership(stage, identifier, property_id, landlord_party_id,
                  share_basis_points, effective_from, effective_to=None, agency_id=None):
    row = {
        "id": identifier, "property_id": property_id,
        "landlord_party_id": landlord_party_id,
        "share_basis_points": share_basis_points,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "model_version": MODEL_VERSION,
    }
    if agency_id:
        row["agency_id"] = agency_id
    proposal = copy.deepcopy(stage)
    proposal.setdefault("ownership_interests", []).append(row)
    validate_for_save(proposal)
    # This only verifies simultaneous currently-active ownership allocations.
    now_active = [x for x in proposal.get("ownership_interests", [])
                  if x.get("property_id") == property_id
                  and x.get("model_version") == MODEL_VERSION
                  and x.get("effective_to") is None]
    if sum(x.get("share_basis_points", 0) for x in now_active) > 10000:
        raise RecordIntegrityError("Active joint ownership shares exceed 100%")
    return row


def guard_no_silent_deletion(previous, candidate):
    """Persisted v1 business records cannot disappear or become unarchived.

    This is deliberately limited to version-tagged records: old snapshots may
    include unlinked or obsolete samples that require explicit reconciliation.
    The physical file/document deletion retention policy is not decided here.
    """
    prior=entity_indexes(previous)
    future=entity_indexes(candidate)
    for collection in ENTITY_COLLECTIONS:
        for key,record in prior[collection].items():
            if record.get("model_version") != MODEL_VERSION:
                continue
            replacement=future[collection].get(key)
            if replacement is None:
                raise RecordIntegrityError(
                    "cannot hard-delete canonical "+collection+" record "+key)
            if replacement.get("model_version") != MODEL_VERSION:
                raise RecordIntegrityError(
                    "cannot downgrade versioned record "+collection+" "+key)
            if record.get("archived_at") and not replacement.get("archived_at"):
                raise RecordIntegrityError(
                    "cannot remove historical archive marker from "+collection+" "+key)


def archive_record(stage, collection, identifier, *, actor, at, reason):
    """Record an explicit internal archive without deleting business history."""
    if collection not in ENTITY_COLLECTIONS:
        raise RecordIntegrityError("unsupported archive collection")
    identity=_key(identifier)
    records=entity_indexes(stage)[collection]
    item=records.get(identity)
    if not item or item.get("model_version") != MODEL_VERSION:
        raise RecordIntegrityError("only existing v1 records can use this archive method")
    if item.get("archived_at"):
        raise RecordIntegrityError("record already archived")
    if (not isinstance(actor,str) or not actor.strip() or
            not isinstance(at,str) or not at or
            not isinstance(reason,str) or not 8 <= len(reason.strip()) <= 500):
        raise RecordIntegrityError("archive needs authenticated actor, time and written reason")
    item["archived_at"]=at
    item["archived_by"]=actor
    item["archive_reason"]=reason.strip()
    item.setdefault("workflow_history",[]).append({
        "event":"archived","at":at,"by":actor,"reason":reason.strip()
    })
    return item
