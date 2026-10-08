# Roger existing-data map — 1E

**Source inspected:** `stage-clone/stage.json`, `stage-clone/serve.py` and `stage-clone/make_users.py` on the current working branch. The sample store contains properties, cases, jobs, registrations, approvals, audit entries, appointments, invitations and documents. It has no canonical Parties, Party roles, Tenancies, rent ledger or compliance-record collection.

This is a mapping specification, not a data migration. No runtime store was changed.

## Record mapping

| Existing record | Target | Mapping and handling |
|---|---|---|
| `users.json.users[]` | Account + Party + PartyRole | Create an account for each user; create/link a Party for its display identity; map `role` to an active role assignment. Never migrate password hashes or sessions into Party data. The account/Party link requires explicit validation; role seeding does not prove a person-to-property relationship. |
| `stage.json.properties[]` | Property + candidate ownership/tenancy relations | Preserve `id` as Property ID. Map `title` to a legacy/public title, `area` to unverified address/locality, `beds` to bedrooms and `rent` to rent amount only after confirming its units/frequency. `landlord` and `tenant` strings become unresolved relationship candidates, not access grants. |
| `cases[]` | Case + optional Party/Property/Tenancy links | Preserve case ID and all history. `property_id` maps directly when it identifies an existing Property. Resolve `name`/email to Parties only when unambiguous and agent reviewed. Preserve original submission details and consent as snapshots. |
| `jobs[]` | Job + Case/Property/Party links | Preserve job ID, `case_id` and `property_id`. Resolve `assigned_to` and `requested_by` by reviewed Party mapping; do not infer from company display name alone. |
| `registrations[]` | Prospect/application + optional Party | Preserve registration ID, submitted fields, consent, status and timestamps. Do not turn pending/rejected applicants into active role assignments. Agent approval may link/create Party and activate a role while retaining submission history. |
| `approvals[]` | Approval event + Property/Job + Party | Preserve IDs, amount, reason and decision history; map `landlord` string only through reviewed links. |
| `appointments[]` | Appointment + Property/Case + participant Parties | Preserve IDs, time, status, outcome and notes. Resolve `invitee_role` and other name fields through explicit participant links. |
| `invitations[]` | Invitation + intended Party/Account + Property relation | Preserve token lifecycle securely; token is not Party identity. Resolve recipient by explicit reviewed invitation flow; accepting the invite creates/link account, Party and scoped relationship. |
| `documents[]` | Document metadata + file object + entity links | Preserve metadata and verification history. Map `data_b64` to private file storage in a separate migration; retain checksum and access scope. Do not expose file bytes through Party records. |
| `audit_log[]` | Audit event | Preserve timestamp, actor/action/target/note. Resolve actor IDs where possible but keep original actor text as immutable legacy evidence. |
| `authority` | Agency configuration / authorization policy | Keep as agency/property authority configuration, not as a person's role. |

## Identity resolution policy

1. Keep source IDs, display values and provenance for every migrated record.
2. Normalize email only for duplicate suggestions. Do not treat it as a unique key: shared, changed, mistyped or reused addresses are possible.
3. Do not auto-merge on name, email, phone or address.
4. Exact, unambiguous account links may be proposed for agent review; unresolved/colliding cases remain unlinked.
5. Legacy strings may continue to render during compatibility but must not authorize access.
6. Do not invent absent legal names, addresses, dates, rent frequency, tenancy/deposit status, company relationships or consent.
7. Record each resolution/override with actor, date, source and reason.

## Migration order and rollback

- Back up `stage.json` and `users.json` with restrictive permissions; verify the backup can be read before mutation.
- Produce a dry-run report counting each proposed Party and relationship, collisions, missing references and unsupported fields.
- Write new collections alongside old data, preserving all existing records and IDs.
- Validate foreign-key coverage and permissions for Agent, Landlord, Tenant and Trades against reviewed fixture identities.
- Switch reads in a reversible deployment only after every required relationship is resolved; keep an untouched backup and rollback path.
- Remove legacy strings only in a later, separately reviewed migration.

## Known blockers before live conversion

- The tracked sample has no account-to-property or tenancy links, and the seeded user file is generated at runtime.
- Property `rent` units/frequency and `area` address completeness require confirmation.
- Landlord and tenant names on property records are not enough to establish legal ownership, management authority, tenancy dates or permissions.
- Existing records therefore support a safe schema and dry-run design, but not automatic conversion into confirmed relationships.
