# Tenant Lifecycle — Prospect to Active Tenancy

---

## Stage 1: Prospect — Looking to Rent

- See properties at **/** (public listings)
- Browse details (title, area, bed, rent, description)
- Select to **enquire** — enters `full_name`, `phone`, `email`
- Agent receives enquiry via **registrations** queue
- Agent **vetting**: reviews, approves or rejects

---

## Stage 2: Viewing — Qualification

- Agent **proposes a viewing slot** (needs `appointment` object)
- Prospect **accepts / declines / requests different time**
- If declined: prospect can re-request a new slot
- Agent marks viewing **attended or not**

---

## Stage 3: Agreement — Signing / Deposits

- Agent sends **invitation link** to create portal account
- Prospect **creates account** — linked to the property
- Tenancy agreement appears — **agent uploads / confirms**
- Bank details enter
- Deposit proof **screenshot** uploaded
- Agent **confirms** agreement, deposit protected, bank details

---

## Stage 4: Key Handover — Tenancy Begins

- Agent and tenant **schedule key handover meeting** (calendar / slot)
- Agent confirms **keys provided**
- Tenant becomes **active tenant**
- Initial rent due recorded

---

## Stage 5: End of Tenancy — Termination

### 5a. Voluntary — 2 months notice

- Tenant notifies agent
- Agent records notice period
- Tenant receives reminder to arrange move-out

### 5b. For-cause — Grounds for eviction

- **Non-payment** — 2 consecutive months unpaid
- **Property damage** — beyond normal wear and tear
- **Landlord sale / move-in** — legal notice served
- Agent **confirms termination** with reason in case thread

### 5c. Completion — Keys returned

- Tenant returns keys (agent confirms in **property status**)
- Property status changes from **"let" → "vacant"**
- Old tenancy record **preserved** (audit trail)
- Agent **issues new login** for next tenant applicant

---

## Agent Dashboard Actions Summary

| Action | Endpoint | Status |
|---|---|---|
| View prospects | `GET /api/registrations` | ✅ Done |
| Approve / reject prospect | `POST /api/case-action` (vet) | ✅ Done |
| Schedule viewing | `POST /api/appointment` | ⏳ NEEDS |
| Send invitation | `POST /api/invitation` | ⏳ NEEDS |
| Confirm agreement | `POST /case-action` (attachment) | ✅ Can use thread |
| Confirm keys returned | `POST /property-status-change` | ⏳ NEEDS |
| Terminate tenancy | `POST /api/termination` | ⏳ NEEDS |

---

## Key Concepts

- **Agent is the conductor** — never gives direct access without confirmation
- **Property is the stage** — status flows: `vacant → advertised → let → in-transition → vacant` (for re-letting)
- **Records never deleted** — audit trail for reference / legal reasons
- **New account, same property** — each tenancy has its own login identifier
- **Exit reason logged** — voluntary, non-payment, sale, damage, landlord-move-in

---

## Required New Objects (NEEDS)

- `prospect` record (track vetted / invited / visiting / agreed / paid)
- `appointment` object (viewing, key handover — slot state)
- `invitation` token (agent → prospect login link)
- `agreement` document (upload / confirm / protect)
- `termination` event (reason, end date, key return confirmation)