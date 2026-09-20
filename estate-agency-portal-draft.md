# Virtual Estate Agency — Portal Draft (v0.1)

A single-solopreneur agency needs a portal that does two jobs at once:

1. **Shop window** — advertise the properties and the management service (public, no login).
2. **Machine room** — four dashboards where landlord, tenant, agent and trades each run their side of the relationship.

Underneath both sits one brain: the **workflow engine** (Event → Identity → Property → Intent → Situation → Rules → Decision → Authority → Action → Communication → Follow-up → Resolution) and the **AI layer** that triages, drafts, reminds and escalates — exactly as set out in the Operating Model.

Design constraint that shapes everything: **the agent is one person.** The portal is not a CRM for a team of ten negotiators; it is a cockpit that lets one human supervise hundreds of concurrent cases by only touching exceptions.

---

## 1. Sitemap

```
PUBLIC (no login)
├── Home (agency pitch, dual CTA: "Find a home" / "List your property")
├── Properties (search + filters)
│   └── Property detail (gallery, EPC, fees, hold-deposit, book viewing)
├── For Landlords (services, pricing, onboarding CTA)
├── For Tenants (how it works, report-a-repair demo, fees transparency)
├── For Trades (join the approved network, credential upload)
├── About / Contact / Legal (privacy, terms, complaints, redress, CMP, deposit schemes)

PORTAL (login)
├── /agent     — solopreneur cockpit
├── /landlord  — owner dashboard
├── /tenant    — occupier dashboard
└── /trades    — contractor dashboard
```

One login screen, role resolved from the account. A user can hold multiple roles (e.g. a landlord who also rents from the agency) with a role switcher.

---

## 2. Public site — the shop window

**Home.** Positioning: "Full lettings and property management, run on rails." Three doors: tenants search, landlords onboard, trades join. Social proof, service-area, regulated-by footer (CMP certificate, redress scheme, ICO).

**Property search.** Map + list view; filters: location, rent, beds, available-from, pet-friendly, furnished. Every listing is a live object in the database — the same record the portal manages — so there is one source of truth. Listing states: *Draft → Advertised → Lettings agreed → Let*.

**Property detail page.** Gallery, floorplan, EPC, rent + deposit, available date, fees, "what happens next" (their move vocabulary made visible: APPLY → VERIFY → SIGN → MOVE IN), and a **Book a viewing** widget that writes straight into the agent's viewing calendar. Tenant accounts are created at application time — the advert is the top of the portal funnel.

**For Landlords.** Packages (tenant-find / rent-collection / full management), the pitch for the portal itself: *"Every landlord gets a dashboard: live rent status, compliance calendar, approvals in one tap."* Onboarding wizard: property details → documents (title, EPC, gas, EICR, key handover) → terms & instructions → sign management agreement (SIGN move).

**For Trades.** Registration: credentials, insurance, quals, rates, availability → agent verifies → approved onto the network. This is the trades' entry into the portal.

---

## 3. Portal foundations (shared by all four dashboards)

- **Identity & tenancy graph.** Every user, message, document, job and payment is attached to a Property → Tenancy. Nothing is ever "a random email" — the Event → Identity → Property steps of the engine happen at intake.
- **Threaded messaging.** One thread per (person × property × topic). No free-floating inboxes. Every message becomes a case if it needs action.
- **Case object.** The universal unit of work: type (maintenance, compliance, payment, viewing, renewal, complaint…), status machine mirroring the engine (`New → Verified → Awaiting decision → Instructed → In progress → Confirm → Closed`), SLA clock, full audit log.
- **Documents.** Versioned vault with expiry dates; expiries generate cases automatically (compliance calendar).
- **Notifications.** Email + push, tenant- and landlord-configurable. The AI *Reminds* and *Chases* before anything becomes late.
- **Audit trail.** Every move (who, what, when, on whose authority) is recorded — the answer to every future deposit dispute.

---

## 4. Agent dashboard — the solopreneur cockpit

The one human is a *choreographer*, not a typist. The dashboard is organised around the exception queue, not around per-landlord folders.

**A. Unified inbox (AI-triaged).** Every inbound message, form, event and system alert lands in one stream. AI pre-sorts into: *Auto-handled*, *Needs my decision*, *Needs landlord approval*, *Emergency*. Each item shows identity, property, intent, situation and the recommended next move.

**B. Exception queue (Section 7 of the model).** Only matters that must not be automated: possession/legal, complaints and disputes, vulnerable-person flags, failed referencing, fraud suspicion, overspend, unclear rules. Each exception carries the AI's summary of the case so the agent decides in seconds, not minutes.

**C. Approvals pipeline.** Everything the AI or a trade has staged that needs a click: expenditure within landlord authority, quotes, invoices out, tenancy agreements for signature. Bulk-approve where authority exists.

**D. Portfolio board.** All landlords × all properties: occupancy, voids, tenancy end-dates, compliance expiry strip (gas / EICR / EPC / alarm tests — red/amber/green), arrears list, viewings today.

**E. Money view.** Rent received/expected per property, client-account position, contractor invoices to settle, management fees due. (Reconciliation and disbursement are processes the portal should drive, with the agent confirming runs.)

**F. Automation studio.** Where the solopreneur earns leverage: templates for every TELL/REQUEST, rules per landlord ("approve repairs up to £150 without asking"), AI autonomy settings, chase schedules, out-of-hours responder.

**Key design rule:** the agent should be able to run the day from screens A–C alone. D–F are the management layer.

---

## 5. Landlord dashboard

The landlord sees **their** portfolio only.

- **Portfolio strip:** each property → tenancy status, tenant, rent, next action.
- **Money:** rent statements (monthly, exportable), income vs fees, pending invoices, year-end pack.
- **Approvals (APPROVE):** expenditure requests with quote attached and one-tap approve/decline + comment; tenant applications if the landlord holds that instruction; renewals and term changes.
- **Compliance calendar:** certificate status per property with expiry countdowns — the landlord never gets surprised.
- **Maintenance history:** every job, cost and photo, per property.
- **Documents:** agreements, certificates, statements, EPCs.
- **Thread with the agent:** the personal channel; anything needing landlord decision arrives here as an APPROVE card, not as prose.

---

## 6. Tenant dashboard

Optimised for phone, low frequency, high clarity.

- **My home:** tenancy at a glance — rent due, fixed-term end, notice deadlines, documents.
- **Payments (PAY):** rent method, history, payment receipts.
- **Report an issue (REPORT):** guided flow — category → severity → photos → access preference. Creates the case live with the status shown back to the tenant (*Verified → Contractor booked → Done*). The single most-used screen in the portal.
- **Appointments (BOOK/CONFIRM):** viewings-in for trades, inspections, and confirmation that a repair is resolved.
- **Renewal / notice (SIGN):** renewal offers for signature; notice wizard with deposit-return timeline.
- **Thread with the agent.**

---

## 7. Trades dashboard

- **Job board:** offered jobs (job sheet, photos, tenancy constraints), accept/decline, quote submission (QUOTE).
- **Schedule:** booked visits with access details and tenant contact.
- **Complete (DO → REPORT):** completion form with photos, parts, warranty note — invoice auto-raised from the completion.
- **Money:** invoice status, payment date.
- **Credentials:** insurance and quals with expiry reminders — lapsed documents suspend job offers automatically.

---

## 8. Authority matrix (who may do what)

The Operating Model ends by asking for this. First pass:

| Move | AI alone | Agent | Landlord | Trade | Tenant |
|---|---|---|---|---|---|
| ASK / TELL (routine) | ✅ draft+send | ✅ | ✅ | ✅ | ✅ |
| BOOK viewing / access | ✅ within rules | ✅ | – | request | request |
| VERIFY identity / docs | ✅ + flags | ✅ decides | – | – | provide |
| REPORT maintenance | intake only | ✅ | – | – | ✅ |
| APPROVE spend ≤ landlord limit | ✅ within standing instruction | ✅ within authority | ✅ above it | request | – |
| APPROVE tenant / renewal | never | ✅ recommend | ✅ decide | – | apply |
| SIGN tenancy | never | ✅ prepare | landlord signs | – | tenant signs |
| PAY / disburse | stage only | ✅ execute | – | invoice | pay rent |
| ESCALATE | ✅ always allowed | ✅ | ✅ | ✅ | ✅ |
| Legal notices / possession | never | agent + solicitor | instruct | – | – |

Two hard rules from the model, enforced in software, not just policy: **AI never signs, never pays, never serves notice**; anything in the Section-7 list is human-only.

---

## 9. Data model sketch

`User(role) — Landlord — Property — Tenancy — Tenant`
`Property →` Case/Job, Document, Viewing, Payment, Message-thread, ComplianceItem
`Case →` events, approvals, attachments, audit log
`Trade — Credential — Job — Quote — Invoice`

Everything hangs off Property/Tenancy — the "stage" in the model.

---

## 10. Build path for a solopreneur

**Stack recommendation:** Next.js + Postgres (Supabase: auth, row-level security per role, storage for documents) + Stripe for payments + a job queue for automations + an LLM layer for triage/drafting. Row-level security is the workhorse: "landlord sees own properties, tenant sees own tenancy, trade sees own jobs" falls out of the schema.

**Alternative worth naming:** for £30–100/month, established CRMs (Arthur, Reapit, etc.) cover much of the agent side but give a weaker tenant/trade experience and little AI leverage. Build if the portal itself is the differentiator; rent if time-to-market wins.

**Phase 1 — MVP (advertise + keep the wheels on):**
public site, listings, viewing booking, tenant repair reporting, agent cockpit inbox + case queue, landlord approvals, compliance calendar.

**Phase 2 — money and trades:** trades portal, quotes/invoices, rent statements, signature flows, landlord statements.

**Phase 3 — AI depth:** auto-triage with real autonomy, chasing, renewal pipelines, learning routing.

The MVP alone delivers the solopreneur promise: one person, exception-only supervision, everything else on rails.
