# Roger MVP — Prototype V1–V5 Feature Inventory & Repository Backlog

**Prepared:** 10 October 2026  
**Purpose:** Agreed inventory and implementation backlog for developing the new designs in `eon88/Roger`, starting from the tested security-release baseline `b0098bc`.  
**Sources:** The local interactive HTML prototypes V1, V2, V3, V4 and V5, especially `roger-mvp-prototype-v5.html`, plus the existing Roger portal/backend review.  
**Status:** **Design reference and development backlog only.** The inventory and V5 HTML are committed to `feature/roger-mvp-v1-v5-20261011`; none of these V1–V5 design enhancements have been deployed to the live Roger agency.

## 1. What we added, version by version

### V1 — Action-first Agent Desk and design foundation

- [ ] A consistent, responsive design system: warm off-white cards, forest-green brand, restrained status colours, typography, icons, desktop/mobile layouts.
- [ ] Agent dashboard: **Today**, attention counts, urgent items, repair assignments and applications requiring decisions.
- [ ] Consolidated navigation: **Today, Inbox, Properties, Work Orders, People & Verification**; less reliance on the original many-tab dashboard.
- [ ] **Needs attention** inbox: cards for repair cases, landlord property submissions, contractor reviews and quote/work-order decisions.
- [ ] Inbox filters (All / Repairs / Listings / Trades / Jobs), search, unread/status indicators and case selection.
- [ ] Case detail workspace: conversation, related people/property, documents, status and next actions on one screen.
- [ ] One-click agent actions: **Assign tradesperson**, **Approve**, **We need to talk**, **Decline**, **Ask a question**, **Write answer back**, **Review quote**, etc.
- [ ] Contractor matching shortlist: trade type, area, verified eligibility, trade profile and availability/fit presentation.
- [ ] Separate resident/landlord conversation, contractor work-order conversation, and **private internal agent notes**; contractors must never receive unrelated private messages.
- [ ] Work-order and property status chips/timelines; seeded demonstration cases.
- [ ] Guided product tour, quick actions, responsive case-list/detail navigation and **Reset demo**.

### V2 — Landlord property submission and two-role journey

- [ ] **Landlord portal**: property portfolio and status of submitted homes.
- [ ] Four-step **Add a property** wizard:
  1. Address, area/postcode and property type.
  2. Bedrooms, bathrooms, rent, furnishing and description.
  3. Photos, EPC and proof-of-authority document selections.
  4. Review and submit.
- [ ] Required-field validation, step navigation, error feedback and pre-submission review.
- [ ] Submit creates a **property review item in the Agent Inbox** and agent property portfolio.
- [ ] Agent actions: **Approve**, **We need to talk**, **Decline**, with explanation where appropriate.
- [ ] Landlord sees the decision, can message the agent, amend information and resubmit.
- [ ] Preview of the future property advertisement after approval; approval **does not automatically publish** the listing.
- [ ] Desktop and mobile layouts for the landlord journey.

### V3 — Four connected portals, repair workflow, compliance and accountability

- [ ] **Preview portal switcher:** Agent / Landlord / Tenant / Trades, sharing one demo case state.
- [ ] **Tenant portal**: home details, repair reporting form, repair history and progress.
- [ ] Tenant submits category, description and photo/evidence selection; Roger generates a repair case in Agent Inbox.
- [ ] Initial urgency/type detection (e.g. broken lock → locksmith, heating → gas/heating) with explicit safety warning for critical terms. Classification is a suggestion, not an unattended dispatch decision.
- [ ] Agent selects a qualified contractor and shares **only the work-order brief and authorised messages**.
- [ ] **Trades portal**: contractor profile, trade skills, insurance/qualification display, assigned jobs.
- [ ] Tradesperson **Accepts / Declines** a job; decline returns it to the agent for reassignment.
- [ ] Tradesperson marks **In Progress**, sends work-order messages and submits completion notes/evidence.
- [ ] Tenant confirms **Fixed** or **Still not fixed**; cross-role statuses update accordingly.
- [ ] **SLA/aging indicators** calculated from demo timestamps and response targets: time left, overdue, actioned. Targets are configurable business targets, **not legal deadlines**.
- [ ] **Auto-generated activity history** for key demo events (report, assignment, acceptance, completion, decisions); prototype-only, not tamper-resistant.
- [ ] Property compliance panel: **EPC**, **gas safety**, **EICR/electrical**, uploaded/review/verified/missing/expired states and expiry display.
- [ ] Agent **global search** across cases, properties and people in the demo.
- [ ] Contractor verification review, eligible/blocked contractor presentation and mobile role views.

### V4 — Invoicing and rent collection visibility

- [ ] After work-completion evidence, tradesperson sees **Create & send invoice**.
- [ ] Invoice entry tied to the correct repair/work order, property and contractor.
- [ ] Invoice fields: reference, labour, materials, VAT (if applicable), terms and calculated total; view sent invoices and statuses.
- [ ] **Agent Finance**: contractor invoices received → review → approve → record payment.
- [ ] Tradesperson sees updated invoice status after the agent acts.
- [ ] **Landlord rent dashboard**: totals **Received / Overdue / Upcoming or Due**.
- [ ] Rent ledger showing property/tenant, period, due date, expected amount, received amount, status and payment history.
- [ ] **Agent-only** action to record a reconciled rent payment; landlord sees the resulting change; partial/outstanding amounts calculated.
- [ ] Financial screens and forms adapted for mobile.

### V5 — Trades invoices in the attention inbox

- [ ] **New invoice cards in Agent → Needs attention**, not hidden solely in Finance.
- [ ] An **Invoices** filter; invoice items also appear in the Jobs view as applicable.
- [ ] Invoice card shows contractor, related job/property, amount, reference and status.
- [ ] Inbox attention counts include invoices awaiting agent action.
- [ ] Open invoice directly from Inbox → **Review / Approve / Record payment**, linked to the financial record.
- [ ] Invoice status synchronises between **Agent Inbox, Agent Finance and Trades portal**; items cease to demand approval once actioned.

---

## 2. Repository implementation checklist (grouped by workflow)

The checked boxes above intentionally remain unchecked: they describe **prototyped** capabilities, **not** completed production features. Existing Roger backend pieces (cases, jobs, registrations, certain notifications, scoped records, basic financial operations) should be **reused and extended** rather than duplicated.

### A. Shared application and UX — P0

- [ ] **UX-01** Create reusable components/styles: navigation, status badges, cards, details drawer, modal, timeline, buttons and responsive layouts.
- [ ] **UX-02** Replace the dense Agent Desk tab structure with Today / Inbox / Properties / Work Orders / People & Verification / Finance (Finance as records, Inbox as actions).
- [ ] **UX-03** All attention counts, filters, unread states and statuses must come from authoritative backend data and update after each action.
- [ ] **UX-04** Persist cross-portal state; switching users must show only role-authorised records rather than swapping an in-browser role variable.
- [ ] **UX-05** Add loading, empty, validation, confirmation and error states; keyboard and mobile accessibility.
- [ ] **UX-06** Add global server-backed search across authorised cases, properties and people, with role-scoped results.

### B. Landlord onboarding & listing review — P0

- [ ] **LL-01** Guided, validated four-step property wizard with resumable drafts.
- [ ] **LL-02** Secure real photo/EPC/authority uploads, file type/size limits, malware-safe serving and document ownership.
- [ ] **LL-03** Store submissions as property onboarding records linked to **landlord Party/account IDs**; create an Agent Inbox review task.
- [ ] **LL-04** Agent decision state machine: submitted → under review → approved for onboarding / needs discussion / declined; require reasons for adverse/clarification decisions.
- [ ] **LL-05** Two-way landlord/agent messaging and resubmission with versioned details and audit events.
- [ ] **LL-06** Separate **onboarding approval** from **compliance clearance** and **public listing publication**; show advert preview before publishing.
- [ ] **LL-07** Property compliance checklist with jurisdiction/property-type applicability, document verification, expiry and reminders. Deposit scheme and Right to Rent belong in **tenancy setup**, not generic property approval; have legal rules reviewed for the relevant UK jurisdiction.

### C. Tenant repairs and intelligent dispatch — P0

- [ ] **TN-01** Tenant repair form: property link, category, description, optional photo/documents, required safety guidance and submission receipt.
- [ ] **TN-02** Automatically create a scoped repair case, conversation, urgency suggestion, work order and Agent Inbox item without prematurely marking it dispatched.
- [ ] **TN-03** Rules-driven trade suggestions: issue category + skill + applicable verified credentials + geographical coverage + availability; agent confirms assignment.
- [ ] **TN-04** Explicit emergency/escalation path (gas smell, electrical danger, fire, flooding etc.); never imply that an AI response replaces emergency assistance.
- [ ] **TN-05** Scoped messages: tenant/agent case, contractor/agent work-order thread, private agent notes and an audited, deliberate handoff of relevant facts.
- [ ] **TN-06** Tenant sees each status, appointments/messages and can confirm completion or reopen an unresolved repair.

### D. Trades onboarding and work orders — P0

- [ ] **TR-01** Full self-service contractor **registration** (not yet a complete interactive wizard in V5): choose skills/categories, service area, availability and contact details.
- [ ] **TR-02** Upload qualifications/licences, insurance, expiry dates and references/proof of previous work; keep each document tied to the contractor Party.
- [ ] **TR-03** Agent verification flow: pending → additional information → verified / declined / expired; independently verify applicable credentials; enforce valid scopes and expiry **server-side**.
- [ ] **TR-04** Dispatch only to an eligible, verified contractor; record offer, acceptance/decline and reassign on decline.
- [ ] **TR-05** Contractor work-order inbox, scoped communication, In Progress status, completion notes and actual evidence uploads.
- [ ] **TR-06** Job timeline and agent/tenant verification before closure; do not treat a contractor's 'Completed' claim as automatic tenant satisfaction.

### E. Invoices, rent, payment visibility — P0 for demo; P1 for full accounting

- [ ] **FN-01** Job-linked contractor invoice: number, dates, labour, materials, tax/VAT where applicable, attachments and totals, with correct currency/precision and validation.
- [ ] **FN-02** Contractor **Send invoice** → creates one real backend invoice record and **Agent Needs attention** item (Invoices filter, Jobs view, Finance view).
- [ ] **FN-03** Agent review/approve/query invoice and separately record a verified payment; contractor sees correct status. Avoid duplicate invoices/payments and unauthorised edits.
- [ ] **FN-04** Landlord rent ledger: tenancy, due period, expected amount, verified receipt(s), balance, paid/partially paid/overdue/upcoming statuses.
- [ ] **FN-05** Only authorised agent/staff can record payment reconciliation; landlord gets read-only access to **their** property and tenants' rent statuses.
- [ ] **FN-06** Handle reversals, corrections and payment evidence via auditable actions rather than secretly rewriting past entries. Real bank/accounting integration is **not** required for initial MVP showcase.

### F. The action engine and operational protections — P0/P1

- [ ] **WF-01 (P0)** Single event/task/action architecture: event → rule → permission-checked next action → status change → notification + audit event.
- [ ] **WF-02 (P0)** Per-role action permissions and strict, Party-ID-based data isolation for cases, properties, uploads, invoice values and messages.
- [ ] **WF-03 (P0)** True server-generated timestamps and SLA/aging indicators with policy-controlled targets, pause rules and escalation ownership.
- [ ] **WF-04 (P0)** Append-only server-generated case events (actor, event, affected entity, timestamp, before/after or reference, correlation ID). JSON mock history is **not immutable**; stronger tamper-evidence/storage is needed before making compliance claims.
- [ ] **WF-05 (P0)** Notification hooks for landlord submissions, new repair, contractor assignment/decline, completion, invoice received and rent overdue, without leaking private data.
- [ ] **WF-06 (P0)** End-to-end role tests: landlord submit → agent decision; tenant report → agent assign → trades accept/complete → tenant confirms; invoice → approval/payment; rent update → landlord reflects accurately.
- [ ] **WF-07 (P1)** Automated certificate-expiry and payment-overdue reminders, aging escalations, monitoring, durable jobs and scheduled processes.
- [ ] **WF-08 (P1)** Admin account onboarding/reset/invite/suspend UI, access to compliance/audit history, backup and rollback checks.

### G. Presentable, isolated showcase — P0

- [ ] **DEMO-01** Recreate V5's fictional landlord, tenant, agent and trades journeys in a **separate demo dataset/environment**. Never reintroduce old seeded test accounts/fictional listings into production.
- [ ] **DEMO-02** Walkthrough mode with clear instructions and a reset function; do not present simulated financial transactions, certificate checks or invoices as genuine.
- [ ] **DEMO-03** Desktop and mobile visual regression screenshots and task-based usability tests with a non-developer.

---

## 3. Suggested build order and release gates

1. **M1 — Visual foundation & unified Agent Inbox:** UX-01 through UX-05 plus WF-01/WF-02; preserve and expand existing server boundaries.
2. **M2 — First full journey (Landlord):** LL-01 through LL-06, basic LL-07 and initial audit events. Agent decisions and landlord feedback must survive logout/relogin.
3. **M3 — Second journey (Repairs):** TN-01 through TN-06, TR-04/TR-05/TR-06; confirm contractor decline and tenant 'still not fixed' return the case to appropriate queues.
4. **M4 — Verified trades:** TR-01 through TR-03, eligibility/expiry checks, attachments and proof of work; no unverified contractor dispatch.
5. **M5 — Money in/out:** FN-01 through FN-05; inbox and finance reconcile one invoice source of truth, and landlord rent statuses come from validated records.
6. **M6 — Polish & demo launch:** WF-03 through WF-06, UX-06, DEMO-01 through DEMO-03. Add comprehensive negative permission tests and keep rollbacks verified.

**Definition of MVP demonstration ready:** A person can complete the landlord submission/agent decision, tenant repair/contractor journey, contractor invoice/agent approval and landlord rent-review story in the live interactive **demo environment**, with consistent navigation and real backend state. Real money movement, legally authoritative credential checks, notifications to actual customers and production operations require additional review.

## 4. Implementation safeguards

- Do **not** copy or overwrite the live Hostinger production volume with mock demo state.
- Do **not** deploy the prototype HTML as if it were a secure authenticated application: browser-side role selection is intentionally insecure demo scaffolding.
- Existing Roger release `b0098bc` runs in production, with security changes not yet merged into GitHub `main`; align the **correct base branch and commits** before starting feature work.
- Prototype evidence/documents are **filenames only**; design and test real secure uploads before onboarding actual people.
- Contractor eligibility, landlord data isolation, actions/permissions, receipt claims and audit events must be validated by the server, not JavaScript alone.
- Separate a work order, invoice, rent receipt and audit event into distinct persistent records; Inbox should index pending actions from those entities rather than holding a second contradictory copy.
- Prefer incremental pull requests, tests, staging/demo deployment and rollback plans; **no production deployment without explicit approval**.

## 5. Proposed repository artifacts

- `docs/mvp/PROTOTYPE_V1_V5_INVENTORY.md` — this checklist.
- `docs/mvp/WORKFLOWS.md` — state diagrams, role permissions, decision tables and notification rules.
- `docs/mvp/UX_SPEC.md` — screens, fields, validation, empty/error states, desktop/mobile design system.
- `docs/mvp/DEMO_SCRIPT.md` — step-by-step five-minute demonstration across the four portals.
- `prototypes/roger-mvp-prototype-v5.html` — **reference-only interactive HTML**, not production source.
- Actual production features should live within the existing portal/backend layout in small, reviewed PRs.
