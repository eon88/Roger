"""Roger B00 reusable two-agency *synthetic* acceptance fixture.

Deterministic identities, no passwords, no production records, no actual documents
or payments. Instantiate separately for each isolated agency database.
"""
import argparse
import json
import re


def build(agency_id):
    if not isinstance(agency_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{2,40}", agency_id):
        raise ValueError("Agency must be an alphanumeric test slug")
    def ident(kind, tag):
        return "ci-" + agency_id + "-" + kind + "-" + tag
    owner, tenant1, tenant2, trade, guarantor = (
        ident("party", "landlord"),
        ident("party", "resident-a"),
        ident("party", "resident-b"),
        ident("party", "contractor"),
        ident("party", "guarantor"),
    )
    p1, p2, t1, t2, case, job = (
        ident("property", "a"), ident("property", "b"),
        ident("tenancy", "a"), ident("tenancy", "b"),
        ident("case", "repair"), ident("job", "repair"),
    )

    def party(pid, role, label):
        return {
            "id": pid, "kind": "person", "status": "active", "roles": [role],
            "display_name": label + " (synthetic " + agency_id + ")",
            "account_id": None, "agency_id": agency_id,
            "email": role + "-" + agency_id + "@example.invalid",
        }

    persons = [
        party(owner, "landlord", "Example landlord"),
        party(tenant1, "tenant", "Example resident A"),
        party(tenant2, "tenant", "Example resident B"),
        party(trade, "trades", "Example plumber"),
        party(guarantor, "guarantor", "Example guarantor"),
    ]
    properties = [
        {
            "id": p1, "title": "Synthetic Flat A", "area": "Birmingham",
            "lifecycle_status": "occupied", "landlord_party_id": owner,
            "tenant_party_id": tenant1, "agency_id": agency_id,
        },
        {
            "id": p2, "title": "Synthetic Flat B", "area": "Birmingham",
            "lifecycle_status": "occupied", "landlord_party_id": owner,
            "tenant_party_id": tenant2, "agency_id": agency_id,
        },
    ]
    def tenancy(tid, pid, who, amount):
        return {
            "id": tid, "property_id": pid, "landlord_party_ids": [owner],
            "tenant_party_ids": [who], "status": "active",
            "tenancy_type": "assured_periodic", "start_date": "2026-06-01",
            "end_date": None, "rent_frequency": "monthly",
            "rent_amount_pence": amount, "agreement_status": "signed",
            "agency_id": agency_id,
        }
    tenancies = [tenancy(t1, p1, tenant1, 115000),
                 tenancy(t2, p2, tenant2, 125000)]
    case_record = {
        "id": case, "property_id": p1, "tenant_party_id": tenant1,
        "name": "Example resident A", "message": "Synthetic pipe leak",
        "status": "reported", "agency_id": agency_id,
    }
    job_record = {
        "id": job, "case_id": case, "property_id": p1,
        "trades_party_id": trade, "status": "invoice_review",
        "invoice": {
            "id": ident("invoice", "repair"), "amount_pence": 12500,
            "status": "recorded_unverified",
        },
        "agency_id": agency_id,
    }
    deposit = {
        "id": ident("deposit", "a"), "kind": "tenancy",
        "property_id": p1, "tenancy_id": t1, "amount_pence": 110000,
        "received_date": "2026-06-01", "status": "received_unverified",
        "protection_deadline": "2026-07-01", "agency_id": agency_id,
        "source": "synthetic_fixture_only",
    }
    document = {
        "id": ident("document", "inventory"), "property_id": p1,
        "tenancy_id": t1, "status": "metadata_only",
        "document_type": "inventory", "access_roles": ["agent"],
        "agency_id": agency_id,
        "description": "Synthetic metadata only; no file bytes",
    }
    rent = {
        "id": ident("rent", "a"), "property_id": p1, "tenancy_id": t1,
        "due_date": "2026-11-01", "amount_due_pence": 115000,
        "adjustments": [], "payments": [{
            "id": ident("payment", "a"), "amount_pence": 50000,
            "received_date": "2026-11-02",
            "reconciliation_status": "recorded_unverified",
        }],
        "agency_id": agency_id,
    }
    return {
        "agency_id": agency_id,
        "parties": persons,
        "properties": properties,
        "tenancies": tenancies,
        "registrations": [{
            "id": ident("registration", "plumber"),
            "role": "trades", "name": "Example plumber", "party_id": trade,
            "status": "pending", "agency_id": agency_id,
        }],
        "cases": [case_record],
        "jobs": [job_record],
        "rent_ledger_entries": [rent],
        "deposit_records": [deposit],
        "documents": [document],
    }


def validate(data):
    assert data["agency_id"]
    groups = [v for k, v in data.items() if isinstance(v, list)]
    ids = [r["id"] for items in groups for r in items]
    assert len(ids) == len(set(ids)), "Record IDs are not globally unique"
    assert all(r["agency_id"] == data["agency_id"] for items in groups for r in items)
    person_ids = {p["id"] for p in data["parties"]}
    prop_ids = {p["id"] for p in data["properties"]}
    tenancy_ids = {t["id"] for t in data["tenancies"]}
    case_ids = {c["id"] for c in data["cases"]}
    for prop in data["properties"]:
        assert prop["landlord_party_id"] in person_ids
        assert prop["tenant_party_id"] in person_ids
    for tenancy in data["tenancies"]:
        assert tenancy["property_id"] in prop_ids
        assert set(tenancy["tenant_party_ids"]) <= person_ids
        assert set(tenancy["landlord_party_ids"]) <= person_ids
        assert tenancy["tenancy_type"] == "assured_periodic"
    for job in data["jobs"]:
        assert job["case_id"] in case_ids
        assert job["property_id"] in prop_ids
        assert job["trades_party_id"] in person_ids
        assert job["invoice"]["amount_pence"] > 0
    for doc in data["documents"]:
        assert doc["property_id"] in prop_ids
        assert doc["tenancy_id"] in tenancy_ids
    for dep in data["deposit_records"]:
        assert dep["property_id"] in prop_ids
        assert dep["tenancy_id"] in tenancy_ids
    for payment in data["rent_ledger_entries"]:
        assert payment["tenancy_id"] in tenancy_ids
        assert payment["property_id"] in prop_ids
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--agency", required=True)
    args = parser.parse_args()
    fixture = build(args.agency)
    validate(fixture)
    print(json.dumps(fixture, separators=(",", ":"), sort_keys=True))
