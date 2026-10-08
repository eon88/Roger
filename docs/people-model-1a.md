# Roger People model — 1A design

**Status:** design decision for the first canonical People model. This document defines the target; it does not migrate live records or change login behaviour.

## What the current code does

Roger currently has two separate identity layers:

- Login accounts live in `users.json` and carry one `role` plus a `display_name`.
- Operational records in `stage.json` copy names and contact details into registrations, enquiries, cases, properties and invitations.

The server then links some records by matching display names or email strings. For example, property ownership and tenant access are checked against names. This is workable for the prototype, but names can change or collide, one person cannot cleanly hold several roles, and a registration or enquiry is not the same thing as a verified person.

## Decision

Use **Party** as the canonical identity record. A Party represents either an individual or an organisation. A party may have multiple role assignments and many relationships to properties, cases and other parties.

Keep **login accounts** separate from Parties. An account proves who can sign in; it is linked to a Party when identity has been established. A Party may exist without an account (prospect, company, joint owner, former tenant), and an account must not gain access merely because its email matches a Party.

Keep **prospects and applications** as workflow records. A registration/enquiry carries its own submitted details, consent, status and audit history, then may be linked to a Party after agent review. Do not overwrite the original submission when creating or linking a Party.

## Target record shapes

Illustrative JSON shape for the transition from the current JSON store; field names can be adapted when the relational schema is designed.

```json
{
  "parties": [
    {
      "id": "party_...",
      "kind": "person",
      "display_name": "Alex Example",
      "legal_name": null,
      "email": "alex@example.test",
      "phone": "+44 ...",
      "address": null,
      "preferred_contact_method": "email",
      "status": "active",
      "notes": "",
      "created_at": "...",
      "updated_at": "..."
    },
    {
      "id": "party_...",
      "kind": "organisation",
      "display_name": "Example Heating Ltd",
      "legal_name": "Example Heating Limited",
      "email": "office@example.test",
      "phone": "+44 ...",
      "address": null,
      "preferred_contact_method": "email",
      "status": "active",
      "notes": "",
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "party_roles": [
    {
      "id": "partyrole_...",
      "party_id": "party_...",
      "role": "landlord",
      "status": "active",
      "valid_from": "...",
      "valid_to": null
    }
  ],
  "party_relationships": [
    {
      "id": "partyrel_...",
      "from_party_id": "party_...",
      "to_party_id": "party_...",
      "type": "employee_of",
      "valid_from": "...",
      "valid_to": null
    }
  ],
  "accounts": [
    {
      "id": "account_...",
      "party_id": "party_...",
      "username": "...",
      "status": "active"
    }
  ]
}
```

### Rules

- `kind` is `person` or `organisation`; it is not an account role.
- A party can hold several roles at once. Initial role values: `agent`, `landlord`, `tenant`, `trades`. Prospect/application status belongs to its workflow record, not to the Party role.
- A company tradesperson is an organisation Party. The named contact is a person Party linked with `employee_of` (or another explicit relationship). A sole trader can be represented as a person Party with the trades role.
- Use immutable IDs for every relationship. Names and email addresses are display/contact attributes, never foreign keys or permission checks.
- Property ownership, tenancy occupancy and job participation should reference Party IDs. Their own domain records define the relationship and its dates; a generic role alone must not grant access.
- Account-to-Party linking is explicit and agent-audited. An email match can suggest a duplicate for review but must never silently merge records or grant access.
- Keep submitted name/email/phone, consent and timestamps on the original enquiry or registration as an immutable snapshot; link it to a Party after review.
- Preserve historical role assignments and relationships with status/end dates instead of deleting them when a person leaves or a role changes.
- Contact details are private. Return only the minimum fields each role needs, using the existing server-side role scoping.

## Workflow and access implications

1. Public enquiry/registration creates a prospect workflow record with the submitted snapshot and consent.
2. An agent reviews it, searches for a possible existing Party, then explicitly links that Party or creates a new one.
3. Approval adds or activates a Party role and, where appropriate, a domain relationship (for example landlord-to-property or trades company-to-contact).
4. An invitation creates an account link only after the invite is accepted and identity checks pass. A property/tenancy relationship and account role determine the permitted view.
5. Role changes, account linking, merging or deactivation are audited. No self-service flow can grant another role or attach an account to another person's record.

## Migration from the prototype

- Add canonical IDs without removing existing names or fields in the first migration.
- Create Parties from user accounts and operational records; preserve every source record and its ID.
- Auto-link only when a deterministic existing identifier is available and unambiguous. Treat email/name collisions as an agent review queue; do not merge them.
- Add `party_id` references alongside current string fields, backfill and validate permissions against both during a short compatibility period.
- Switch reads and access checks to IDs only after all required relationships have been reviewed and backfilled.
- Retain old fields until role-workflow tests pass, then remove them in a separate migration with a backup and rollback plan.

## Acceptance criteria for implementation

- One person can be landlord and tenant (or hold another combination of roles) without duplicate identity records.
- One organisation can have multiple contact people and a contact person can be linked to a company.
- Prospects remain distinct from active portal users; approval does not erase the submitted application.
- Property, case, job and account links use stable IDs rather than names/emails.
- Duplicate email addresses do not merge identities or expose property data.
- Role-scoped views and every existing four-role workflow continue to pass after migration.
- Agent actions that link accounts, parties, roles or properties leave an audit entry.

## Next roadmap item

Proceed to **1B — Property model**, then define Party-to-Property and Party-to-Tenancy relationships together before migrating existing records.
