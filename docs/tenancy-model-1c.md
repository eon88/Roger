# Roger Tenancy model — 1C design

**Status:** target tenancy record and lifecycle decision. This document does not create or alter tenancies in live data.

## Purpose

A Tenancy is a time-bounded legal/operational relationship connecting one Property to one or more tenant Parties and one or more landlord Parties. It is distinct from the enduring Property and from any portal account. A new tenancy is created for each let; renewal or replacement terms are versioned or recorded as a successor tenancy so the old record remains historically accurate.

## Target record

```json
{
  "id": "tenancy_...",
  "property_id": "property_...",
  "landlord_party_ids": ["party_..."],
  "tenant_party_ids": ["party_..."],
  "start_date": "2026-11-01",
  "end_date": null,
  "rent": {"amount_pence": 125000, "frequency": "monthly", "due_day": 1},
  "deposit": {
    "amount_pence": 144230,
    "scheme": null,
    "reference": null,
    "status": "not_recorded"
  },
  "agreement_status": "draft",
  "status": "pending",
  "move_in_date": null,
  "notice_date": null,
  "checkout_date": null,
  "document_ids": [],
  "created_at": "...",
  "updated_at": "..."
}
```

The IDs in `landlord_party_ids` are a convenience projection; the canonical source is the dated Party-to-Tenancy participation record described in [1D](core-relationships-1d.md).

## Rules

- A tenancy belongs to exactly one property and may include multiple tenants and owners.
- A landlord on a tenancy must have an ownership or authorised-management relationship to the property for the relevant period. The property agent is an operator, not automatically the landlord.
- Dates are ISO 8601 dates in the property's jurisdiction. Rent is integer minor units with explicit frequency and due rule.
- Agreement status and tenancy status are separate: a signed agreement does not imply that move-in occurred.
- The rent ledger, deposit record, inspections, cases and documents reference a tenancy ID where applicable. Historical values are snapshots; changing a live profile must not rewrite an issued agreement, ledger entry or statement.
- Current tenancy is derived by date and status. Property keeps no duplicate free-text current-tenant field after migration.
- Only one active occupancy tenancy per dwelling at a time unless the property model explicitly supports separate units.
- A joint tenancy is one tenancy with several tenant Parties, not duplicate tenancy records.
- Renewal/variation preserves the prior agreement and its dates. Do not overwrite a signed agreement's terms.
- Former tenant portal access is explicitly revoked or narrowed after checkout; historical messages and obligations remain available to the agent.

## Lifecycle

`prospect → application → referencing → approved → offer → agreement → deposit → move_in → active → renewal | notice → checkout → deposit_resolution → ended`

Decline/withdrawal may happen before activation. Missing or uncertain dates, deposit information or agreement state must remain explicit as unknown/pending rather than being fabricated from the property card.

## Acceptance criteria

- Joint tenants and joint owners are representable without duplicate property records.
- Each tenancy has immutable identity and a clear status/date history.
- Property view can show current, future and past tenancies separately.
- Rent obligation, deposit, agreement and lifecycle state are independent fields.
- Ending a tenancy does not delete its associated cases, rent records, documents or audit trail.
- A tenancy transition alone cannot grant an account access; account and Party-to-tenancy permissions are checked separately.

## Prototype notes

The current sample `stage.json` contains no `tenancies` collection. It stores property landlord and tenant names directly in `properties[]`. Those names are not enough to invent tenancy dates, legal status, deposit or agreement facts. The safe initial migration is to preserve them as unverified relationship candidates and ask the agent to confirm tenancy details.
