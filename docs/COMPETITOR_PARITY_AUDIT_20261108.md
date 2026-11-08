# Roger v1.0 — competitor parity audit (8 November 2026)

**Scope:** The private development branch `feature/roger-v1-single-release-20261108` at PR [#14](https://github.com/eon88/Roger/pull/14). **NOT** an audit of the deployed Hostinger site. No production changes are authorised. The relevant baseline is `stage-clone/serve.py`, the four role portal pages, `agent_briefing.py`, `repair_diagnosis.py`, `repair_case_dossier.py`, the existing Python/browser tests, and `docs/ROGER_V1_SINGLE_RELEASE_PLAN.md`.

**Method:** Compare the publicly documented features of five products (plus Fixflo/Aidenn) to the source code and last completed synthetic test evidence. `FOUND` means an implemented, testable subset—not equivalent breadth, usability, support or commercial reliability. `PARTIAL` means some functions exist but important behaviour or release acceptance remains open. `NOT DEMONSTRATED` means no equivalent end-to-end implementation could be established from this review. These labels never establish production readiness.

## Competitor benchmark

| Competitor | What its official documentation demonstrates | Roger's overlap | Largest gap |
| --- | --- | --- | --- |
| **Street.co.uk** | Sales+lettings CRM, viewing management, client apps, AI maintenance triage, landlord statements, rent arrears, contractor compliance, AI writing/onboarding, AI call handler, integrations | Portals, repair/approvals, property/tenancy records, narrow AI repair intake, ledger/statement subset | Integrated sales-to-lettings journey, proactive lead/AI operations, accurate portal sync, robust client accounting, mature compliance |
| **Reapit** | End-to-end sales/lettings/property management, viewings, payment/reconciliation, partner ecosystem; 2026 Reapit AI announcement describes voice-first copilot, marketplace and builder (rollout stages should be checked) | Lettings/property/contractor workflow core | Full sales progression/chains, production-grade client accounts, AI agents across business, reporting and ecosystem |
| **Alto / PropertyFile** | Buyer, vendor, applicant, landlord and tenant portals; e-signing; applicant offers/viewing feedback; tenancy timeline and balances; AI writing, applicant matching and analytics | Tenant, landlord, trades and Agent Desk portals, selected application/tenancy fields | Buyer/vendor/applicant portals, e-signing, bank reconciliation, multi-office diary and matching, AI insights |
| **Arthur Online** | Occupant/landlord/contractor/manager apps; issue-to-work-order, multiple quotes, contractor acceptance/decline, evidence and invoices; portfolio/room-level management, portal syncing, automated reminders, Fixflo integration | Strongest overlap: repairs, quote+approval chain, contractor verification, visits, statements and role scoping | Automated/exception-rich work order workflow, multiple contractors, mature document/evidence handling, inspections and integrations |
| **agentOS** | Highly customisable sales+lettings CRM, open V4 APIs across appointments/applications/deposits/documents/inspections/maintenance/reporting, portals and partner integrations, bank reconciliation | CRM domain objects, basic management and accounting records | Custom field engine, comprehensive supported API and external integrations, accounting, marketing and reporting |

**Specialist AI benchmark — Fixflo/Aidenn:** Chat intake, optional image analysis, chat transcript, report summarising fault/troubleshooting, suggested parts and work orders. Roger has guided text intake, a locally demonstrated text model, an unverified structured dossier and emergency escalation. True photo understanding, detailed contractor-parts report, complete transcript, broad troubleshooting library and actual outcome/false-negative benchmarks remain NOT DEMONSTRATED. No claim of engineering diagnosis or emergency response is warranted.

Official sources:
- [Street product index](https://street.co.uk/product/index); [Street property management](https://live.street.co.uk/product/property-management); [Street Cortex](https://cortex.street.co.uk/)
- [Reapit lettings](https://www.reapit.com/platform/lettings-crm); [Reapit AI announcement, April 2026](https://www.reapit.com/press-releases/reapit-sets-the-direction-for-the-ai-powered-estate-agency)
- [Alto PropertyFile overview](https://support.altosoftware.co.uk/hc/en-gb/articles/5048069878431-PropertyFile-Overview); [Alto product features](https://www.altosoftware.co.uk/product-features/); [Alto Intelligence, October 2026](https://support.altosoftware.co.uk/hc/en-gb/articles/5742191676831-Alto-Intelligence-Overview)
- [Arthur workflow management](https://www.arthuronline.co.uk/features/workflow-management); [Arthur property management](https://www.arthuronline.co.uk/features/property-management-system)
- [agentOS V4 API](https://hub.agentos.com/-what-is-the-agentos-api-and-what-can-it-do); [agentOS lettings](https://agentos.com/software/lettings-overview/)
- [Fixflo AI report](https://help.fixflo.com/support/solutions/articles/61000319590-fixflo-ai-reporting-what-happens-in-fixflo-when-an-issue-is-reported); [Fixflo tenant AI intake](https://help.fixflo.com/support/solutions/articles/61000319589-fixflo-ai-reporting-what-tenants-see-when-they-report-an-issue)

## Roger: checked capabilities

| Feature | Code in branch | Audit status |
| --- | --- | --- |
| Public property listings and acquisition forms | `index.html`, `serve.py` property/public/prospect actions | **PARTIAL** — working local publication/enquiry paths; no proven multi-portal syndication |
| Four role portals and access controls | `agent.html`, `landlord.html`, `tenant.html`, `trades.html`, `serve.py` | **FOUND**, browser tested with synthetic users; not equivalent to Alto's buyer/vendor/applicant portals |
| People/properties/tenancy lifecycle | `handle_party_action`, `handle_property_action`, `handle_tenancy_action` | **PARTIAL** — objects and transitions, not full end-to-end business experience |
| Leads/appointments | `handle_prospect_action`, `handle_appointment` | **PARTIAL** — no demonstrated AI qualification, live viewing booking, listing recommendations or full sales offers |
| Sales progression / chains | No dedicated implemented module established | **NOT DEMONSTRATED** |
| Tenant repair / contractor / landlord approval | `handle_tenant_issue`, `handle_case_action`, `handle_job_action`, `handle_landlord_action` | **FOUND** — synthetic four-role happy path tested; exception/operational acceptance remains |
| Structured repair evidence | `repair_case_dossier.py`; `agent.html` evidence panel | **FOUND**, server validation/urgency recomputation; user-submitted statements remain unverified |
| Local AI symptom questions | `repair_diagnosis.py`; tenant portal | **FOUND** in synthetic real-Ollama text browser test |
| Actual AI photo diagnosis | Optional Ollama vision code but no genuine vision-model success case | **NOT DEMONSTRATED** |
| AI copilot across agency / lead acquisition | `agent_briefing.py` is a read-only rules-based priority list | **NOT DEMONSTRATED** as a cross-application agent; no autonomous communications |
| Financials | `handle_rent_ledger_action`, `handle_landlord_statement_action`, invoice/payment records | **PARTIAL** — manual external payments and snapshots, no verified live bank reconciliation/client-money readiness |
| Compliance / inspections | `handle_compliance_action`, documents, appointments | **PARTIAL** — basic certificate records, expiry tracking; formal inspections, inventory and evolving requirements remain |
| Messaging / notifications | `handle_email_sync`, notification and thread actions | **PARTIAL** — provider-backed delivery, complete queue and multi-channel communication unproved |
| Agent Desk workflow priority | `agent_briefing.py` and `agent.html` | **FOUND** for read-only evidence-linked operational signals; incomplete if source records are missing |
| Customisable fields and public integration API | No comparable documented extensibility framework established | **NOT DEMONSTRATED** |
| Native app, mobile browser | Responsive HTML; mobile browser test coverage for public site | **PARTIAL** — no full role-based mobile acceptance or native apps |
| Agency hosting / subscriptions | `ops/saas/provision_agency.py`, `docs/SAAS_AGENCY_MVP.md` | **PARTIAL** — separate app/database per agency works in isolated CI; no self-serve subscription/billing or production multiagency scalability claim |
| Backup / recovery / security assurance | Existing scripts, sandbox CI restore, role isolation tests | **PARTIAL** — production-like disaster recovery and security validation are release blockers |

## Release blockers, ordered by dependence

**P0 — core business parity**
1. Finish usable agent-led sales/lettings funnel: public lead → applicant matching/viewing → offer/reference → tenancy/notice/checkout. If the target is *full estate agency* parity rather than lettings-first, explicit seller/vendor sales progression and chains must also be built.
2. Close finance gaps: true reconciliation evidence, detailed landlord statements/arrears/fees and export capability; regulated client-money handling needs accountant/compliance sign-off.
3. Complete property/tenancy/client portal experience across all roles, including safe document sharing, evidence, renewals and clear change history.
4. Expand maintenance exception flows and model diagnostics, including actual photo testing, multiple quotes, safety accuracy review, role-correct contractor details and agent approval gates.

**P1 — operational parity**
5. Rule-based compliance checklists, inspection/inventory and required reminder workflows; configurable policies that avoid inaccurate legal claims.
6. Reliable automation engine for case actions, approvals, rent/certificate follow-ups with idempotent retries, alerts and delivery tracing.
7. AI drafting, applicant/tenant matching, agent copilot and analytics grounded in the tenant/property database, subject to explicit confirmation for external action.
8. API/integration design, agency configuration, optional portal syndication and communications providers with permission checks.

**P0 — must be passed before the ONE deployment**
9. Verify real role-based end-to-end browser journeys on a populated synthetic multi-agency stack and on mobile widths.
10. Run security/privacy and accessibility review, capacity measurements, backup+RESTORE on a genuinely production-like clone, rollback rehearsal and release sign-off.
11. No interim production deployments or customer installs. Branch commits are incremental **development work, not releases**.

## Interpretation

**Closest competitor today: Arthur Online for the maintenance/lettings workflow. Biggest functionality gaps: full CRM sales progression, accounting/reconciliation, automated integrations, flexible analytics and business-wide AI.**

Do **not** assign a fabricated parity percentage. These competitors have paid modules and integrations; documentation cannot verify every feature's current availability, quality or bundle. Roger's green CI jobs verify synthetic tests, **not** parity or commercial readiness. As of this audit, the complete single v1.0 release is **NOT READY**.
