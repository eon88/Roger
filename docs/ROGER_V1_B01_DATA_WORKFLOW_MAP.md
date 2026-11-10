# Roger v1 — B01 authoritative data relationships and workflow contract

**As of:** 10 November 2026  
**Source baseline:** `14073e5ea80b1ab8629882993fdd4b407c9daa1c`  
**Active development:** `feature/roger-v1-single-release-20261108`, draft PR #14, never deployed.

## 1. Authoritative data map

| Business concept | Authoritative collection | Secondary / display records that MUST NOT be auto-merged |
| --- | --- | --- |
| Agency | Root `agency_id` bound to one physical SaaS database | Agency branding and hostname environment variables |
| Human identity and role | `parties` Party IDs + verified `account_id` links | Registration/applicant leads, legacy free-text names, property `landlord` / `tenant` labels |
| Property | `properties` | Marketing data `public_listing`; original owner-entered `property_submissions` |
| Unit/room | Optional `property_units` with parent `property_id` | Existing property bedrooms/room descriptions; not an automatic split |
| Owner share and effective mandate | Optional `ownership_interests` for share basis points + `management_agreements` for agency authority | Owner names or `landlord_party_id` on legacy property; ownership share is not a management mandate |
| Application → tenancy | `cases` (enquiry) → `tenancies` (accepted tenant Party IDs, property, agreement) | Applicant free-text, stale prospect state, legacy tenancy owner/occupant labels |
| Repair | `cases` with linked `jobs` | Contractor visit notes, email thread and vendor-facing label |
| Invoice | Currently `jobs` invoice and quotation fields; **not yet a unified independent invoice ledger** | Contractor invoices, landlord statements and rent ledger are different economic events; do NOT merge or mark client-money ready |
| Rent | `rent_ledger_entries` with exact-pence payments and adjustments | Statement previews and bank reconciliation are evidence, not confirmation of transferred money |
| Holding / tenancy deposit | `deposit_records`, each linked to tenancy/property | Tenancy `deposit_amount_pence` is planned agreement amount, not payment or protection proof |
| Document | `documents` metadata, with private bytes under `FILES_DIR` | Tenancy `document_ids` and job `document_ids` are views/pointers, not separate attachments |
| Inspectable condition | `inventories` linked to tenancy/property, plus date, room snapshots, meter/key records | Repairs and compliance visits are separate historical events |
| Registration / compliance | `registrations`, `compliance_records` and property `prs_registration` (typed subjects) | Agent reminders are derived work, not government-certified compliance |
| History and responsibility | `audit_log`, local per-record `history`, authenticated actor and server timestamp | UI status badge and notification are not an authoritative event |

**Never deduplicate using only name, mobile number, email, postcode or similarity.** An explicit agent identity review and audit is needed before linking old data.

## 2. Versioning and compatibility

`stage-clone/canonical_records.py` provides the canonical collection catalogue, strict link checks for records tagged `model_version: 1`, the optional Unit and OwnershipInterest constructors, legacy inspection, and a **copy-only** upgrade plan. It does not write an agency database.

`model_metadata.version = 1` denotes adoption of the new catalogue while retaining historical records. Old records have no `model_version` and remain in compatibility mode; missing legacy links are **reported**, never guessed, deleted, or silently reassigned.

`ops/migration/upgrade_canonical_v1.py` supports offline preview, stop-the-instance apply and exact-byte restore from a private backup. It refuses writes in production/staging and refuses an apply with unresolved legacy references. These controls are **not** proof that an actual live PostgreSQL migration has been rehearsed: a production-compatible DB restore and signed release plan remain B26 work.

**New records covered by strict link validation on save:** tenancy, inventory, deposit and optional unit/ownership records. Legacy records and untagged job/approval/document records are still being normalised; do not claim the entire model is strict.

## 3. Concurrency and persistence

`storage_write_lock()` serialises HTTP updates using a per-file inter-process lock or a PostgreSQL advisory transaction lock. A persistent `_stage_revision` counter now adds compare-and-swap protection: stale snapshots are rejected with a conflict instead of overwriting newer records. A complete document/tenant request is read before taking the lock.

`save_stage()` checks duplicate entity IDs, strict v1 links, agency identity, and expected revision **before** an atomic file replace or a PostgreSQL transaction with its entity projections. It increments revision only on a successful commit.

**Limitations:** all external workers/importers must use the same lock; direct SQL writers outside Roger can bypass snapshot revision and advisory lock. A release gate must prohibit unsynchronised direct writers, verify migration tooling, and ultimately add database-native constraints after legacy reconciliation.

## 4. Workflow transitions and permission boundaries

`workflow_engine.py` is authoritative for **property** and **tenancy** transition graphs. The property and tenancy HTTP handlers now call the same engine after server-side permission and business-rule validation, recording actor, time, status and optionally a client-supplied request token. Replaying the token for a different change is forbidden; replaying the identical transition makes no new event. These changes do not automatically certify legal notices, release funds or approve work.

Agent-only role access for those two HTTP actions comes from server `H.ROLE_API`, not a hidden menu or form.

**Still open B01.04:** case/contractor-job/quote/variation/invoice/approval transitions currently have separate handler-specific guards. Before B01 acceptance they need a shared transition-and-audit service (or documented audited adapters) covering every action/role, including no-duplicate approvals, legitimate replays and stale requests, without breaking the four-role repair journey.

## 5. Integrity and identity acceptance gaps

- **B01.01 / B01.02:** reconcile shadow/duplicate business concepts; explicitly define an invoice source of truth, typed documents and eventually database-native constraints after imported-legacy repair.
- **B01.03:** the optional property-unit and joint ownership model is defined and strict constructors tested; owner shares are in basis points and cannot exceed 100% for concurrent active records. Joint ownership UI and accounting allocation belong to B05/B12.
- **B01.04:** consolidate case/job/quote/invoice/approval transitions and prove permissions/retries globally.
- **B01.05:** stale file writes pass unit tests. Two-real-PostgreSQL-stack test has been added and must pass the same revision before signoff.
- **B01.06:** strict newly tagged IDs/links and agency-owned collections fail closed; untagged historical links remain in compatibility mode and need human review in B04.
- **B01.07:** offline dry-run/exact-backup rollback unit tests pass; production-compatible PostgreSQL migration/restore remains release-blocked.

## 6. B01 acceptance evidence to collect

- Unit test `tests/test_b01_canonical_records.py` — duplicates, foreign tenancy link, deposit/inventory property consistency, optional units and joint owners.
- Unit test `tests/test_b01_snapshot_revision.py` — stale object overwrite rejection.
- Unit test `tests/test_b01_schema_upgrade.py` — dry-run/apply/backup/rollback/foreign source rejection.
- Unit test `tests/test_b01_workflow_engine.py` and `tests/test_b01_agent_transition_handlers.py` — permitted property/tenancy transitions, audit, request replay and malformed input rejection.
- CI Docker/PostgreSQL `tests/b00_seeded_agency_integration.py` — seeded two-agency storage, foreign-cookie/record denial and real stale-write guard.
- Entire existing Python suite, four-role Chromium browser suite and two-agency SaaS suite on the exact same head revision.

**B01 status:** in progress until *all* seven acceptance tasks are demonstrated. No deployment/merge authorization is implied.
