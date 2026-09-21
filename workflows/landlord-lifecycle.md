# Landlord Lifecycle — From Property Inquiry to Re-letting

---

## Stage 1: Registration — Becoming a Landlord

- Landlord connects via **/register/landlord** or enquiry form
- Agent reviews registration — verifies ownership, insurance, consent
- Agent **approves** landlord account
- Landlord receives **invitation link** to create portal account
- Landlord **onboards property** — uploads details (photos, description, rent, deposit, available date)

---

## Stage 2: Property Onboarding — Listing for Rent

1. Agent reviews property details — corrects if needed
2. Property added to **public listings** for prospective tenants
3. Property status: **`let` → `vacant → advertised`** or **`vacant`** (if empty)
4. Landlord can **track interest** (enquiries count, viewings booked)

---

## Stage 3: Letting Process — Finding a Tenant

- Tenant reports issue via **/report** — agent assigns
- Agent **shortlists prospects** — shares shortlist with landlord (optional)
- Agent schedules **viewings** — landlord can approve access times if requested
- Agent **qualifies** selected prospect — references, credit, suitability
- Agent makes **offer** — draft tenancy agreement prepared
- Landlord **reviews and approves** agreement terms and rent

---

## Stage 4: Agreement & Finance — Tenant Moves In

- Prospect signs tenancy agreement
- Tenant pays deposit + first month rent
- Agent **confirms payment** and key handover
- Property status: **`advertised → let`**
- Landlord notified: tenant name, agreement start date, rent, deposit details

---

## Stage 5: Active Tenancy — Ongoing Management

- Tenant can **report issues** via **/report**
- Agent **assigns work** to trades — landlord notified of scheduled visits
- Landlord can **check case status** in dashboard — see open jobs, issues, history
- **Rent collected** by agent — rent reminders sent to tenant (agent handles)
- Landlord can **request repairs / upgrades** or confirm completed work
- Agent manages **communication** between tenant, landlord, and trades

---

## Stage 6: Renewal / End of Tenancy

- **3 months before end** — agent notifies landlord of upcoming expiry
- Landlord decides: **renew** / **new terms** / **end tenancy**
- If ending — agent checks for **valid grounds** (sale / move-in / breach)
- **Notice served** — 2 months voluntary / statutory period for for-cause
- Tenant moves out — agent confirms **keys returned** via property visit
- Property status: **`let → vacant → re-advertised`**
- Landlord can **set new rent** or **new terms** for next tenant
- Old tenancy record **preserved** (audit trail) — agent issues new accounts for new tenant

---

## Landlord Dashboard Actions Summary

| Action | Endpoint | Status |
|---|---|---|
| View properties | `GET /api/my-properties` | ✅ Dashboard view |
| Add property | `POST /api/properties` | ⏳ NEEDS (manual today) |
| Edit rent / terms | `PATCH /api/properties` | ⏳ NEEDS |
| Approve agreement | `POST /case-action` (approve_quote) | ✅ Built |
| Approve rent increase | `POST /property-rent-increase` | ⏳ NEEDS |
| Approve letting | `POST /case-action` (let) | ✅ Can reuse |
| End tenancy | `POST /api/termination` | ⏳ NEEDS |
| Receive payment report | `GET /api/payment-report` | ⏳ NEEDS |
| View repair evidence | `GET /case-thread` | ✅ Built |

---

## Key Concepts

- **Agent presents candidates to landlord** — but final decision is landlord's
- **Landlord approves agreements** — rent, deposit, terms must be confirmed before letting
- **Rent flows landlord → agent** (agent collects from tenant, passes to landlord on schedule)
- **Maintenance access** — landlord must give permission for tradesperson access unless emergency
- **Deposit handling** — agent must confirm deposit is protected (per legal P0 requirements)

---

## Required New Objects (NEEDS)

- `property` object with status (`vacant`, `advertised`, `let`, `in-transition`)
- `landlord_view_shortlist` — share prospect shortlist with landlord for approval
- `rent_increase` workflow — landlord proposes, tenant agrees
- `payment_report` — rent/deposit summary, ready for HMRC / accounting

---

## Flow Diagram

`Register → List → Let → Collect → Work → Renew or End → Re-list`

The **agent manages tenants**; the **landlord validates agreements**; the **portal tracks** the property stage through every transition.