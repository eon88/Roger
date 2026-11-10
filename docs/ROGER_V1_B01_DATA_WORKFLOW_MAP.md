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

**New records covered by strict link validation on save:** tenancy, inventory, deposit, optional unit/ownership records, and new agent-uploaded documents. New canonical job, appointment and approval links are checked when a record is version tagged. Legacy records remain available for review; do not claim the entire model is strict.

## 3. Concurrency and persistence

`storage_write_lock()` serialises HTTP updates using a per-file inter-process lock or a PostgreSQL advisory transaction lock. A persistent `_stage_revision` counter now adds compare-and-swap protection: stale snapshots are rejected with a conflict instead of overwriting newer records. A complete document/tenant request is read before taking the lock.

`save_stage()` checks duplicate entity IDs, strict v1 links, agency identity, and expected revision **before** an atomic file replace or a PostgreSQL transaction with its entity projections. It increments revision only on a successful commit.

**Limitations:** all external workers/importers must use the same lock; direct SQL writers outside Roger can bypass snapshot revision and advisory lock. A release gate must prohibit unsynchronised direct writers, verify migration tooling, and ultimately add database-native constraints after legacy reconciliation.

## 4. Workflow transitions and permission boundaries

`workflow_engine.py` is authoritative for **property** and **tenancy** transition graphs. The property and tenancy HTTP handlers now call the same engine after server-side permission and business-rule validation, recording actor, time, status and optionally a client-supplied request token. Replaying the token for a different change is forbidden; replaying the identical transition makes no new event. These changes do not automatically certify legal notices, release funds or approve work.

Agent-only role access for those two HTTP actions comes from server `H.ROLE_API`, not a hidden menu or form.

**B01.04 accepted in isolated development, 10 November:** a shared action-request ledger in `workflow_engine.py` now hashes the authorised action payload, actor and request token into the same snapshot as the event. Existing agent job actions (including supplier payment/credit recording and invoice handoffs), landlord approvals and all per-case actions check an identical replay after their server-side role and object permission gates; differing payloads or actors are conflicts. Retried case replies/approval decisions do not duplicate thread messages. **Implemented and tested:** authenticated agent, tradesperson, landlord and case actions now pass shared domain transition/role checks; retried contractor start/completion, invoice handoffs, partial-payment events, variation handling and landlord decisions have durable histories and replay protection. Tokens remain optional for compatibility with older clients, while status guards and supplier reference uniqueness prevent repeated unauthorised financial effects. No actual payments or legal decisions are automated by the workflow engine.

## 5. Integrity, canonical authority and future release boundaries

- **B01.01 / B01.02 (accepted foundation):** the authoritative Person, Property, Tenancy, Case, Document and Supplier Invoice sources are explicitly enumerated in `legacy_reconciliation.AUTHORITATIVE`; supplier invoice identity remains bound to `jobs` (not rent receipts or landlord statements). External source-ID collisions flag both rows, supplier invoice numbers are uniquely checked per contractor, and shadow invoice contradictions stop offline migration. `propose_reviewed_link` produces a copy with actor, date, reason and audit events, never a guessed merge. Actual new-agency historic duplicates remain B04 supervised import decisions; creating a separate accounting ledger is B12 work.
- **B01.03:** the optional property-unit and joint ownership model is defined and strict constructors tested; owner shares are in basis points and cannot exceed 100% for concurrent active records. Joint ownership UI and accounting allocation belong to B05/B12.
- **B01.04 (accepted foundation):** `workflow_engine.validate_domain_action` blocks forbidden repair/job/quote/invoice/approval actor and status transitions. Property/tenancy transitions retain the shared graph; case handlers are audited, server-role-checked adapters. Agent and trades actions, landlord approvals, and case actions share payload-bound replay checks. Payments, supplier credits and variations preserve workflow events even when their status badge is unchanged. Legal interpretation and actual payment-provider sign-off remain later bundle/release work.
- **B01.05:** stale file writes pass unit tests. Two-real-PostgreSQL-stack test has been added and must pass the same revision before signoff.
- **B01.06 (accepted foundation):** legacy inspection flags wrong-property job/document/deposit/rent/approval/appointment links, missing attachment pointers, document supersession gaps, duplicate invoice numbers and cross-agency links. New canonical jobs/approvals/documents are version tagged; uploads refuse mismatched subjects. `guard_no_silent_deletion` prevents changing archived IDs, durable workflow/reconciliation/audit histories, prior payments, supplier credits, document bytes and links without reviewed evidence. The real two-agency PostgreSQL pilot rejects wrong-tenant documents and foreign jobs, and proves the database unchanged after denial. Historic imported issues are blocked for explicit B04 human review, never silently reassigned.
- **B01.07:** offline dry-run/exact-backup rollback unit tests pass; production-compatible PostgreSQL migration/restore remains release-blocked.

## 6. B01 acceptance evidence

- Unit test `tests/test_b01_canonical_records.py` — duplicates, foreign tenancy link, deposit/inventory property consistency, optional units and joint owners.
- Unit test `tests/test_b01_snapshot_revision.py` — stale object overwrite rejection.
- Unit test `tests/test_b01_schema_upgrade.py` — dry-run/apply/backup/rollback/foreign source rejection.
- Unit test `tests/test_b01_workflow_engine.py` and `tests/test_b01_agent_transition_handlers.py` — permitted property/tenancy transitions, audit, request replay and malformed input rejection.
- CI Docker/PostgreSQL `tests/b00_seeded_agency_integration.py` — seeded two-agency storage, foreign-cookie denial, real stale-write guard, wrong-property document refusal, foreign-agency job refusal and unchanged database after rejected writes.
- Entire existing Python suite, four-role Chromium browser suite and two-agency SaaS suite on the exact same head revision.

## 7. Continued implementation (10 November 2026)

- Additional regression files: `tests/test_b01_historical_link_reconciliation.py`, `tests/test_b01_document_attachment_consistency.py`, `tests/test_b01_financial_action_replay.py`. These add 23 focused tests on top of pre-existing coverage.
- New strict link and duplicate-source diagnostics in `canonical_records.py`; no automatic merging or silent alteration of earlier records.
- Added new-upload relationship checks, canonical document IDs/version tagging, per-case request replay, landlord approval replay and agent repair/financial action replay.
- Existing legacy document supersession test now explicitly links its historical job to the case it references; intentionally broken links are refused.
- **Final tested code SHA:** `3ed0a0230137a05423151d052b70c225c1930e43`. Independent unit, browser and SaaS stacks passed at this SHA; aggregate mandatory gate succeeded at [run 42784113763](https://github.com/eon88/Roger/actions/runs/42784113763).
- **No production, staging, B02 or PR merge actions.**

**B01 status:** ACCEPTED for isolated development, **7/7 foundation tasks**. Historical real-agency import decisions remain in B04, production-like PostgreSQL restore and external legal/accounting release approval remain B26. No production/staging/merge authorization is implied.

## 8. Final B01 evidence and bounded acceptance (10 November 2026)

- **Code tested:** [`3ed0a0230137a05423151d052b70c225c1930e43`](https://github.com/eon88/Roger/commit/3ed0a0230137a05423151d052b70c225c1930e43)
- **Python:** 593 regression tests passed — [Actions run 42784113705](https://github.com/eon88/Roger/actions/runs/42784113705).
- **Four-role real Chromium browser:** passed — [Actions run 42784113696](https://github.com/eon88/Roger/actions/runs/42784113696).
- **Independent two-agency real PostgreSQL:** passed, including denial of foreign agency job and conflicting document links — [Actions run 42784113516](https://github.com/eon88/Roger/actions/runs/42784113516).
- **Mandatory one-SHA policy + Python + browser + SaaS aggregate gate:** passed — [Actions run 42784113763](https://github.com/eon88/Roger/actions/runs/42784113763).
- **Legacy snapshot source inspection:** committed `stage-clone/stage.json` has 4 properties, 17 cases, 10 jobs, 6 approvals and 1 document; no duplicate IDs, broken direct parent links, suspicious supplier invoice collisions or orphan document pointers were found in a read-only check. This is a demo snapshot, not a check of external historic agency datasets.
- **Negative cases:** foreign actor, stale writes, replay with changed payload, invalid transitions, unapproved work, mismatched tenancy documents, financial over-settlement and missing payments, changing recorded supplier invoice amounts, document evidence mutation and destructive audit history replacement all have regression coverage.
- **Scope boundary:** no production migration or deployment; no real owner client-money movement; no certification of every pre-existing third-party agency dataset. Those depend on B04/B10–B12/B26 as recorded in the master checklist. B02 can now start on this same draft one-release branch.
