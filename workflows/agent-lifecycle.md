# Agent Lifecycle — Orchestrating Rentals from First Contact to Completion

---

## Stage 1: Prospect Contact — Lead Capture

- Visitor at **/** (public listings)
- Prospect submits **enquiry** — `POST /api/public` — enters full_name, phone, email
- Agent receives enquiry in **registrations** list (`/api/registrations` → agent's dashboard)
- Agent **reviews enquiry** — decides to **vet** (qualify) or **reject** outright

---

## Stage 2: Vetting — Validating the Prospect

1. Agent pulls **property details** linked to enquiry → `/properties/:id`
2. Agent **vetting**: validates identity, references, affordability
3. Agent marks prospect **`vetted-approved`** or **`vetted-rejected`** → `POST /api/case-action` with `status=approved|rejected`
4. Agent may **add internal note** → `POST /thread` with type=internal

---

## Stage 3: Viewing — Scheduling Access

1. Agent **proposes a slot** → `POST /api/appointment` (NEEDS `appointment` object)
2. Prospect **accepts / declines** — agent notified (`notification=true`)
3. Prospect declines → Agent proposes **alternate slot** (loop)
4. Prospect accepts → Agent logs **meeting created** event
5. Agent can **mark attended / not-attended** → `POST /case-action` with `status=attended|missed`

---

## Stage 4: Invitation — Creating the Portal Login

1. Agent **creates case** on property → `POST /case` with `property_id`
2. Agent sends **invitation** to prospect → `POST /api/invitation` (NEEDS token + email)
3. Prospect **creates account** — auto-assigned `tenant` role on property
4. Agent confirms → new **tenant record** appears in case

---

## Stage 5: Agreement — Legal & Finance Setup

1. Agent **uploads agreement** to case → `PATCH /case` with `document` attachment (NEEDS upload)
2. Agent sets **deposit amount** + **due dates** → `POST /case-action` with `status=agree_sent`
3. Agent **confirms bank details** entered by tenants → verification step
4. Agent requests **payment proof** from tenant → `POST /thread` with type=payment_request

---

## Stage 6: Key Handover — Start of Tenancy

1. Agent schedules key handover meeting → `POST /api/appointment` (reuse appointment object)
2. Tenant attends, receives keys → agent **records receipt**
3. Agent flags property **work-started at** → `PATCH /properties/:id` with `status=let`
4. Tenancy formally begins — case transitions to **active**

---

## Stage 7: Active Management — Jobs & Repairs

1. Tenant reports issue → `POST /report` → new case
2. Agent **reviews report** → triage (safety vs. routine)
3. Agent **assigns to trade** → `POST /case-action` with `assignment` + trade-type routing (Jev auto-classifies)
4. Agent **quotes / bids**:
   - For small jobs → agent **creates direct quote** on behalf
   - For large jobs → agent requests **tradesperson quotes** via pool (`/trades-pool`)
5. Agent **presents quotes** to tenant + landlord → `POST /thread` with `quote_list`
6. Agent **approves or requests revision** → `POST /case-action` with `approve_quote|request_revision`
7. Landlord **confirms rent** collected during repairs if property vacant

---

## Stage 8: Financials — Payment & Deposit Handling

1. Agent **receives rent** from tenant → `payment_received=true`
2. Agent **dispatches rent** to landlord → `POST /case-action` with `distribute_rent`
3. Agent **dispatches deposit** to protection scheme → `POST /case-action` with `protect_deposit`
4. Agent reconciles invoices → visible in **financial dashboard**

---

## Stage 9: Renewal / End of Tenancy

1. **3 months before lease end** → agent triggers renewal workflow via `/case-action` with `status=renewal_reminder`
2. If tenant renews → agent **prepares new agreement**
3. If tenant exits → agent **checks grounds**:
   - Voluntary leave → `status=notice_given`
   - For-cause → valid reasons tagged (non-payment 2 months, damage, sale, move-in)
4. Agent **schedules final inspection** → `POST /api/appointment`
5. Agent confirms **keys returned** → property returns to `vacant`
6. Old case **preserved** in archive — full history retained

---

## Agent Dashboard Actions Summary

| Action | Endpoint | Status |
|---|---|---|
| View open enquiries | `GET /api/registrations` | ✅ Done |
| Vet / reject prospect | `POST /api/case-action` (status=approved|rejected) | ✅ Built |
| Schedule viewing | `POST /api/appointment` | ⏳ NEEDS |
| Create case | `POST /case` | ✅ Built |
| Send invitation | `POST /api/invitation` | ⏳ NEEDS |
| Upload agreement | `PATCH /case` (doc) | ⏳ NEEDS |
| Confirm keys handed | `PATCH /properties` | ✅ Built (status) |
| Assign to trade | `POST /case-action` (assignment) | ✅ Built |
| Approve quote | `POST /case-action` (approve_quote) | ✅ Built |
| Distribute rent | `POST /case-action` (distribute_rent) | ✅ Built |
| Protect deposit | `POST /case-action` (protect_deposit) | ✅ Built |
| Issue invoice | `POST /case-action` (invoice) | ✅ Built |

---

## Key Concepts

- **Agent is the sole orchestrator** — never lets landlords, tenants, or trades interact directly
- **Agent controls state transitions** — property and case status changes only via agent action
- **Agent owns verification** — every critical step requires explicit agent confirmation
- **Agent enforces deadlines** — renewals, notice periods, payment due dates managed through case threads
- **Agent preserves evidence** — every action logged with timestamp, user_id, role

---

## Required New Objects (NEEDS)

- `appointment` — unified scheduling for viewings, inspections, key handovers
- `invitation` — secure token-based account creation for new tenants
- Case `document` / `attachment` — for agreements, payment proofs, inspection reports
- `deposit_scheme` integration — statutory protection confirmation (links to legal P0)

---

## Flow Diagram

`Enquire → Vet → View → Invite → Fix → Collect → Inspect → End → Re-list`

The **agent conducts every stage**; **landlords approve agreements**, **trades execute jobs**, **tenants occupy** — and the **portal tracks** the whole lifecycle from first email to final key drop.