# Roger v1.0 — FINAL FUNCTIONAL SCOPE / BUILD CONTRACT

**Scope frozen:** 8 November 2026 · **Target:** England-first residential **LETTINGS AND PROPERTY MANAGEMENT ONLY**, multi-agency SaaS with independently segregated agency data. This document amends and sharpens `ROGER_V1_SINGLE_RELEASE_PLAN.md` and the competitor audit.

## One-release commitment

1. No intermediate app downloads, customer installs, merges to production, Hostinger changes, or data migrations while this is built.
2. Work on `feature/roger-v1-single-release-20261108` and use disposable CI/staging clones. Incremental git commits are **not versions/releases**.
3. Release only after the complete in-scope journeys are demonstrably working, independently tested, appropriately reviewed, and reversible from a proved production backup. Provide one rollout checklist and one rollback procedure.
4. This is a **design contract, not evidence of implementation**. Items without acceptance evidence are OPEN regardless of whether similar controls exist in the current code.
5. Change this frozen scope only for discovered security, legal compliance, critical data-integrity omissions or explicit product-owner approval. Do not add competitors' unrelated features simply because they exist.

## Supported market and exclusions

**In scope:** England private residential single-property and portfolio letting agents; managed and tenant-find-only management agreements; rental property advertising and landlord acquisition; renter/applicant journey; multiple landlords and tenants; property and tenancy history; HMO/licensing indicators and room/subunit data (not a full specialist HMO compliance service); role-based portals on desktop and mobile browser.

**Out of scope:** property SALES, buyers/vendors, sales offers, conveyancing/chains, auctions, commercial property, overseas legal regimes, student-residence specialist operations, holiday lets, leasehold/block management, public property-portal syndication without an authorised integration agreement, in-app bank transfers, and autonomous legally binding decisions. No native Android/iOS apps required when mobile responsive browser/installed PWA works. Do not build a general AI swarm, scraping competitor private sites, or a bespoke accounting replacement.

## Modules that MUST work for the single v1 release

| ID | Product capability | Required end-to-end behaviour (acceptance) |
| --- | --- | --- |
| 01 | **Agency SaaS / configuration** | Operator can provision isolated agency, domain/branding, packages and staff accounts; invite, suspend, revoke and recover staff securely; configure office contacts, opening times, emergency instructions, fees, maintenance authority, document retention and branches. Agency isolation holds across API, files, reports and backups. |
| 02 | **Master data + migration** | One authoritative linked model for Agency → Property / optional Unit/Room → Ownership/Management mandate → Tenant/Applicant/Guarantor/Trades → Tenancy → Case/Task/Payment/Document. Effective dates and state history survive changes. CSV templates/import preview/duplicate matching/rollback/error reports; CSV and document export; no silent replacement or overwrites. |
| 03 | **Landlord onboarding / agreement** | Enquiries → owner verification → property survey → management-agreement type, fee schedule, spending authority and start/stop dates → property compliance → rental marketing. One landlord can own several properties; joint owners require proper authorization and role scoping. |
| 04 | **Rental listings / applicant journey** | Rental advert with price and availability; enquiry, rental viewing requests, appointments/reminders, feedback, rental application, consented referencing, holding-deposit tracking where used, offer at permitted rent, guarantor if needed, decision trail. Directly convert approved applicant into tenancy without re-entering records. No rental bidding or prohibited pre-contract rent requests. |
| 05 | **2026 tenancy management** | Assured periodic tenancy structure for the mainstream England PRS, with correctly tracked periodic rent, occupiers, evidence and notices **not a mandatory fixed-term end date**. Record right-to-rent checks and follow-ups with restricted visibility; agreement/docs/e-sign through approved workflow; permitted rent increases/notice, tenant pet requests, lawful possession/ending instructions requiring human legal review. Historical and exceptional tenancy types must be explicitly marked, not forced into invalid states. |
| 06 | **Money / deposit / statements** | Tenant rent schedule, receipts and arrears, recorded external bank evidence and import-assisted reconciliation, landlord fees and configurable VAT, contractor expenses/credits, owner distributions and exact-pence landlord statements; adjustments must audit who/why. Track separate holding deposit and protected tenancy deposit: amount limits, scheme/reference, deadlines, prescribed-information evidence, return/dispute. Explicitly distinguish booked, paid, reconciled and transferred; no fake payment or direct transfer claims. |
| 07 | **Repairs / contractor operations** | Tenant photos and guided text interview → deterministic safety escalation + optional verified real model/vision → agent triage → contractor eligibility → multiple quotation options where needed → owner authority/approved variation → accepted visit/access/no-show/parts delay → work evidence → tenant confirmation/reopen → invoice, approvals and recorded payment. Every transition has a named owner, deadline, audit and visible status, with exception and duplicate-report paths. No autonomous emergency dispatch. |
| 08 | **Inspection / inventory / keys** | Custom inspection schedules and follow-ups; room-by-room check-in, mid-term and check-out inventory with dated photos, meter readings, keys/access log, tenant comments, sign-off and end-of-tenancy comparisons. Attach evidence to tenancy and property, not personal inboxes. Changes to historic evidence are versioned. |
| 09 | **Compliance and complaints** | Property-specific gas/EICR/EPC/alarms/licence fields where applicable; contractor credential/insurance expiries; agent redress/CMP membership records as appropriate; right-to-rent evidence; required notices and tenant-facing documents; due dates, document provenance, expiry alerts and responsible person. Record repairs hazards, complaints, escalation, resolution, evidence retention. Jurisdiction/property type and legal commencement dates are configurable and professionally reviewed; NO automatic declaration of legal compliance. |
| 10 | **Communications and office workflow** | Central timeline per person/property/tenancy/case; shared vs internal notes, email inbox/outbox provider configuration, templates, private attachments, recorded consent, delivery status/retry/dead-letter, complaint/repair follow-up, calendar, task ownership, reminders and overdue queue. Send/approve permissions verified server-side. |
| 11 | **Agent Desk / AI assistant / reporting** | The agent sees an evidence-linked daily action queue, search across authorised records, portfolio exceptions, void periods, repair SLA ageing, landlord rent/arrears, compliance and staff tasks. AI may summarise, suggest, classify, draft and compare case evidence with a source link, model/version and confidence caveat; **human confirmation before emailing, approving, spending, changing rights, legal decisions or external actions**. Useful KPI reports/export; no invented figures. |
| 12 | **Customer launch / operations** | Repeatable tenant/landlord/trades invitations, staff roles, real agency branding, support/complaint page, published fee/CMP/redress disclosures as applicable, agency plan/service limits, subscription/invoicing process clearly labelled manual where not automated. Privacy notice, consent, subject-access/export/delete workflows with lawful retention, MFA/strong passwords, access audit, encrypted off-server backup+restore, monitoring, accessible mobile browser and multi-agency isolation. |

**Feature not present != optional.** Finish all 12 to their described acceptance level or explicitly re-scope the release before it is called v1.

## Time-sensitive England requirements that MUST shape the data model

**Law changed on 1 May 2026 (Renters' Rights Act).** In particular:
- New and most existing assured tenancies are **periodic**. Section 21 routes are abolished for the main private-rented sector. A property/tenancy model that requires a future fixed-term end and 'renewal' for every tenancy is **wrong**. Audit `handle_tenancy_action`, tenancy `end_date`, current `renewal` states, agent prompts and UI text before acceptance.
- Advertising must show an asking rent and cannot invite/accept above-price rental bidding; prevent rent requests before the agreement is signed. Rent increase notices have a regulated method/frequency; requests to keep pets have decision rules. These are **workflow policy checks with human review**.
- Tenant Fees rules limit permitted payments and deposit amounts; track deposit and holding-deposit deadlines, evidence and refund decisions rather than a single undifferentiated "deposit" amount.
- **Private rented sector registration:** regional rollout starts **15 December 2026 in West Midlands**, and is scheduled to expand through 2027. Record registration status, number, dates, region, responsible landlord and underlying documents; reminders as rules take effect. Do not pretend Roger can submit through a government API unless verified/authorised integration exists.
- Licensing varies by council and property: track HMO/additional/selective licence applicability and numbers/expiry as configurable evidence fields, not unreviewed automated legal advice.
- If agency holds client money, client money protection requirements and trust/accounting procedures apply; otherwise provide recording/reconciliation workflows only. Redress-scheme membership, right-to-rent checks and relevant notices need auditable fields.

**Legal sources for live verification and counsel review:**
- [Renters' Rights Act overview](https://www.gov.uk/guidance/renters-rights-act-an-overview-for-landlords)
- [PRS landlord registration rollout](https://www.gov.uk/guidance/register-your-rental-property-service-guidance-for-letting-agents-and-property-managers)
- [Rent and deposit fees, updated July 2026](https://www.gov.uk/guidance/fees-you-can-charge-as-part-of-a-tenancy)
- [Right to Rent guide, October 2026](https://www.gov.uk/government/publications/landlords-guide-to-right-to-rent-checks/landlords-guide-to-right-to-rent-checks-1-october-2026-accessible)
- [Client money protection](https://www.gov.uk/client-money-protection-scheme-property-agents)
- [Letting/property manager redress](https://www.gov.uk/redress-scheme-estate-agencies)
- [HMO licensing](https://www.gov.uk/renting-out-a-property/houses-in-multiple-occupation-hmo)

This is a software acceptance plan, **not legal certification**. Keep policy effective dates and versions and schedule independent landlord/agency solicitor and accountant review of the regulated flows before release.

## Foundation decisions to avoid 50 reworks

- **One stable data spine:** never duplicate party/property/tenancy IDs in isolated pages; associate all documents, evidence, financial entries and audit events with canonical IDs.
- **One workflow engine:** explicit permission-checked state transitions and idempotency keys; no ad-hoc UI-only mutations.
- **One agency-privacy boundary:** isolated agency data plus fine-grained role/record/attachment rights and explicit share permissions.
- **Money is evidence-led:** exact integer pence, reversals not destructive edits, independent payment reconciliation and zero autonomous funds movement.
- **AI is an assistant, not an authority:** genuine model/vision tests, safety fallback, provenance, bounded inputs, consent, feedback and monitoring, all important actions requiring human confirmation.
- **Custom fields and integrations are pluggable:** add useful labelled agency/property fields and documented export/import interfaces without pre-building every portal, bank, e-sign or CRM connector.
- **Usability is a release gate:** works for a small agency managing its day from a laptop, and tenants/owners/contractors on phone browser, including empty, error and offline/interrupted connection states.
- **Migration before launch:** agency cannot adopt Roger if hundreds of properties and tenancies must be typed manually. CSV migration wizard, preview, dry-run, reconcile totals, test import and export are mandatory.
- **No intermediate production versions:** internal work may run in CI and disposable staging; production only after acceptance and a verified rollback.

## End-to-end release evidence (minimum)

These must be automated or documented on **one reproducible build**, not signed off from unrelated old tests:

1. Two separate agencies, each with two properties, joint-ownership scenario, multiple tenancies and clients. Full role/agency ID and document isolation.
2. Landlord enquiry → agency mandate → compliance/documents → rental advert → enquiry/viewing → application/referencing/holding deposit → approved periodic tenancy. No duplicate people or records.
3. Rent accounting for several periods with unpaid, late, partial, adjustment, credit, agency fee, owner statement, reconciliation failure and reversal. Exact penny totals; no claim of payment without evidence.
4. Tenant maintenance with real local text model, genuine vision model and no-model fallback, different hazard severities, quote/variation rejected/accepted, no-access, work evidence, reopen, invoice, final sign-off.
5. Inspection with room photos, meter and keys, before/after condition and checkout/dispute/evidence versioning.
6. Expired/missing licence/certificate, right-to-rent follow-up, landlord registration due and staff/contractor credential expiration. Role notification and denial scenarios.
7. Provider-backed email delivery, refused delivery, retries and idempotent duplicate prevention; relevant communication visibility per role.
8. Application and payments UX on mobile browsers; keyboard/accessibility checks; import/export with generated synthetic agency data.
9. Restore an isolated production-like clone and prove rollback, production-host capacity, security/performance scan, privacy handling, staff account recovery and operational logs.
10. Product owner and qualified legal/accounting checks where appropriate, explicit recorded release approval, then **one** safe versioned deployment.

## Deferred intentionally (do not insert later without product owner change)

Property sales and all buyer/vendor/sales-chain work, native phone apps, automatic funds transfer, proprietary Rightmove/Zoopla integration without agreements, broad HMO/block management rulesets, custom hardware/IoT, insurance underwriting, property valuations for sale, general-purpose AI agents, autonomous debt enforcement or legal notice serving. The first release can expose clear manual/export handoffs to specialist providers without pretending the integration is complete.

**Release status: OPEN.** None of this document is a declaration that Roger v1.0 is complete or deployable.
