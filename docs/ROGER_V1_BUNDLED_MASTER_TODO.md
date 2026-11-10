# Roger v1.0 — BUNDLED MASTER TO-DO LIST

**Created:** 8 November 2026  
**Branch:** `feature/roger-v1-single-release-20261108`  
**Release PR:** https://github.com/eon88/Roger/pull/14  
**Governing product contract:** [ROGER_V1_FINAL_SCOPE_FREEZE.md](ROGER_V1_FINAL_SCOPE_FREEZE.md)  
**Product:** England-first **residential lettings and property management ONLY**. No property sales, buyers, vendors, conveyancing or sales chains.

## How to work

1. **One active bundle at a time.** Pick the next dependency-ready bundle; run its tests and record evidence before starting another.
2. **Small implementation passes inside each bundle.** If a bundle spans many files, split its unchecked tasks into no more than 3–5 closely related code edits per pass. Review and test after each pass. These are internal git commits, **not downloads, installations or releases**.
3. **One branch / one final release.** All changes remain on the one-release development branch and in synthetic CI or isolated test infrastructure. Nothing is deployed, merged into the working product or installed by the user until B26.
4. **Truthful status labels:** OPEN = unimplemented/unchecked; PARTIAL = relevant code exists; CODED = implemented; UNIT PASS = isolated tests; BROWSER PASS = real UI tested; ACCEPTED = full bundle contract including negative cases; BLOCKED = an external requirement is unsatisfied. An earlier green job does **not** mark an entire bundle complete.
5. **At end of each bundle:** record exact commit, tests and run IDs, implementation/denial/edge cases, regressions, unresolved blockers, and update the checklist. Keep old features working.
6. **Do not silently shrink scope.** In-scope missing features remain open until verified. Qualified England letting legal/accounting approval and real external provider access are release dependencies, not something code alone can certify.

## Baseline evidence (not full-system acceptance)

- **503 Python tests passed** on commit `df81dd62dcd26e85721b36d6e507809554490b25`: https://github.com/eon88/Roger/actions/runs/42533281668
- **Four-role Chromium and extended repair, tenancy, inventory and deposit browser checks passed:** https://github.com/eon88/Roger/actions/runs/42533281621
- **Two independent agency pilot stacks passed:** https://github.com/eon88/Roger/actions/runs/42533281673
- **Real Ollama text interview passed in an isolated experiment:** https://github.com/eon88/Roger/actions/runs/42524033552
- The genuine vision-model review, whole-lifecycle acceptance, production-like backup/restore, security and regulated workflow review are **NOT accepted**.
- **Production state:** unchanged. **Release status: NOT READY.**

## Execution order at a glance

| Phase | Bundles | Outcome |
| --- | --- | --- |
| I. Architecture & foundation | B00–B04 | Reliable shared data, permissions, agency operations and migration |
| II. Lettings lifecycle | B05–B09 | Landlord/property → rental applicant → legally appropriate tenancy |
| III. Finance | B10–B12 | Traceable deposits, rent, reconciliation and owner statements |
| IV. Property operations | B13–B17 | Safe repairs, trade workflows, AI, inspections and compliance |
| V. Communications & intelligence | B18–B22 | Documents, email, automation, Agent Desk and integration boundaries |
| VI. Independent acceptance & release | B23–B26 | Security/UX testing, integrated release candidate, proven rollback and one launch |

**Dependency note:** Some bundles may have existing code and tests; that is a useful starting point, not proof of acceptance. Work on an earlier bundle may reveal a later defect, which should be logged and assigned back to the correct bundle.

## I. Architecture & foundation

### B00 — Release baseline and test map

**Depends on:** None  
**Starting point:** Test suites running; acceptance traceability incomplete

- [x] **B00.01** Snapshot the existing v1 development branch, CI checks, test fixtures and API/portal inventory as the immutable comparison baseline.
- [x] **B00.02** Turn the 12 frozen product modules into a requirements-to-tests traceability matrix, assigning one named owner and evidence link per requirement.
- [x] **B00.03** Classify each existing feature as absent, coded, unit-tested, browser-tested or fully accepted; avoid generic 'done' claims.
- [x] **B00.04** Create one reproducible isolated two-agency dataset with landlord, property, renter, trades, invoices, deposits and documents.
- [x] **B00.05** Define an explicit pass/fail/blocked template and a top-priority bug queue; record dependencies without expanding product scope.
- [x] **B00.06** Set CI branch checks so a failed test blocks bundle acceptance; ensure no workflow can deploy the development branch.

**Bundle acceptance (DONE):** Each agreed requirement maps to an implementation location, at least one acceptance test or known gap, and a release-gate owner; the protected draft branch cannot deploy.

**Evidence:** [B00 immutable baseline](ROGER_V1_B00_BASELINE.md) `14073e5ea80b1ab8629882993fdd4b407c9daa1c` · [12-module requirements/test/owner matrix](ROGER_V1_B00_TRACEABILITY_MATRIX.md) · [status, blocker register and test-report template](ROGER_V1_B00_ACCEPTANCE_AND_BLOCKERS.md) · deterministic test fixtures `tests/fixtures/v1_two_agency_data.py` · Docker/PostgreSQL seeding and cross-agency checks `tests/b00_seeded_agency_integration.py` · [one-run mandatory acceptance CI: PASS](https://github.com/eon88/Roger/actions/runs/42771971198) (policy, Python, Chromium and isolated SaaS, same SHA). **B00: accepted as development/test-map setup — NOT v1 production release approval.** **Governance limitation:** GitHub ruleset list was empty; administrator-enforced merge protection is not confirmed and remains a B26 release blocker.


### B01 — Canonical data model and workflow engine

**Depends on:** B00  
**Starting point:** Linked Party/property/tenancy entities exist; workflow model partial

- [x] **B01.01** Inventory all record types, identifiers and relationships; eliminate duplicate Person, Property, Tenancy, Case, Invoice and Document sources.
- [x] **B01.02** Define schema versions, migration functions, integrity constraints, relevant foreign keys, effective dates and soft-deletion/archival rules.
- [x] **B01.03** Design distinct units/rooms and joint ownership while keeping optional features backward compatible.
- [x] **B01.04** Centralise legal workflow transitions, actor permission, reason, history and idempotency across repairs, tenancy, invoices and approvals.
- [x] **B01.05** Make updates atomic and safe under competing staff requests; test concurrent writes to the current snapshot/PostgreSQL backend.
- [x] **B01.06** Prevent cross-agency references, orphan documents, contradictory status and silent data replacement.
- [x] **B01.07** Test legacy data upgrades and reversible backup/restore of schema changes.

**Bundle acceptance (ACCEPTED — ISOLATED DEVELOPMENT ONLY):** Every workflow uses authoritative linked identifiers, validated transitions and durable audit records; migration and concurrency tests pass.

**Evidence (B01 ACCEPTED — 7/7):** [canonical data/workflow and review map](ROGER_V1_B01_DATA_WORKFLOW_MAP.md) · [exact code commit `3ed0a023`](https://github.com/eon88/Roger/commit/3ed0a0230137a05423151d052b70c225c1930e43) · [593 Python tests PASS](https://github.com/eon88/Roger/actions/runs/42784113705) · [real four-role browser PASS](https://github.com/eon88/Roger/actions/runs/42784113696) · [independent two-agency PostgreSQL and denied foreign links PASS](https://github.com/eon88/Roger/actions/runs/42784113516) · [same-SHA mandatory aggregate gate PASS](https://github.com/eon88/Roger/actions/runs/42784113763). The canonical business sources and supplier invoice identity are declared; legacy duplicate source identities and inconsistent job/finance/document links are surfaced for explicit reviewed corrections, never auto-merged. Workflow action and role/status graphs, payload-bound retries, immutable financial history, agency isolation, stale-write denial, backup/recovery and wrong-link rejection are tested. The committed demonstration snapshot has no reported orphan links or duplicate source IDs.

**Boundary and handoff:** B01 accepts the data/workflow *foundation* on synthetic isolated copies, not the cleanliness of future agency imports. B04 handles actual historical source reconciliation by an authorised human; B10–B12 finish deposits/client-money and financial accounting; B26 requires production-compatible restore rehearsal, qualified legal/accounting sign-off and one release. Request tokens remain optional for legacy clients; server state/unique financial evidence guards still block unsafe duplicates, with full client rollout in later bundles. **No B02 changes, no production/staging deployment, no merge, no installation. B02 is dependency-ready.**

### B02 — Authentication, roles and agency isolation

**Depends on:** B01  
**Starting point:** Existing four-role login, agency separation and synthetic boundary tests

- [x] **B02.01** Enumerate server-side access controls for every GET, POST, upload, attachment download, export, email and background job.
- [x] **B02.02** Verify agent roles versus landlord, tenant, applicant and trades: identity, property relationship, job assignment and document access.
- [x] **B02.03** Complete staff invitation, suspension, password-reset/recovery, session revocation and strong authentication/MFA approach.
- [x] **B02.04** Protect against CSRF, insecure cookies, brute force, unsafe shared links and hidden privilege escalation.
- [x] **B02.05** Add cross-agency, cross-property, joint owner, multiple occupant and stale-session denial tests.
- [x] **B02.06** Audit information leakage in logs, public error responses, analytics, statements and notification payloads.

**Bundle acceptance (ACCEPTED — ISOLATED DEVELOPMENT ONLY):** Every endpoint denies unauthorised actors in automated tests; realistic two-agency/browser isolation passes, including documents and exports.

**Evidence (B02 ACCEPTED — 6/6):** [Security access matrix and release boundaries](ROGER_V1_B02_SECURITY_ACCESS_MATRIX.md) · [exact tested implementation `712fb489f6164a0517ed4384d9a523d3a3533dfc`](https://github.com/eon88/Roger/commit/712fb489f6164a0517ed4384d9a523d3a3533dfc) · [635 Python tests PASS](https://github.com/eon88/Roger/actions/runs/42802512821) · [four-role Chromium browser PASS](https://github.com/eon88/Roger/actions/runs/42802512931) · [independent two-agency real PostgreSQL staff/tenant isolation PASS](https://github.com/eon88/Roger/actions/runs/42802512818) · [one-commit mandatory aggregate PASS](https://github.com/eon88/Roger/actions/runs/42802512802). All GET/POST routes inventoried and protected/public policy checked by AST test. Four-role/account/Party ownership, landlord/tenant document/financial redaction, TLS-ready secure cookies, origin-CSRF checks, denied expired/role-changed/foreign sessions, staff administrator invite/suspend/reset, password confirmation, optional TOTP MFA, session revocation, public error redaction, safe attachment downloads and joint owner/occupant denial tests completed.

**Boundary/handoff:** B02 accepts the local development security *foundation* against synthetic isolated data and a live two-agency **test** database, not production IAM certification. Staff-enforced MFA is configurable and OFF until staged rollout; account/IP brute-force throttle is per process, not yet distributed; TOTP secrets need deployment-grade encryption/key custody and administrator break-glass MFA recovery policy in B26. The future single release must pass its own deployment and operational review. **B03 is dependency-ready but no B03 changes, staging/production deployment, PR merge or release have been made.**

### B03 — Agency onboarding and SaaS administration

**Depends on:** B01, B02  
**Starting point:** Isolated SaaS agency pilot and provisioning scripts; billing/ops not accepted

**Progress (PARTIAL — NOT ACCEPTED, 10 November 2026):** Agency profile and verified-admin edit page/API, branch/contact configuration, operator-only manual plan/status controls, runtime suspension guard, staff/property plan limits and initial B03 Python tests are committed. Existing isolated two-agency pilot passed; full same-SHA browser/aggregate acceptance is being rerun after an unrelated tenancy-form refresh issue. See [B03 exact implementation and remaining acceptance gates](ROGER_V1_B03_ONBOARDING_PROGRESS.md). **All B03 checkboxes remain open until their complete acceptance evidence is recorded; no deployment or release.**

- [ ] **B03.01** Finish repeatable agency creation with verified agency ID, domain, branding, office address, operating hours and emergency contacts.
- [ ] **B03.02** Implement office/branch settings, staff/permissions, service package and maintenance/spending authorities.
- [ ] **B03.03** Complete subscription lifecycle and plan limits; accurately label manual payment/invoicing if no approved payment provider exists.
- [ ] **B03.04** Build agency suspension, cancellation, data export, retention and support escalation paths without cross-tenant access.
- [ ] **B03.05** Ensure tenant, owner and contractor invitations use the correct agency URL, roles and expiry/revocation controls.
- [ ] **B03.06** Run automated new-agency bootstrap and offboarding with independent database/file isolation, including backup and restore.

**Bundle acceptance (DONE):** Two newly provisioned agencies can operate independently, onboard all roles and follow a documented billing/admin lifecycle.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


### B04 — Existing agency import, export and migration

**Depends on:** B01, B02, B03  
**Starting point:** Dry-run CSV for people/properties/tenancies implemented; history/documents/money still missing

- [ ] **B04.01** Add guided CSV templates and preview for owners, joint owners, renters, applicants, properties/rooms, current tenancies and mandates.
- [ ] **B04.02** Extend mapping to historic repair cases, jobs, inspection evidence, documents, rent ledger transactions, deposit schemes and prior statements.
- [ ] **B04.03** Detect duplicates without merging different people merely because they share an email/phone; require reviewed decisions.
- [ ] **B04.04** Dry-run full totals, financial balances, linked relationships and document availability, with a downloadable exception report.
- [ ] **B04.05** Make production-like PostgreSQL import transactional and idempotent; verify no portal activation or listing publication by default.
- [ ] **B04.06** Implement selective export, archive/history exports and source reconciliation for agency departure and GDPR subject-access.
- [ ] **B04.07** Prove rollback from an encrypted pre-import backup on a stopped isolated copy.

**Bundle acceptance (DONE):** A realistic agency dataset can import, reconcile to source totals, export and restore without missing/duplicated records or unauthorised access.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


## II. Lettings lifecycle

### B05 — Landlord onboarding and management authority

**Depends on:** B01, B02, B03  
**Starting point:** Owner enquiry and property onboarding/approvals partially built

- [ ] **B05.01** Finish landlord enquiry, follow-up, identity/ownership evidence, role and joint-owner approval.
- [ ] **B05.02** Track property surveys, landlord/agency agreements, mandate start/stop dates and tenant-find-only versus fully managed services.
- [ ] **B05.03** Capture recurring agency fees, VAT applicability, spending thresholds, emergency authority and bill approvals.
- [ ] **B05.04** Associate multiple properties with one owner and multiple owners with one property without access leakage.
- [ ] **B05.05** Provide landlord portal for submissions, outstanding evidence, property status, approvals, contract documents and contact history.
- [ ] **B05.06** Test new/declined/incomplete/terminated mandates and audit changes to authority and fees.

**Bundle acceptance (DONE):** A new landlord can become an authorised managed client with verifiable property links, terms, permissions and portal visibility.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


### B06 — Property readiness and rental listing

**Depends on:** B05, B17  
**Starting point:** Listings and landlord-to-agent approval exist; publication policy partial

- [ ] **B06.01** Complete property/unit details, availability, rent period, address, photographs, accessibility/amenities and agent contact information.
- [ ] **B06.02** Gate publication on owner authority and the applicable property documents/certificates/licensing review.
- [ ] **B06.03** Implement draft → agent review → advertised → let agreed → occupied/withdrawn transitions with dates and history.
- [ ] **B06.04** Enforce asking-rent visibility and prohibit workflows that solicit or accept unlawful rental bidding.
- [ ] **B06.05** Finish public mobile rental search, filters, property detail pages and accurate contact forms.
- [ ] **B06.06** Ensure listing changes propagate to tenant/landlord/agent views while private notes and documents stay private.
- [ ] **B06.07** Test withdrawn, already-let, unavailable, duplicate and concurrent-applicant listing states.

**Bundle acceptance (DONE):** Only authorised, complete, approved rental adverts are public; enquiry and listing state survive a real browser reload.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


### B07 — Applicant leads and rental viewings

**Depends on:** B06, B19  
**Starting point:** Prospect/appointment records exist; journey partial

- [ ] **B07.01** Create one applicant record per consenting person, linked to rental enquiry and desired property.
- [ ] **B07.02** Implement enquiry ownership, qualification fields, communication preferences and non-discriminatory manual review.
- [ ] **B07.03** Provide viewing availability, agent/tenant-approved time slots, confirmations, cancellations, reschedules and no-shows.
- [ ] **B07.04** Record viewing feedback, follow-up reminders, decision stage and property-interest history.
- [ ] **B07.05** Support safe rental-property matching and shortlists without exposing other applicants.
- [ ] **B07.06** Verify duplicate leads, unavailable dates, cancelled appointments and mobile applicant flows.

**Bundle acceptance (DONE):** A rental enquiry can be tracked through a real viewing and agent follow-up without duplicate people or calendar contradictions.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


### B08 — Rental applications, referencing and tenancy conversion

**Depends on:** B07, B09, B10, B18  
**Starting point:** Tenancy/people models exist; complete referencing-to-tenancy path not demonstrated

- [ ] **B08.01** Build an application form with occupants, guarantors, required consent and configurable review steps.
- [ ] **B08.02** Record referencing provider handoff/results without fabricating checks or storing excessive sensitive data.
- [ ] **B08.03** Keep lawful holding-deposit handling separate from the tenancy security deposit and protect fee/rent-request boundaries.
- [ ] **B08.04** Capture rental offer/acceptance at permitted asking rent; reject double allocation and overbooking.
- [ ] **B08.05** Prepare agreement/e-sign handoff or independently documented manual signing and identity checks.
- [ ] **B08.06** Convert an accepted applicant into an assured periodic tenancy using existing IDs, preserving documents and application history.
- [ ] **B08.07** Run negative/withdrawn/rejected, co-tenant, guarantor and accepted-to-move-in browser journeys.

**Bundle acceptance (DONE):** Enquiry → application → reviewed referencing/holding deposit → signed tenancy reuses canonical records, with no duplicate applicant or unlawful automatic commitment.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


### B09 — 2026 periodic tenancy lifecycle

**Depends on:** B01, B08  
**Starting point:** Assured-periodic validators, rent proposals and pet requests exist; full transitions incomplete

- [ ] **B09.01** Audit old fixed-term, end-date and renewal assumptions in code, UI, reports, tasks and imported records.
- [ ] **B09.02** Implement appropriate England assured-periodic lifecycle and separate flagged legacy/excluded tenancies.
- [ ] **B09.03** Track occupants, rental period, permitted rent increases, Form 4A service evidence, disputes and effective dates.
- [ ] **B09.04** Complete right-to-rent evidence, follow-up dates and staff-only access controls.
- [ ] **B09.05** Support tenant pet requests with written reason/response deadlines and agent decision history.
- [ ] **B09.06** Implement lawful notice records, ending/possession routes requiring human legal review, surrender and checkout.
- [ ] **B09.07** Test legacy conversion, notices, objections, joint tenants, multiple rent periods and history preservation.

**Bundle acceptance (DONE):** All tested tenancy states comply with the agreed rule model, never invent a renewal/fixed end, and keep legal actions behind human review.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


## III. Finance

### B10 — Holding deposits, tenancy deposits and disputes

**Depends on:** B08, B09  
**Starting point:** Separate deposit models, cap/deadline/evidence tests and tenant screens exist; full return/dispute handling partial

- [ ] **B10.01** Complete receipt status distinction: recorded, evidenced/reconciled, protected, refunded, applied and disputed.
- [ ] **B10.02** Enforce holding-deposit limits, permitted retention/return, decision deadlines and audited tenant consent.
- [ ] **B10.03** Track tenancy security deposit cap, actual protection scheme, reference, statutory protection/prescribed-info evidence and late flags.
- [ ] **B10.04** Add tenant-visible scheme details, attachments when authorised, dispute pathway and checkout deductions/return evidence.
- [ ] **B10.05** Prevent duplicate deposit records, double refunds, silent deletion or reuse of someone else's evidence.
- [ ] **B10.06** Test partially returned and disputed deposits, tenancy replacements, old deposits and deadline escalations.

**Bundle acceptance (DONE):** Each tenant deposit has an auditable full lifecycle, accurate deadlines and owner/tenant visibility, with no false payment or scheme-verification claims.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


### B11 — Rent charges, receipts and arrears

**Depends on:** B09, B10  
**Starting point:** Rent ledger and human statement-matching partial; money integration not accepted

- [ ] **B11.01** Generate recurring charges for weekly/fortnightly/monthly tenancy periods and applicable effective rent changes.
- [ ] **B11.02** Handle partial, late, over, skipped and duplicated receipts in exact integer pence.
- [ ] **B11.03** Record charges/credits, arrears ageing, adjustments and reasoned reversal entries without editing historical truth.
- [ ] **B11.04** Add evidence-linked bank CSV matching and multiple candidate handling; never call unverified receipts reconciled.
- [ ] **B11.05** Support safe statement import, manual review of payer identity and reconciliation exceptions.
- [ ] **B11.06** Maintain landlord/property/tenancy segregation across ledgers and exports.
- [ ] **B11.07** Test leap dates, concurrency, late rent increases, multiple periods, small rounding cases and monthly totals.

**Bundle acceptance (DONE):** Rent balances and ageing reconcile exactly across ledger, agent, tenant and export, with a traceable evidence chain for every receipt.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


### B12 — Landlord accounts, fees and statements

**Depends on:** B11, B14  
**Starting point:** Snapshot statements/invoices exist; full reconciliation and accounting review missing

- [ ] **B12.01** Define service fee schedule, commission, VAT rules where applicable, billable services and manual overrides with approval.
- [ ] **B12.02** Attach contractor quotes/invoices/credits to property, job, owner authority and accounting period.
- [ ] **B12.03** Generate period-based owner statement with opening balance, charges, tenant receipts, agency fees, expenses, credits and closing balance.
- [ ] **B12.04** Record landlord disbursement instructions and external payment evidence without performing bank transfers.
- [ ] **B12.05** Export statements with correct tax labels and supporting evidence; make appropriate details visible in landlord portal.
- [ ] **B12.06** Provide accounting integration/export boundaries; no assertion that Roger is a regulated client-money or banking system.
- [ ] **B12.07** Test exact-pence arithmetic, joint owner splits, late supplier invoices, credits, reversals and access denial.

**Bundle acceptance (DONE):** An agency can explain every figure on a landlord statement; summaries match source records and have accounting-review evidence.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


## IV. Property operations

### B13 — Tenant repair reporting and safety triage

**Depends on:** B01, B02, B19  
**Starting point:** Repair interview, evidence dossier and four-role browser journey implemented

- [ ] **B13.01** Finish tenant self-service fault report with structured category, location, urgency, photos, access instructions and review before sending.
- [ ] **B13.02** Add duplicate problem detection, follow-up to existing case and genuine human choice to merge or keep separate.
- [ ] **B13.03** Apply conservative emergency rules for gas, carbon monoxide, electrical danger and water leaks, with safe, location-appropriate instructions.
- [ ] **B13.04** Make dangerous cases prioritised but never falsely claim emergency dispatch or a definitive diagnosis.
- [ ] **B13.05** Record report, diagnosis provenance, timeline, SLA/next actor and tenant-visible status without leaking private contractor/owner data.
- [ ] **B13.06** Test unanswered questions, attachments, corrupted uploads, repeated requests, no-model fallback and unrelated tenant access.

**Bundle acceptance (DONE):** Every issue creates one appropriate linked case and receives safe handling; report/priority/history remain correct across portals.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


### B14 — Contractor jobs, landlord authority and completion

**Depends on:** B05, B13, B12  
**Starting point:** Quote/approval/work order/visit/invoice skeleton and some four-role tests exist

- [ ] **B14.01** Complete contractor registration, credentials, insurance/service area and renewal checks before assignment.
- [ ] **B14.02** Support suitable contractor invitation, acceptance/decline and multiple competing quotations.
- [ ] **B14.03** Apply owner spending limits, explicit authority/approval and contractor variations with a non-bypassable audit chain.
- [ ] **B14.04** Implement appointments, access/no-access, missed/late work, parts delays, rescheduling and evidence upload.
- [ ] **B14.05** Track completed work, tenant acknowledgement/reopening, independent agent acceptance and contractor invoice/credit.
- [ ] **B14.06** Prevent duplicate jobs, double invoicing, stale-authority approvals, contractor access to unassigned properties and status divergence.
- [ ] **B14.07** Run full positive and negative four-role browser tests covering each exceptional branch.

**Bundle acceptance (DONE):** The full repair lifecycle and its exceptions work with proper human approval, evidence and accurate invoices.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


### B15 — AI diagnostics, vision and agent suggestions

**Depends on:** B13, B14, B20  
**Starting point:** Real small Ollama text test passed; genuine vision inference NOT demonstrated

- [ ] **B15.01** Run an actual compatible vision model on representative consent-free synthetic fault images; evaluate observed evidence, uncertainty and failures.
- [ ] **B15.02** Compare text, photo, no-model and model-timeout behaviour against the same structured fault scenarios.
- [ ] **B15.03** Build grounded source-linked defect summaries, probable trade/parts suggestions and owner/contractor handoff without overstated diagnosis.
- [ ] **B15.04** Create reproducible safety benchmark sets for dangerous/non-dangerous faults and inspect false-negative patterns.
- [ ] **B15.05** Add bounded input/response size, runtime budget, model provenance, rate limits, prompt-injection defences, privacy/retention and consent.
- [ ] **B15.06** Keep every external communication, quote, spending decision, legal interpretation and emergency escalation under human control.
- [ ] **B15.07** Log feedback and refusals so model behaviour can improve without exposing tenant private data.

**Bundle acceptance (DONE):** Real text and image inference plus safe fallback pass independent browser and safety evaluations; provenance/limitations are visible.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


### B16 — Inventories, inspections and keys

**Depends on:** B09, B18  
**Starting point:** Rooms, meters, keys and disputed issued inventory implemented; complete inspection/compare flow partial

- [ ] **B16.01** Complete scheduled pre-let, check-in, mid-term, checkout and repair-related property inspections.
- [ ] **B16.02** Capture room-by-room condition, time-stamped photographs, meter readings, serials, equipment details and key/access log.
- [ ] **B16.03** Version evidence and issue immutable tenant/landlord-visible inventories with controlled acknowledgements and disputes.
- [ ] **B16.04** Produce check-in versus checkout condition comparison and a clear dispute/evidence report for deposit review.
- [ ] **B16.05** Support multiple tenants, tenant refusal/non-response and agent-approved corrections through new dated versions.
- [ ] **B16.06** Test evidence download rights, missing photos, time zone/date accuracy, multiple rooms and mobile photographic upload.

**Bundle acceptance (DONE):** An agent can inspect at move-in, compare at checkout, account for keys and give both sides a usable auditable record.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


### B17 — Property compliance, complaints and policy dates

**Depends on:** B05, B09, B16  
**Starting point:** Certificates, regional PRS registration reminders and licensing categories exist; rules incomplete

- [ ] **B17.01** Define property-type and relevant council policy applicability without automatically certifying compliance.
- [ ] **B17.02** Finish evidence and expiry records for gas, electricity/EICR, EPC, alarms, safety visits, licensing and contractor credentials.
- [ ] **B17.03** Track HMO/additional/selective licence numbers, agents' redress/CMP status where applicable, PRS registration details and changing effective dates.
- [ ] **B17.04** Complete right-to-rent evidence, follow-up dates, privacy controls and responsible person assignment.
- [ ] **B17.05** Build repair/tenancy complaints, acknowledgement, investigation, escalation, resolution and audit history.
- [ ] **B17.06** Link missing/expired documents to priority tasks, reminders, property readiness and issue assignment gates.
- [ ] **B17.07** Obtain qualified UK legal/property-management review of legally sensitive rules and test boundary dates/exception cases.

**Bundle acceptance (DONE):** Each relevant property has accurate evidence-backed obligations, due work and a traceable complaints process; legal assumptions documented and reviewed.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


## V. Communications & intelligence

### B18 — Documents, signatures and safe sharing

**Depends on:** B01, B02  
**Starting point:** Document records/share roles exist; complete evidence and agreement handoffs partial

- [ ] **B18.01** Enforce upload size, MIME type, image integrity, file sanitisation/malware scanning and stored filename safety.
- [ ] **B18.02** Associate every attachment with authoritative agency/property/tenancy/person/job/invoice plus purpose and visibility.
- [ ] **B18.03** Restrict sensitive identity/bank statements to permitted roles, including links, direct downloads, emails and exports.
- [ ] **B18.04** Complete document versioning, retention, correction, supersession, revocation and download audit.
- [ ] **B18.05** Support tenancy/management agreement signatures via an authorised integration or explicitly labelled manual external signing evidence.
- [ ] **B18.06** Provide tenant/landlord/trades document timelines and evidence requests with secure mobile upload.
- [ ] **B18.07** Test unauthorised download, guessed IDs, malicious filename, cross-agency uploads, duplicate versions and missing signature.

**Bundle acceptance (DONE):** Documents remain accessible only to intended parties, with immutable/reviewable version history and completed lawful agreement handoff.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


### B19 — Communications centre and delivery

**Depends on:** B02, B18  
**Starting point:** Some threads and email plumbing; real provider delivery/retry not verified

- [ ] **B19.01** Create one timestamped communication timeline linked to agency, property, tenancy, case, task and person.
- [ ] **B19.02** Separate agent internal notes from tenant/landlord/trades-visible messages and protect attachment access.
- [ ] **B19.03** Finish consent/preferences, email templates, recipient validation, sender identity and reply threading.
- [ ] **B19.04** Connect and test a supported mail provider for real test-account send, receipt, rejection and bounced-message handling.
- [ ] **B19.05** Add reliable outbox delivery records, provider message IDs, retry/reconciliation and dead-letter review without duplicate sends.
- [ ] **B19.06** Notify the appropriate actor on key property, booking, maintenance, deposit and compliance events.
- [ ] **B19.07** Test sender/recipient disclosure, all four portals, opt-out where applicable, failed delivery, duplicates and data retention.

**Bundle acceptance (DONE):** An agent can see exactly what was sent, delivered, refused or requires follow-up, with correct recipient and privacy boundaries.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


### B20 — Scheduler, reminders and office automations

**Depends on:** B17, B19  
**Starting point:** Event-triggered tasks exist; reliable scheduler/queue incomplete

- [ ] **B20.01** Create a durable scheduled-job engine for reviews, inspections, case follow-ups, payment reminders and compliance expiry.
- [ ] **B20.02** Define event triggers, effective time zones, due dates, escalation owner, snooze, completion and cancellation semantics.
- [ ] **B20.03** Use durable idempotency keys, retries/backoff, bounded concurrency and dead-letter handling on dispatch.
- [ ] **B20.04** Preserve history through server restart, duplicate webhook events, temporary provider outages and staff handovers.
- [ ] **B20.05** Allow each agency to configure safe alert channels and operating hours without bypassing required compliance reminders.
- [ ] **B20.06** Keep AI suggestions and system actions distinct; require agent approval for legal, financial and externally binding actions.
- [ ] **B20.07** Test job execution exactly once under repeated requests, crash/restart, clock changes, missing data and disabled accounts.

**Bundle acceptance (DONE):** Due work happens reliably, is accountable, survives failures and never silently duplicates customer messages or financial actions.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


### B21 — Agent Desk, search and management reporting

**Depends on:** B09, B12, B14, B17, B20  
**Starting point:** Read-only priority feed built; cross-module executive reporting partial

- [ ] **B21.01** Join all authorised work into a priority dashboard: new leads, viewings, arrears, overdue repairs, compliance, invoices, approvals and tasks.
- [ ] **B21.02** Provide permission-filtered search across people/properties/cases/tenancies with source links and current status.
- [ ] **B21.03** Show clear responsible actor, due date, source evidence, next step, urgency and whether an item is unverified.
- [ ] **B21.04** Build useful occupancy, void periods, average repair ageing, arrears, rent collection, pipeline and staff workload reports.
- [ ] **B21.05** Add date/agency/property filters and CSV/PDF export with reconciliation against raw records.
- [ ] **B21.06** Preserve form drafts during automatic refresh and never hide error, empty-state, partial-data or slow-network conditions.
- [ ] **B21.07** Test every KPI with known synthetic expected totals and confirm no cross-agency or forbidden personal data leaks.

**Bundle acceptance (DONE):** An agent can manage a typical day's work from one dashboard with traceable, accurate numbers and working action links.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


### B22 — Integrations, operator tools and service limits

**Depends on:** B03, B19, B21  
**Starting point:** Email/integration settings partial; broad provider support not built

- [ ] **B22.01** Document an authenticated permission-scoped integration/export API with versioning, rate limits and secret management.
- [ ] **B22.02** Finish configurable agency integrations (mail, referencing, e-sign, accounting) only when real provider access and terms are available.
- [ ] **B22.03** Use explicit manual handoffs where no authorised connection exists; never impersonate provider integration.
- [ ] **B22.04** Set agency-level feature availability, quotas, worker/model limits and support diagnostics suited to available hosting.
- [ ] **B22.05** Build non-tenant-facing operator support for agency health, suspension/recovery, usage, billing records and incident access logs.
- [ ] **B22.06** Test API version compatibility, revoked credentials, disabled provider, rate limits and cross-agency denial.

**Bundle acceptance (DONE):** All claimed integrations are real and monitored; every unsupported provider has a clear manual pathway and no misleading UI.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


## VI. Independent acceptance & release

### B23 — Security, privacy and legally sensitive review

**Depends on:** B01–B22 implemented  
**Starting point:** Some isolation/authentication tests; full audit and external sign-off absent

- [ ] **B23.01** Perform endpoint/role/record access matrix audit, privilege escalation, CSRF, injection, file upload, secrets and session review.
- [ ] **B23.02** Scan vulnerable dependencies and test log redaction, storage encryption, secret rotation and least-privilege infrastructure.
- [ ] **B23.03** Review GDPR/UK GDPR purpose limitation, applicant consent, privacy notice, subject access/export, deletion versus lawful retention.
- [ ] **B23.04** Verify consented processing for images/AI model data, provider data transfers, opt-out and retention controls.
- [ ] **B23.05** Independently review England letting, tenancy, deposit, property compliance and regulated client-money representations with qualified professional advice.
- [ ] **B23.06** Resolve all critical/high findings and record residual limitations, sign-offs and known unsupported circumstances.
- [ ] **B23.07** Run realistic cross-agency attack and confidentiality checks, including backup/export and internal admin access.

**Bundle acceptance (DONE):** No open critical/high security issues; legal/accounting review evidence exists for sensitive functions; privacy and agency isolation pass.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


### B24 — Full desktop, Android browser and accessibility acceptance

**Depends on:** B05–B22 implemented  
**Starting point:** Public mobile layout and some portal browser flows tested; full usability not accepted

- [ ] **B24.01** Run every agreed journey from a fresh browser session as agent, landlord, applicant/tenant and contractor.
- [ ] **B24.02** Test Android-width and desktop responsiveness: navigation, labels, form validation, buttons, dialogs, uploads and downloads.
- [ ] **B24.03** Test keyboard focus, contrast, screen-reader names, actionable status messages, tables and modal dismissal.
- [ ] **B24.04** Test lost network, slow model, timeout, refresh, stale form, duplicate submits, reopening, session expiry and error recovery.
- [ ] **B24.05** Ensure automatic refresh never overwrites active form edits or silently drops data; maintain scroll and focus safely.
- [ ] **B24.06** Run automated accessibility checks plus manual interaction tests on representative devices/browsers.
- [ ] **B24.07** Fix broken links, dead-end pages, placeholders and inconsistent status labels before acceptance.

**Bundle acceptance (DONE):** Each important journey passes recorded browser tests at desktop and Android sizes, with usable errors and no core accessibility blocker.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


### B25 — Integrated cross-agency release simulation

**Depends on:** B00–B24  
**Starting point:** 503 Python tests, Chromium repairs/tenancy/deposits and 2-agency CI passed; complete v1 journey not yet tested

- [ ] **B25.01** Freeze one exact release-candidate commit and run unit, integration, lint/static, browser, AI and infrastructure tests on it.
- [ ] **B25.02** Use realistic synthetic two-agency fixtures: joint owners, multiple properties, co-tenants, guarantors, contractors and linked bank/repair data.
- [ ] **B25.03** Run landlord acquisition → rental listing → viewing → referencing → accepted tenancy → move-in → charges/maintenance → checkout.
- [ ] **B25.04** Run full finance cases with due/late/partial/reversal, statement matched/unmatched, owner fees, contractor expense and deposit dispute.
- [ ] **B25.05** Run serious repair/safety/vision failures, quote rejection, stale approvals, no-access, reopened cases and end-of-job sign-off.
- [ ] **B25.06** Run failed/duplicate communication jobs, licence/certificate expiry, account suspension, lost sessions and cross-tenant/API denials.
- [ ] **B25.07** Produce requirements-to-tests matrix, defects with severity, external review outcomes and accepted/rejected cases for every one of the 12 modules.

**Bundle acceptance (DONE):** One identical build passes the entire signed-off 12-module acceptance matrix and no P0/P1 defect is open.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __


### B26 — Production-like operations, backup, rollback and one deployment

**Depends on:** B25 passed, professional reviews complete  
**Starting point:** Backup/recovery scripts exist; production-like rollback/4 GB VPS capacity not accepted; no deployment

- [ ] **B26.01** Inspect target Hostinger resource limits, CPU/memory/disk, PostgreSQL volumes, TLS, domains and model/integration service budgets.
- [ ] **B26.02** Build an isolated production-like clone from an actual current backup and document restore integrity and downtime requirements.
- [ ] **B26.03** Rehearse encrypted off-host backup, safe schema/data migration, rollback and recovery with recorded checksums.
- [ ] **B26.04** Perform load, concurrency, stress, disk-full and restart tests against target constraints without touching live customers.
- [ ] **B26.05** Configure monitoring, alerts, operator health checks, retention, error logs and incident response/runbook.
- [ ] **B26.06** Check all release evidence, prepare a single reviewed deploy artifact and final preflight/rollback decision.
- [ ] **B26.07** Only after every gate passes, back up live state, deploy Roger v1.0 ONCE, run post-launch smoke on all portals and verify no data loss or role crossover.
- [ ] **B26.08** Keep exact previous working build and a demonstrated reversible rollback plan; document any actual postlaunch issue separately.

**Bundle acceptance (DONE):** Production can run safely at target capacity, recover from a proven backup, and the one approved version is deployed and verified without loss of previous data.

**Evidence:** commit __ · Python tests __ · Chromium/integration run __ · acceptance __ · open blockers __



## Final release gate — must be 12/12 PASS on the same exact build

- [ ] **Gate 01** All four connected portals plus public rental marketing use the same correct agency/property/tenancy records.
- [ ] **Gate 02** Landlord → property → advert → applicant/viewing → referencing → periodic tenancy → move-in/checkout passes.
- [ ] **Gate 03** Tenant reporting → safety/AI triage → contractor/owner authority → visit → evidence → settlement passes.
- [ ] **Gate 04** Money/deposits, client-money limitations and owner statements reconcile with exact amounts and evidence.
- [ ] **Gate 05** Compliance/registration/complaints/certificates, expiry reminders and specialist review pass.
- [ ] **Gate 06** Reliable reminders, mail delivery, retry, backoff, dead letters and duplicate prevention pass.
- [ ] **Gate 07** Real text and vision model evaluations, auditable provenance, safe fallback and human oversight pass.
- [ ] **Gate 08** Endpoint/document/export/notification privacy, identity, agency isolation and security audit pass.
- [ ] **Gate 09** All four portals and applicant flow are usable on desktop and Android-width browsers and accessible.
- [ ] **Gate 10** Automated regression, concurrency/load, restored clone, monitoring and incident workflows pass.
- [ ] **Gate 11** Agency onboarding/billing/export/support, permitted integrations and lawful notices/agreements are production-ready.
- [ ] **Gate 12** Verified off-site backup, tested restore/rollback, explicit final release sign-off, ONE deploy and postlaunch smoke pass.

**Release rule:** No production deployment until *every* gate is evidenced. If a gate cannot be met, keep the single development branch open and the live Roger unchanged.

## Deferred / explicitly OUT OF SCOPE

Property sales, buyer/vendor accounts, conveyancing/sales chains, property auctions, commercial property, foreign legal regimes, block/leasehold management, native Android/iOS applications when the mobile site suffices, unsupported Rightmove/Zoopla syndication, direct bank transfers, automated legal/possession decisions, custom IoT, a general AI swarm, or any integration without authorised provider access.

## Future working instruction

Say **“Start B00”** (or another dependency-ready bundle) to work on exactly that bundle. Implement its tasks, run relevant and global regression tests, fix failures, and record acceptance in this file; do not request a new product specification and do not deploy interim builds.
