"""B01 reviewed reconciliation for canonical links and invoice shadow records.

This is a copy-only proposal engine, not an automatic deduplicator and not a
migration writer. It leaves all unreviewed historical records intact. B04 uses
the reviewed report during agency import; B26 proves actual backup/restore.
"""
import copy
from datetime import datetime, timezone

import canonical_records as canonical


# One authoritative collection for each concept. A supplier invoice is a
# versioned job financial event; it is NOT a landlord statement or rent receipt.
AUTHORITATIVE = {
    "person": "parties",
    "property": "properties",
    "tenancy": "tenancies",
    "case": "cases",
    "contractor_job": "jobs",
    "supplier_invoice": "jobs",
    "document": "documents",
    "rent_entry": "rent_ledger_entries",
    "deposit": "deposit_records",
}


def reconciliation_report(stage):
    """Non-mutating, deterministic list of anomalies requiring human review."""
    report = canonical.inspect(stage)
    findings = [dict(w) for w in report["warnings"]]
    jobs = stage.get("jobs", [])
    documents = canonical.entity_indexes(stage)["documents"]
    by_supplier_invoice = {}
    for job in jobs:
        jid = str(job.get("id", ""))
        nested = job.get("invoice")
        if isinstance(nested, dict) and job.get("invoice_pence") is not None:
            if nested.get("amount_pence") is not None and (
                    type(nested["amount_pence"]) is not int
                    or nested["amount_pence"] != job.get("invoice_pence")):
                findings.append({
                    "collection": "jobs", "id": jid, "field": "invoice",
                    "issue": "shadow_invoice_amount_conflict"
                })
        supplier = canonical._key(job.get("assigned_to_party_id"))
        number = job.get("invoice_number")
        if supplier and isinstance(number, str) and number.strip():
            key = (supplier, number.strip().upper())
            if key in by_supplier_invoice:
                for duplicate_id in (by_supplier_invoice[key], jid):
                    findings.append({
                        "collection": "jobs", "id": duplicate_id,
                        "field": "invoice_number", "issue": "duplicate_supplier_invoice"
                    })
            else:
                by_supplier_invoice[key] = jid
    for collection in ("jobs", "tenancies", "cases"):
        for record in stage.get(collection, []):
            pointer_ids = record.get("document_ids")
            if pointer_ids is None:
                continue
            if not isinstance(pointer_ids, list):
                findings.append({
                    "collection": collection, "id": str(record.get("id", "")),
                    "field": "document_ids", "issue": "invalid_document_pointer_list"
                })
                continue
            seen = set()
            for document_id in pointer_ids:
                key = canonical._key(document_id)
                issue = ("duplicate_document_pointer" if key in seen else
                         "orphan_document_pointer" if key not in documents else None)
                if issue:
                    findings.append({
                        "collection": collection, "id": str(record.get("id", "")),
                        "field": "document_ids", "issue": issue,
                    })
                seen.add(key)
    # The report does not include names, emails, payment references or bytes.
    findings.sort(key=lambda x: (x["collection"], x["id"], x["field"], x["issue"]))
    return {
        "agency_id": stage.get("agency_id"),
        "authoritative": dict(AUTHORITATIVE),
        "counts": report["counts"],
        "issues": findings,
        "ready_for_canonical_linking": not findings,
    }


def propose_reviewed_link(stage, *, collection, record_id, field,
                          target_id, actor, at, reason):
    """Link one historic record only after an explicitly documented review.

    All source rows, fields other than the approved link, and original evidence
    remain intact. Caller must use the same stage lock and revision check when
    saving the proposed copy. No name/email matching or cross-agency linking.
    """
    if collection not in canonical.REFS or field not in canonical.REFS[collection]:
        raise canonical.RecordIntegrityError("unsupported reviewed relationship")
    if (not isinstance(actor, str) or not actor.strip()
            or not isinstance(reason, str) or not 12 <= len(reason.strip()) <= 500):
        raise canonical.RecordIntegrityError("named reviewer and detailed reason required")
    if not isinstance(at, str):
        raise canonical.RecordIntegrityError("review timestamp required")
    try:
        timestamp = datetime.fromisoformat(at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timezone is required")
    except ValueError as exc:
        raise canonical.RecordIntegrityError("valid timezone-aware review timestamp required") from exc
    proposal = copy.deepcopy(stage)
    indexes = canonical.entity_indexes(proposal)
    original = indexes[collection].get(canonical._key(record_id))
    parent_collection = canonical.REFS[collection][field]
    target = indexes[parent_collection].get(canonical._key(target_id))
    if not original or not target:
        raise canonical.RecordIntegrityError("reviewed subject or parent does not exist")
    agency = stage.get("agency_id")
    if (agency and (original.get("agency_id") not in (None, agency)
                    or target.get("agency_id") not in (None, agency))):
        raise canonical.RecordIntegrityError("reviewed link crosses agency boundary")
    if (original.get("agency_id") and target.get("agency_id")
            and original["agency_id"] != target["agency_id"]):
        raise canonical.RecordIntegrityError("reviewed link crosses agency boundary")
    previous = original.get(field)
    if str(previous) == str(target_id):
        raise canonical.RecordIntegrityError("reviewed link is unchanged")
    original[field] = target["id"]
    # Never assert a successful repair if the proposed record still has a
    # conflicting parent, property or another problem on the same field.
    before = reconciliation_report(stage)
    after = reconciliation_report(proposal)
    def signature(issue):
        return tuple(issue.get(k) for k in ("collection", "id", "field", "issue"))
    old_issues = {signature(i) for i in before["issues"]}
    new_issues = {signature(i) for i in after["issues"]}
    if new_issues - old_issues:
        raise canonical.RecordIntegrityError("reviewed link introduces new inconsistency")
    if any(x["collection"] == collection and x["id"] == str(record_id)
           and x["field"] == field for x in after["issues"]):
        raise canonical.RecordIntegrityError("reviewed link still has unresolved conflict")
    canonical.validate_for_save(proposal)
    decision = {
        "collection": collection, "record_id": str(record_id),
        "field": field, "from": previous, "to": target["id"],
        "actor": actor.strip(), "at": at, "reason": reason.strip()
    }
    original.setdefault("reconciliation_history", []).append(dict(decision))
    proposal.setdefault("audit_log", []).append({
        "action": "reviewed_link_reconciled", "target": str(record_id),
        "actor": actor.strip(), "at": at, "note": field,
    })
    return proposal, decision
