# Trades Lifecycle — From Job Request to Completion

---

## Stage 1: Registration — Becoming a Tradesperson

- Tradesperson connects via **/register/trades** or enquiry form
- Agent reviews registration — verifies qualifications, insurance, certifications
- Agent **approves** tradesperson account
- Tradesperson receives **invitation link** to create portal account
- Agent can **add tradesperson to pool** (`/trades-pool`)

---

## Stage 2: Job Assignment — Entering the Queue

- Tenant or landlord **reports an issue** via **/report**
- Agent receives report — validates urgency (safety / non-urgent / scheduled)
- Agent **checks trades pool** — assigns to appropriate tradesperson based on trade type
- Tradesperson receives **job notification** in dashboard

---

## Stage 3: Quote Request — Estimating Work

1. Tradesperson views job — photos, description, property details
2. Tradesperson **creates quote** — items, labour, materials, price, timeline
3. Tradesperson **submits quote** to tenant (and optionally to landlord)
4. Tenant and landlord can **review and approve** quote
5. If rejected, agent can **re-quote** or assign to another tradesperson

---

## Stage 4: Quote Approval & Booking

- Tenant **approves quote**
- Agent receives confirmation
- Agent **books commencement** — sets target start date
- Property status updates: **work in progress**
- Tradesperson can **update job status** (started / on-site / materials ordered)

---

## Stage 5: Work Execution — On-Site Activity

- Tradesperson visits property
- Tradesperson logs **actual time / materials used / issues found**
- Agent can **chat** with tradesperson for updates
- Tradesperson can **request additional work** (e.g., "found leak behind")

---

## Stage 6: Completion — Invoicing & Payment

- Tradesperson **marks job complete**
- Agent **reviews completed work** — photos, receipts, quality check
- Agent **issues invoice** — link to pay
- Tenant pays (agent collects)
- Tradesperson receives **notification of payment**
- Property **repaired / updated** in case history

---

## Stage 7: Post-Completion / Follow-Up

- Tenant can **rate the work** (optional feedback)
- Tradesperson **archives job** for portfolio
- Landlord can **verify repair quality** if they requested it
- Case updates with **repair evidence** attached

---

## Tradesperson Dashboard Actions Summary

| Action | Endpoint | Status |
|---|---|---|
| View own quotes | `GET /api/trades` | ✅ Built |
| Create quote | `POST /api/quote` | ✅ Built |
| Submit quote | `POST /api/quote-submit` | ✅ Built |
| Approve quote | `POST /api/quote-approve` | ✅ Built |
| Request work | `POST /api/quote-request` | ✅ Built |
| Start job | `POST /api/job-start` | ⏳ NEEDS |
| Update job | `POST /api/job-update` | ⏳ NEEDS |
| Complete job | `POST /api/job-complete` | ⏳ NEEDS |
| Issue invoice | `POST /api/invoice-issue` | ⏳ NEEDS |

---

## Key Concepts

- **Agent assigns by trade** — gas → gas-safe, electrician, plumber, painter, etc.
- **Quotes are optional** — but highly recommended for transparency
- **Payment flows** — tenant pays, agent collects, then dispatches to tradesperson (or tradesperson invoice directly)
- **Evidence required** — photos of completed work, receipts, before/after
- **Trade type auto-routing** — Jev classification routes gas/electric/unsafe to specialist trades automatically

---

## Required New Objects (NEEDS)

- `job-status` field on cases (`in_progress`, `awaiting_confirmation`, `awaiting_payment`, `completed`)
- `tradesperson_rating` object (feedback from tenant / landlord)
- `invoice_template` for standard quotes / invoices
- `materials_list` on work orders

---

## Flow Diagram

`Report → Quote → Approve → Book → Work → Complete → Pay → Review`

The **agent orchestrates**; the **tradesperson executes**; the **portal tracks** every stage.