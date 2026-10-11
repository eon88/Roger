# Roger repairs pilot — build/test handoff
Updated 11 October 2026 · Working branch: `feature/roger-fast-mvp-20261011`

## Scope
Focused England-first small-agency pilot. The repair process is built in stages and tested with synthetic cases. These are not a legal-compliance certificate or permission to handle real client money.

## Completed and code-tested
- [x] Tenant reports create a private case with evidence, not an immediate public job. Only an agent can review and dispatch a case, with a required reason. Repeated dispatch is blocked.
- [x] Agent sends quote request to an approved, account-linked trades Party. New work cannot be directly assigned or self-claimed without approval.
- [x] New repair quotes are approved **before** work starts. A signed active full-management mandate tied to the real property owner supplies that property's spending limit; a quote over it requires that landlord's explicit approval. Changes to the mandate invalidate pending owner approval.
- [x] Contractor identity for a new repair is resolved by linked Party ID, approved registration, checked credentials, relevant trade and current insurance. Revalidate before approval/start. Suspended/unlinked/expired contractors are blocked. An unverified claimed Gas Safe number does not authorise a gas job.
- [x] The contractor may start only when pre-work approval is recorded. An invoice above the approved amount is refused pending a separately approved variation process (not built yet).
- [x] Work completion, tenant confirmation/reopening, invoice submitted, invoice approved and **manually recorded external payment** are separate. An invoice cannot become paid merely because the agent or landlord approved it. No payment provider is connected.
- [x] Tenant, landlord and trades screens now reflect the main revised states.
- [x] Removed fictitious tenant email, office phone/email, fake verified gas engineer, and false emergency response-time promises from the pilot screens.
- [x] Synthetic four-role back-end end-to-end test; property-isolation and denial tests; existing four-role browser smoke.

## Task 01 — appointment and property access implementation (11 October 2026)

**Development only; not deployed.** This step is **partly accepted** pending the dedicated full browser journey and access-policy review.

- [x] Assigned and authorised contractor can propose a real job-linked visit; a second active visit is rejected.
- [x] Tenant explicitly accepts or requests a new time, including after a previous confirmation; rescheduling cancels earlier contact/access consent.
- [x] Wrong tenant, landlord, unrelated contractor or trade cannot confirm on behalf of the resident.
- [x] Agent has an accurate diary; contractor sees confirmed times and only consented access preferences; no key codes or entry credentials are collected.
- [x] Missed/no-access and parts-delay outcomes require a reason and do **not** complete the job, submit an invoice or close the repair.
- [x] Work authorisation is rechecked before confirming or changing a contractor visit; withdrawn approval blocks the visit.
- [x] New role, cross-property, wrong-job, time validation, consent, reschedule and delay regression tests. Standard Python tests and the existing four-role portal browser smoke pass.
- [ ] Run the dedicated full visit browser test (`node tests/visit_browser_smoke.cjs`) in isolated CI and record the run link. The script exists, but it is **not yet wired into the GitHub Actions workflow**; an attempted workflow edit was blocked. The existing browser smoke does not cover the full visit journey.
- [ ] Office review: confirm acceptable access instructions, tenant contact consent and any safe, offline key handover process. Never store lockbox codes in general appointment notes.

**Current status:** built on the feature branch with regression coverage; awaiting full browser proof and office acceptance. Do not call Task 01 DONE or proceed to Task 02 until those gates are met.

## Task 02 — case tracking implementation (11 October 2026)

**Built and regression-tested on the development branch. No production changes.**

- [x] Each new tenant repair or public enquiry starts with one **agent** next action and a dated internal tracking target. This is an office target, **not** a tenant response-time promise.
- [x] Agent can assign one named *role* (agent, linked tenant, linked landlord or assigned contractor), next action and valid future/today due date to an open case.
- [x] Existing repair job and invoice state changes update the case's next role/action and tracking date; closed cases lose active next steps.
- [x] Agent Desk shows the next actor/action/date, and includes waiting cases and overdue cases in attention views.
- [x] Report retries can use a client-generated idempotency key; the same signed-in owner/property/key and identical report returns the same case number instead of producing a duplicate.
- [x] Tenant and landlord scoped stage responses strip **internal_notes** entirely; shared threads still obey their audience lists.
- [x] Reopening a completed repair requires a resident's explanation, retains history and reassigns agent follow-up. It cannot be repeatedly reopened while still reported.
- [x] Synthetic role, isolation, idempotency, stage-transition, deadline and internal-notes regression tests; normal four-role browser smoke runs separately.
- [ ] **Remaining:** near-simultaneous duplicate submissions/concurrent writes require transactional storage controls (Task 06). Same-wording reports with *different* request IDs are not auto-merged; the agent still needs a manual duplicate decision.
- [ ] **Remaining:** verify next-step assignment on older/legacy open cases, named staff assignees, overdue escalations/reminders, disputes across every path and a fully populated multi-role browser acceptance journey.

**Status: PARTIAL / code-tested; not fully accepted.** Do not silently mark Task 02 DONE. The user asked to defer the extra Task 01 visit browser test and move on.

## Task 03 — quote, invoice and external payment controls (11 October 2026)

**Status: PARTIAL / implemented and code-tested with synthetic fixtures; NOT deployed or approved to handle client money.**

- [x] Contractor portal sends labour, materials and explicitly chosen VAT rates as itemised quote lines; server validates net/VAT/gross in integer pence and refuses bad totals.
- [x] Quotes retain versions, declared scope and frozen breakdowns. Above-limit owner approval is tied to the exact version, scope, quote amount and current management mandate.
- [x] Extra work uses its own approval. The agent can approve within the full combined spending limit; above it the linked landlord approves the exact extra cost before that extra scope is authorised. Pending variations block invoicing.
- [x] New trades UI asks for supplier invoice number, net amount and VAT. The server checks duplicate supplier invoice numbers for the same contractor across jobs and ensures that itemised totals agree.
- [x] Agent records external payments in separate dated entries and can record supplier credits by number and reason. Part-payments leave a balance; all-credit settlements are credited, never falsely bank-paid.
- [x] Agent and landlord views distinguish approved invoices, actual external payment references, credits and outstanding balances. Owner statement snapshots count external entries by payment date, not gross invoice face value.
- [x] Python financial regression tests cover line arithmetic, quote revisions, authority, variations, duplicate numbers, credits, part-payments and statement figures.

**Still required:**

- [ ] Human check of supplier invoice/credit-note evidence and accounting/VAT rules. Legacy API submissions without itemisation or a supplier number are still allowed for compatibility, but flagged as incomplete.
- [ ] Transaction-safe concurrent updates, including duplicate invoices and external receipts (Task 06). The shared JSON snapshot storage is not financial-grade.
- [ ] A dedicated populated four-role browser finance journey, not just general login/property-submission smoke.
- [ ] Independent reconciliation against real bank records; Roger does not verify, receive or transfer money.

**Release:** Remains in draft PR #5; no live Hostinger deployment, no payments integration.

## Task 04 — verified contractor evidence and service area (11 October 2026)

**Status: PARTIAL — security gates, agent review UI and synthetic tests implemented on the feature branch. No production release.**

- [x] **Fail closed for new repairs**: a 'checked' onboarding stage, approved registration, insurance date, or applicant-claimed Gas Safe number alone does not authorise dispatch. Roger now requires a linked active trades Party/account and a current, agent-recorded independent check supported by **two separate agent-verified trades documents** (insurance and qualification).
- [x] Agent records separate insurer and qualification source/reference, checked-by/date, checked trade categories, finite review expiry, and confirmed service areas or outward postcode codes. Only the agent can create/revoke that record; the original documents stay in the private library.
- [x] Live checks on every new quote/dispatch, work start, authorisation, landlord approval and variation: block suspended, unlinked, expired, replaced/rejected evidence, missing current insurance, changed registered trades and out-of-area work.
- [x] Regulated gas work additionally requires a separate current Gas Safe evidence document and manual independent register lookup reference; legacy in-memory claimed credentials are not sufficient on legacy regulated booking routes either.
- [x] Revocation instantly blocks new eligibility. Renewal preserves the old verification record in history; source and document changes invalidate the old verification. The Agent Desk shows upcoming review dates, missing/invalid proof, and an office-controlled renewal/revoke form.
- [x] Contractor selection now filters by a verified service area matching the property's locality or outward postcode (backend independently checks again). No postcode prefix guessing.
- [x] Added `tests/test_contractor_verification.py` for direct role denial, independent source records, cross-Party evidence rejection, document expiration/replacement, gas registration proof, date limits, exact postcode matching, trade-scope changes and revocation; refreshed existing synthetic repair/test fixtures.

**Still required before claiming the entire area accepted:**

- [ ] Actually inspect genuine supplier/insurer/Gas Safe/other register records and supporting documents. **The agent records an attestation; Roger does not connect to or certify an outside issuer.** No real contractor has been automatically checked.
- [ ] Check jurisdiction-specific regulated qualifications, insurance policy scopes/limits and who can legally perform each trade with an appropriately qualified human. The prototype category list is not a legal licensing engine.
- [ ] Contractor self-service upload/renewal and timed notification delivery/retries are not complete; the agency can upload and verify documents via the current admin Documents screen, and review warnings are displayed on the Agent Desk.
- [ ] Full populated browser run of proof upload → manual issuer check → approval → trade acceptance/expiry/revocation; the standard four-role smoke tests do not exercise this specific workflow.
- [ ] Transaction-safe concurrent dispatch and immutable evidence storage validation / restoration (Task 06 / Task 05).

**Release policy:** Draft development branch only. The user previously chose to defer the optional full appointment journey; this contractor browser journey remains a future acceptance gate.

## Task 05 — real office contacts, notifications and access revocation (11 October 2026)

**Status: PARTIAL / code-tested in the development branch. No live release.**

- [x] Agent-only Office contacts screen, saved private draft, explicit publish/unpublish with agent attestations that the telephone/email are real and the out-of-hours/emergency rules were reviewed; version and audit records. Without publication, other roles see a safe generic message referring to signed paperwork, NOT fabricated contacts.
- [x] Tenant, Landlord and Trades pages display only published office phone, email/hours, out-of-hours number/instructions and the reviewed emergency policy. Every page warns that Roger is not a 24/7 emergency response service.
- [x] Notification creation checks account-linked, active recipient Parties; an external email destination must match that recipient's linked Party email (agent outbox uses the published office address). Retry submissions can be deduplicated by request ID.
- [x] Manual email outbox states: queued, externally recorded sent (requires independent message ID/source), failed (record reason and schedule retry), exhausted (three failures), and retry only after its due time. The record includes an audit event and original messages are not cloned during retry.
- [x] High-priority tenant repair reports create one agent-only in-app alert (never an email or an emergency attendance promise); repeated report requests do not create duplicate alerts.
- [x] An agent can disable a linked non-agent portal account and all its active sessions, blocking future login while retaining tenancy/case data. The action is audited and prevents revoking agent rights through this simplified route.
- [x] Synthetic office publishing/denial, notification scoping, manual delivery evidence, retry exhaustion, account revocation and urgent-report tests; standard unit and general four-role browser workflows.

**Still open for full acceptance:**

- [ ] Actually enter and independently check the real agency phone, office hours, out-of-hours provider and reviewed emergency policy. No contact details were invented or published automatically.
- [ ] Integrate a real provider or securely operated mail worker with delivery receipts, failure callbacks and automated retries. **The current outbox is manual only: Roger does NOT send the queued messages.** Failure/retry recording alone is not an email service.
- [ ] Live operational reminders, emergency escalation and human response rota, notification retention/privacy policies, full staff/administrator MFA and recovery.
- [ ] End-to-end disaster backup/restore drill on a disposable clone (including uploaded document files, users and exact state) and transaction-safe/concurrent writes, still needed before production release.
- [ ] Dedicated role-populated browser acceptance test for office settings, failed mail retries and session revocation. The existing general browser smoke does not exercise these journeys.

**Do not deploy without:** backup + restore evidence, real office contacts, operational emergency procedures and user approval.

## Next P0 tasks (NOT DONE)
1. Appointments and access: propose/accept/reschedule/cancel/no-access, contact consent, key instructions and a parts-delay branch. Block misleading “scheduled” statuses.
2. Case control: single next person/action and due date, duplicate reporting/idempotency, internal/private vs shared notes, disputes, reopening after completed work.
3. Financial completion: itemised quotes, VAT, quote version/scope receipt, approved variations, invoice number/duplicate check, partial payments, credits, reconciliation. Keep all money external until a reviewed accounting route exists.
4. Contractor proof: evidence attachments, independent credential check (especially regulated trades), verification expiry, service-area checks and re-review. Gas dispatch remains blocked without explicit verified proof.
5. Office settings and delivery: real agency contact and emergency policy, notifications with failure/retry, audit, account invitations/access revocation, tested restore.
6. Database safety: PostgreSQL currently also uses shared JSON snapshots; implement transaction-safe concurrent updates and verify independent tenancy/agency access at API/file level.
7. True populated browser pilot for all four roles (current browser smoke checks portals and property submissions; the full repair path is unit-tested with synthetic fixtures but not yet with browser clicks).

## Release status
All work here is on the GitHub feature branch. **Not merged or deployed to the production Hostinger Roger.** Release only after security/data checks, fresh backup, passing CI and an explicit production decision. The live application remains on the previous deployed version.
