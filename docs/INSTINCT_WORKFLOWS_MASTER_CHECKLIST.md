# Roger — Instinct AI master workflow checklist

**Updated:** 11 October 2026  
**Working branch:** `feature/roger-fast-mvp-20261011` — **not merged to `main`; not deployed to production**.  
**Source:** User-provided *Roger workflows to build next* (Instinct AI, 11 October 2026), checked against the current [repair pilot progress](REPAIRS_PILOT_PROGRESS.md), [MVP roadmap](mvp/README.md) and [fast-track PR #5](https://github.com/eon88/Roger/pull/5).

## Read this first

- **25 Instinct areas tracked**: **0 fully accepted**, **16 partly implemented**, **9 open/not end-to-end verified**. This is a checklist of broad work areas, **not a claim that no underlying features exist**.
- `PARTIAL` = at least one real piece is reported built or tested, but the full Instinct acceptance test has not passed.
- `OPEN` = still needs a complete, evidenced workflow; screens or isolated functions may already exist.
- Change an item to `DONE` **only** after its complete acceptance check passes with synthetic test data, permissions verified and evidence linked.
- Instinct priorities: **P0** focused repairs pilot and safety, **P1** wider agency operations, **P2** later enhancements. Some P1 invoice pieces are needed in the pilot.
- This tracks the **development branch**, not what is currently live. A successful unit test is not a passed end-to-end browser pilot; neither constitutes legal sign-off.
- **No unreviewed production merges, migrations or deployment**. Keep live Hostinger Roger stable and isolate testing. No real client money processing without separate review.

## Immediate execution order — one small change, test it, then the next

These seven unfinished P0 jobs are taken from `docs/REPAIRS_PILOT_PROGRESS.md` and must be treated as **not done** until checked off:

- [ ] **01 Appointments and access** — offer/accept/change/cancel visit; no-access and parts delay; scoped contact/key handling. *(R4, T3, A2)*
  - [x] Development code: assigned trade proposals, tenant confirmations/change requests, agent diary, no-access/parts-delay reasons, consent scoping and status safeguards.
  - [x] Python regression suite and existing general four-role browser smoke passing at development commits.
  - [ ] Run the new dedicated full browser visit test (`node tests/visit_browser_smoke.cjs`) and link successful evidence.
  - **Deferred at the user's request (11 Oct 2026).** Do not block progress on Task 02; Task 01 remains not accepted.
  - [ ] Office-approved secure access/key handover procedure and acceptance check; **do not mark Task 01 done yet**.
- [ ] **02 Case control** — next person/action and due date, duplicate prevention, notes visibility, reopen/dispute rules. *(A1, S2, T2, T3)*
  - [x] Server keeps a single next actor/action/internal due date for new reports and enquiries and updates it for the common job/approval statuses.
  - [x] Agent Desk editing and attention views; retry-safe tenant report IDs; internal-note read privacy; completed-case dispute/reopen control.
  - [x] Synthetic permissions, privacy, duplicate-token and transition regression tests added in `tests/test_case_control.py`.
  - [ ] Still needed for full acceptance: safe concurrent writes, manual same-issue duplicate handling, legacy-case backfill, automated escalation/real people ownership, fully populated role-based browser verification.
  - **Status: PARTIAL, tested code; not production deployed.**
- [ ] **03 Financial controls** — itemised/VAT quotes, versioned approvals, variations, unique invoice numbers, part payments, credit/reconciliation. *(A2, L2, R3, R5)*
  - [x] Itemised VAT-aware net/gross quotes, quote versions, exact approval snapshots; legacy sums flagged as incomplete.
  - [x] Extra-work approval within mandate or by the linked landlord when the combined amount exceeds authority.
  - [x] Supplier invoice numbers, itemised totals, part-payments, credits, outstanding balance and updated agent/landlord/trades screens.
  - [x] Statements include dated external payment records and exclude credits from bank-payment totals. Synthetic regression tests added.
  - [ ] Remaining: independent supplier/VAT evidence review, concurrency-safe accounting and duplicate prevention, bank reconciliation and fully populated finance browser pilot.
  - **Status: PARTIAL — code-tested but not a live payment or bookkeeping system.**
- [ ] **04 Contractor evidence** — independently checked certificates, uploads, expiry and coverage. *(R1, S2)*
  - [x] New repair authorisation requires a current agent-attested independent verification tied to two distinct, verified contractor documents plus an active approved account.
  - [x] Recorded insurer and qualification source/reference, verified trade list, checked service area, review expiry and revocation/renewal history.
  - [x] Distinct regulated gas evidence/lookup reference required; claimed numbers and legacy booking bypass cannot authorise gas jobs.
  - [x] Dispatch, quote/start, prework/variation approval and trade picker enforce expiry, Party/doc links and exact checked locality; Agent Desk flags missing or soon-expiring proof.
  - [x] Added synthetic permissions, expiry, source references, changed trade, Gas Safe, document replacement and service-area tests.
  - [ ] Still needed: genuine external issuer checks by a trained operator, policy/licence scope review, contractor self-upload and expiry notifications, dedicated browser journey and transactional storage protection.
  - **Status: PARTIAL — built and code-tested, NOT automatically checked against external registers and NOT live.**
- [ ] **05 Office settings and delivery** — real contacts/out-of-hours policy, alerts/retries, audit, user revocation and restore. *(S2, S3, T1)*
  - [x] Agent can save, review, publish or hide actual office phone, email, hours and emergency policy; all four roles receive only published details; missing contacts use paperwork, never invented data.
  - [x] Manual email outbox with Party-address validation, duplicate request IDs, required external sent-message evidence, failure reasons, timed requeue and three-attempt limit; no simulated delivery.
  - [x] Urgent maintenance intake creates one agent-only in-app alert; account revocation invalidates active non-agent sessions and future logins, preserving records.
  - [x] Agent controls, audit entries and synthetic regression tests added to the development branch.
  - [x] Disposable offline file-backend restore rehearsal script + tests validate JSON records, copied checksums and missing/corrupt document rejection (synthetic, no live data).
  - [ ] Remaining: real agency review/publication, actual SMTP/provider delivery + worker/retries, administrator recovery/MFA, real Hostinger backup-restore drill, production resilience and populated browser checks.
  - **Status: PARTIAL — tested code, manual email outbox only, no real contacts configured, not deployed.**
- [ ] **06 Database and tenant isolation** — safe concurrent writes and two-agency/two-tenancy API/document denial tests; PostgreSQL development must remain isolated until reviewed. *(S1, S4)*
  - [x] Serialize the entire modifying HTTP request across Roger file-backed processes with an OS write lock; development PostgreSQL requests use a transaction-scoped advisory lock.
  - [x] Prevent stale GET session cleanup from overwriting newer logins or revocations. Reject reads **and saves** of mixed-agency or incompletely tagged multi-agency snapshots.
  - [x] Regression: four simultaneous processes edit the same JSON snapshot and preserve every update; two independent tenancy/account scopes cannot view foreign records/downloads or reply to another tenant's case. Wrong-agency snapshot/API requests fail closed.
  - [x] Unit tests for a mocked PostgreSQL advisory transaction and lock-aware HTTP dispatch. File backend remains the only runtime concurrency path exercised with real processes.
  - [ ] Still needed: real PostgreSQL concurrent/rollback tests, row-level agency isolation, multi-agency account ownership, coherent writes across different storage systems, operational backup/restore and a populated production-like security pilot. Current PostgreSQL projections are shared global tables; multi-agency hosting is NOT supported.
  - **Status: PARTIAL — safe cooperative writers and legacy one-agency fail-closed checks tested, NOT full multi-agency production isolation or deployment.**
- [ ] **07 Full populated browser pilot** — exercise real clicks across Agent, Tenant, Landlord and Trades for report → approval → trade visit → tenant result → invoice/external payment record. *(All P0 items)*

**Build/test rule for each step:** implement the smallest vertical slice; run regression + denied-action tests; run a genuine role-based browser scenario; verify records survive reload; update this file with evidence; only then move to the next item. If failed, fix before advancing.

## All 25 Instinct work areas

### Shared foundations (S1–S4)

- [ ] **S1 — Shared records and multi-agency isolation** · **P0** · **🟡 PARTIAL**
  - **Already there / tested subset:** Role/account-linked records, server-side sessions and property-isolation/denial tests exist.
  - **Still needed:** Add true agency IDs on every relevant record; test two independent agencies and tenancies, all API/download routes and explicit role switching. Make shared data writes concurrency-safe.
  - **Done when:** Two agencies and two unrelated tenancies cannot read/write each other's objects or attachments, including guessed IDs.

- [ ] **S2 — Identity, evidence and notifications** · **P0** · **🟡 PARTIAL**
  - **Already there / tested subset:** Invites, role-scoped documents, sessions, messages and an audit log exist.
  - **Still needed:** Add password reset, admin MFA, staff revocation, internal versus shared notes, versioned audit evidence, delivery/failure/retry notifications, reminders, next actor and due dates.
  - **Done when:** A revoked user loses access; private notes never leak; failed notifications retry without duplicates; every state-changing action is auditable.

- [ ] **S3 — Operational readiness** · **P0** · **🟡 PARTIAL**
  - **Already there / tested subset:** Previous production release was health-checked and backed up; security work has isolated tests.
  - **Still needed:** Add configurable real office contacts and emergency policy, monitoring, mobile/accessibility review, upload security and size limits, duplicate/stale-write protection, and restore verification for this release.
  - **Done when:** Backups can be restored, repeated clicks create no duplicate work, real contact details are never fabricated and live Roger remains recoverable.

- [ ] **S4 — Privacy, migration and money boundaries** · **P0 / P1** · **🟡 PARTIAL**
  - **Already there / tested subset:** Role-based data restrictions and separated invoice approval versus external payment recording exist.
  - **Still needed:** Document privacy notices, agency data map and retention policy; review landlord/trade exposure. Later: validated import/export, data-subject requests, accounting mapping and reversible reconciliation.
  - **Done when:** Private records remain scoped, retention and deletion decisions are documented, and no simulated balance is presented as protected client money.

### Agent (A1–A6)

- [ ] **A1 — One agent action queue** · **P0** · **🟡 PARTIAL**
  - **Already there / tested subset:** Agent Desk/navigation, tasks/cases and repair status views exist on the development branch.
  - **Still needed:** Create a single actionable inbox with named next actor, next action, deadline, overdue filter and escalation; add duplicate merging, phone-report capture and internal/shared note separation.
  - **Done when:** Every open case has exactly one accountable next actor and due date; reopening/cancelling preserves history.

- [ ] **A2 — Triage, dispatch and cost control** · **P0** · **🟡 PARTIAL**
  - **Already there / tested subset:** Agent-only repair dispatch, linked vetted trades, signed property mandate and quote-before-work spend gates are code-tested.
  - **Still needed:** Add complete quote comparison, VAT-inclusive approval, emergency escalation policy, approved variations, access/visit handling and race-safe assignments.
  - **Done when:** No unauthorised spend or dispatch; changed quote/mandate invalidates approval; emergencies follow reviewed policy rather than silent acceptance.

- [ ] **A3 — Compliance calendar and evidence** · **P0 / P1** · **⬜ OPEN**
  - **Already there / tested subset:** Compliance and document modules exist, but this whole evidence/calendar workflow is not proven.
  - **Still needed:** Track gas safety, EICR, EPC, alarms and applicable licences with reviewed evidence, issue dates, expiry dates, delivery proofs and outstanding repairs. Later automate renewals.
  - **Done when:** Missing/expired evidence appears in agent action queue; a new certificate does not automatically close outstanding remedial work.

- [ ] **A4 — Lettings and tenancy lifecycle** · **P1** · **⬜ OPEN**
  - **Already there / tested subset:** Property submission wizard and agent onboarding decision are browser-tested; that is not a complete tenancy lifecycle.
  - **Still needed:** Connect marketing, enquiries/viewings, application/reference checks, Right to Rent, tenancy agreement, deposit evidence, inventory/keys, notices, move-out and deposit disputes.
  - **Done when:** One tenancy links permitted occupiers/guarantors and records real-world compliance evidence, not checkbox assumptions.

- [ ] **A5 — Rent, arrears and accounts** · **P1** · **⬜ OPEN**
  - **Already there / tested subset:** Some rent-ledger views and manual external payment recording exist; full reconciliation is not verified.
  - **Still needed:** Add scheduled charges, bank import/matching, suspense, part payments, reversals, refunds, arrears, fees, owner statements and bank-confirmed remittance.
  - **Done when:** Every balance and statement ties back to entries; unmatched bank receipts never automatically become paid rent.

- [ ] **A6 — Requests, disputes and reporting** · **P1 / P2** · **⬜ OPEN**
  - **Already there / tested subset:** Generic cases, tasks and reporting surfaces exist; complaint/notice/reporting journeys are not proven.
  - **Still needed:** Add complaint and antisocial-behaviour cases, pet/permission workflows, reviewed rent-change and notice processes, staff cover and deadlines; later portfolio analytics.
  - **Done when:** Complaints escalate independently of repairs; no automatic unlawful rent/possession decision.

### Tenant (T1–T5)

- [ ] **T1 — My home and the right office** · **P0** · **🟡 PARTIAL**
  - **Already there / tested subset:** Tenant role scoping and account-linked records exist; fake report email and stage office details were removed.
  - **Still needed:** Complete tenancy-specific invite/access lifecycle, contact preferences, verified office/out-of-hours information, move-out revocation and unlinked-home help state.
  - **Done when:** Tenant sees only their tenancy, no invented office/contact details, and loses access when their entitlement ends.

- [ ] **T2 — Safe repairs reporting** · **P0** · **🟡 PARTIAL**
  - **Already there / tested subset:** Private repair reports with evidence and agent review/dispatch have synthetic end-to-end tests.
  - **Still needed:** Add structured hazards/categories, urgent guidance reviewed for England, access needs, upload retry, duplicate prevention and reporting receipt/reference.
  - **Done when:** Urgent safety steps appear before normal filing; no false 24/7 promises; reports survive reload and do not duplicate.

- [ ] **T3 — Repair tracking and reopening** · **P0** · **🟡 PARTIAL**
  - **Already there / tested subset:** Repair status, completion feedback and tenant confirmation/reopening are code-tested.
  - **Still needed:** Connect next-update timeline, proposed appointment accept/change/cancel, access/no-access, reminders, dispute/reopen follow-up and due dates.
  - **Done when:** A contractor cannot close an unresolved tenant problem; visit and next-action statuses agree across roles.

- [ ] **T4 — Rent and tenancy paperwork** · **P1** · **⬜ OPEN**
  - **Already there / tested subset:** Tenant document/rent sections exist; full ledger and evidence-driven paperwork journey is unverified.
  - **Still needed:** Add tenant-specific rent schedule and receipts, shared-ledger balances, tenancy/deposit/safety records, acknowledgements and inventory comments.
  - **Done when:** Tenant sees only entitled charges and documents; uploaded paperwork is not labelled as a completed legal step.

- [ ] **T5 — Requests, complaints and moving out** · **P1** · **⬜ OPEN**
  - **Already there / tested subset:** General messages/cases exist; requests, complaints and check-out/deposit journeys are not proven.
  - **Still needed:** Add pet/permission requests, complaints, reviewed notices, move-out inspection, meter/key record, inventory disagreements and deposit dispute tracking.
  - **Done when:** Disagreement remains visible and no software-generated decision claims to be a deposit-scheme ruling.

### Landlord (L1–L5)

- [ ] **L1 — Property mandate and decision rights** · **P0** · **🟡 PARTIAL**
  - **Already there / tested subset:** Signed active property mandates and ownership-linked spending limits govern the tested repair approval path.
  - **Still needed:** Complete co-owner/authorised-decision handling, preferred contractors, reserve/emergency rules, mandate changes and expiry/acceptance screens.
  - **Done when:** Every instruction binds to an effective mandate version; unapproved changes do not increase authority.

- [ ] **L2 — Approval of actual scope and cost** · **P0** · **🟡 PARTIAL**
  - **Already there / tested subset:** Above-limit owner approval and invalidation on mandate changes are code-tested.
  - **Still needed:** Tie approvals to exact itemised scope, quote version, VAT-inclusive amount, exclusions, validity and change requests; add variation/decline reason and immutable receipt.
  - **Done when:** Editing approved scope/cost requires fresh consent; silence is never counted as approval.

- [ ] **L3 — Statements, bills and payout proof** · **P1** · **⬜ OPEN**
  - **Already there / tested subset:** Landlord rent/bills sections exist; reconciled statements and payouts are not validated.
  - **Still needed:** Add monthly per-property/portfolio statements, reserves, charges, fee/VAT breakdown, linked invoices, payment evidence, CSV/PDF and remittance references.
  - **Done when:** Every statement entry opens a real ledger item and net payout reconciles to confirmed payment.

- [ ] **L4 — Compliance and property health** · **P1** · **⬜ OPEN**
  - **Already there / tested subset:** Document and compliance areas exist; complete property-health tracking is unverified.
  - **Still needed:** Add certificate and inspection timeline, renewal reminders, missing evidence, licence details, repairs/remedial work and recurring maintenance history.
  - **Done when:** Owner can see overdue obligations, unresolved tasks and responsible party without assuming a file equals compliance.

- [ ] **L5 — Tenancy decisions and portfolio planning** · **P1 / P2** · **⬜ OPEN**
  - **Already there / tested subset:** Portfolio screens exist; tenancy decisions/asset planning are not proved.
  - **Still needed:** Add occupancy/void view, agent-reviewed rent changes, pet requests, deposit claims, ending management instructions; later budgets/yield analytics.
  - **Done when:** Sensitive tenant documents remain hidden from owners unless necessary and lawful; no automatic tenancy ending.

### Trades (R1–R5)

- [ ] **R1 — Approved contractor profile** · **P0** · **🟡 PARTIAL**
  - **Already there / tested subset:** Account-linked approved contractor identity, trade/insurance/expiry gates and restriction of unverified gas work are code-tested.
  - **Still needed:** Add independent evidence checking, document uploads, service area, availability, scheduled renewals and secure changes to payment details.
  - **Done when:** Expired, unverified, unlinked or unsuitable contractors cannot receive restricted work via the UI or API.

- [ ] **R2 — Job brief and reliable assignment** · **P0** · **🟡 PARTIAL**
  - **Already there / tested subset:** Targeted quote requests, agent dispatch and blocking of unapproved self-claims are code-tested.
  - **Still needed:** Improve full job brief, safe limited access/contact details, deadlines and acceptance/decline, cancellation rules and simultaneous-assignment safety.
  - **Done when:** Two acceptances cannot award an exclusive job twice; an invitation never permits work to start.

- [ ] **R3 — Quotes and variations** · **P0** · **🟡 PARTIAL**
  - **Already there / tested subset:** Pre-work quote/mandate approval is enforced; overspend invoices are blocked.
  - **Still needed:** Add labour/parts/VAT lines, fixed versus estimate, validity/expiry, quote version lock, revised quotes, attachments and approval-based variations.
  - **Done when:** Superseded quotes cannot be awarded; extra work is a new approved variation, never a silent overwrite.

- [ ] **R4 — Visits and evidence of completion** · **P0** · **🟡 PARTIAL**
  - **Already there / tested subset:** Work-completion state and tenant confirm/reopen flow exist.
  - **Still needed:** Implement proposed/confirmed visit, consent and safe key instructions, no-access/cancellation, parts delays, before/after evidence, certificates and follow-up visits.
  - **Done when:** Proposed is not confirmed; parts keep case open; a defect/reopen retains original evidence.

- [ ] **R5 — Invoices and payment visibility** · **P1 (pilot subset P0)** · **🟡 PARTIAL**
  - **Already there / tested subset:** Invoice submitted/approved/externally-paid states are distinct; work beyond approved amount is refused.
  - **Still needed:** Add invoice numbers and duplicate checks, itemisation/VAT, credits, partial payments, reconciliation, rejection/correction and remittance proof. Keep payments external for pilot.
  - **Done when:** Approval is not payment; paid requires externally verified evidence and recorded reference/date.

## Progress and evidence log

| Date | Evidence | What it proves | What it does **not** prove |
| --- | --- | --- | --- |
| 11 Oct 2026 | [Repairs pilot handoff](REPAIRS_PILOT_PROGRESS.md) | Synthetic backend repair loop, property denial checks, roles/screens and independent approval/payment states reported tested | Real populated browser repair flow, full case/visit/invoice details, production deployment |
| 11 Oct 2026 | [PR #5](https://github.com/eon88/Roger/pull/5) | Fast-track code exists on the feature branch (Agent Desk, roles, backend, synthetic tests) | Merged, deployed or accepted full Instinct backlog |
| 11 Oct 2026 | [Latest browser smoke](https://github.com/eon88/Roger/actions/runs/38174705840) | Four-role login/navigation and landlord property submission/review smoke succeeded | Full repair flow through browser clicks |
| 11 Oct 2026 | [Latest automated tests](https://github.com/eon88/Roger/actions/runs/38174705777) | Development-branch test job succeeded | Approval of every product, security or legal requirement |

## Completion protocol

1. Mark sub-work completed only with commit/PR + passing automated test + named manual/browser evidence; use **DONE** only once the entire area's acceptance check is covered.
2. Test **agent, tenant, landlord, trades** data views, wrong-role denial, wrong-property/tenancy denial, reload persistence and duplicate/concurrent actions whenever relevant.
3. Use synthetic test identities and a separate test instance; never seed demo people/properties into live agency data.
4. For legal, regulated trade, privacy, money and deposit steps, require policy/professional review outside the application.
5. Run backups and restore drills, then separately approve any release and record the **deployed commit**; branch completion is not production completion.

## Next after P0

Complete tenancy onboarding/move-out and deposit evidence, reconciled rent/arrears/landlord statements, complaints and statutory compliance evidence (P1). Leave bulk tools, digests, analytics and external integrations (P2) until the core loops pass.

**Scope note:** England-first small-agency product. Requirements that vary by property, tenure, location or current law need explicit policy/legal review. This is a product backlog, not legal certification.
