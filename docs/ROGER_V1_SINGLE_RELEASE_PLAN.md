# Roger v1.0 — one-release programme

**Date:** 8 November 2026 · **Work branch:** `feature/roger-v1-single-release-20261108`

## Release promise

**One installation/deployment, after all agreed release gates pass.** All implementation commits, experiments, model changes and test failures stay on this development branch or disposable test infrastructure. Do not merge to main, replace the working Hostinger deployment, migrate production data, or direct a user to install partial releases. The existing production system remains untouched. Rollback must be demonstrated from a current encrypted production backup **before** launch.

The goal is to reproduce the *functional level* of modern lettings/property-management platforms in original code. Do not copy competitor proprietary implementation, UI assets, confidential data, or protected brands. "Parity" applies to the **England-first small letting agency and property-management use case**, not every sales, auctions, block management, client-money or enterprise feature advertised by giant competitors.

## Evidence from five competitors (+ specialised Fixflo)

Primary sources, reviewed 8 November 2026:

| Platform | Publicly documented capabilities worth reproducing |
| --- | --- |
| [Street.co.uk feature index](https://street.co.uk/product/index) and [platform](https://street.co.uk/) | Sales and lettings CRM, lead management, booking and calendar, multi-branch workflows, tenant/landlord apps, AI maintenance triage, contractor compliance, rent/arrears, statements, AI onboarding, AI call handler, notifications |
| [Reapit lettings CRM](https://www.reapit.com/platform/lettings-crm) | Tenancy progression, viewing bookings, works orders, compliance checklists and certificate tracking, renewals and client accounting; [client accounting](https://www.reapit.com/platform/client-accounts) also supports reconciliation and landlord payments |
| [Alto PropertyFile tenant](https://support.altosoftware.co.uk/hc/en-gb/articles/5048069943327-PropertyFile-Tenant-Portal) and [landlord](https://support.altosoftware.co.uk/hc/en-gb/articles/5048084684959-PropertyFile-Landlord-Portal) | Property/tenancy timeline, rent/deposit/account summary, repair reporting and status, selective sharing of documents, landlord statements, viewings/feedback and maintenance transparency |
| [Arthur Online stakeholder apps](https://support.arthuronline.co.uk/support/solutions/articles/202000052158/) and [repair workflows](https://www.arthuronline.co.uk/features/workflow-management) | Separate apps for manager, tenant, contractor and owner; contractor updates, work orders, reminders, evidence and links to Fixflo |
| [agentOS property management](https://agentos.com/software/property-management/) and [V4 API](https://hub.agentos.com/-what-is-the-agentos-api-and-what-can-it-do) | Inspections/inventories, certificates and reminders, keys, contractor job/invoice flows, configurable fields, API/integration architecture |
| [Fixflo Aidenn](https://help.fixflo.com/support/solutions/articles/61000319590-fixflo-ai-reporting-what-happens-in-fixflo-when-an-issue-is-reported) | Structured AI report, photos and fault summary, troubleshooting history, suggested parts, chat audit, agent to-do; *full diagnostic equivalence is not yet demonstrated* |

These are publicly documented products. Real tenant/agent UI interactions behind paid logins, internal code, SLAs, security standards, and all optional tiers cannot be inferred.

## Roger inventory against target

Status refers to *code on the development baseline and automated tests*, not a production certification.

| Area | Roger starting point | v1.0 gap and acceptance |
| --- | --- | --- |
| Public marketing / leads | **Partial:** listings, tenant enquiries, landlord and trades funnels | Accurate property publication state, lead stages, agent responses, no placeholder offers, mobile browsing, conversion/audit tests |
| Agency accounts / multitenancy | **Partial:** per-agency isolated stacks, invite/first-login, owner recovery | Lifecycle, staff permissions, MFA/recovery, documented data export, complete cross-agency permission/browser tests, provisioning controls |
| People / Properties / Tenancies | **Partial:** linked Party, property and tenancy models in SaaS branch | Full lifecycle and immutable IDs, multiple tenants/owners, dates/rent/deposits, no duplicated person/property records, safe migrations |
| Landlord portal | **Partial:** onboarding, linked property view, approvals | statements/marketing/viewings, explicit document sharing, fully joined portfolio history and period reports |
| Tenant portal | **Partial:** reports, case progress, documents, appointments | tenancy timeline, balances and deposits, complete repair interview, mobile usability and access/privacy |
| Trades portal | **Partial:** approval, qualification/insurance gates, quotes/invoices, visits | uploads, renewals, independent verification workflow, accurate attendance/evidence, service areas, performance history |
| Repairs / approvals | **Strong code-tested foundation**: four-role workflow incl. variations, evidence, landlord approvals | full exception branches, automated reminders, audit, multiple work orders per issue where legitimate; safety checks |
| AI repair assistant | **Experimental code-tested**: rule screening + local text model interview | structured server-side diagnostic provenance, real vision tests, safe questions, symptom/asset guidance, optional video escalation only if integration available |
| Agent Desk | **Partial:** Today/inbox, cases, jobs, tasks | one actionable briefing from all subsystems, search, priorities and provenance; human-reviewed actions |
| Communications | **Partial:** threads and some email plumbing | central timeline, delivery/retry with verified provider, internal versus shared notes, ownership and data minimisation |
| Rent / accounts | **Partial:** ledger, invoices, landlord statement snapshots, manually recorded external payments | reconciled payment evidence, rent adjustments/arrears, bank integration *only with accounting review*, end-to-end exact-pence tests; no claim of regulated client-money readiness |
| Compliance / inspections | **Partial:** certificates and tasks | jurisdiction rules, expiries/escalations, inventories, visit/inspection evidence and reminders |
| Automation / integrations | **Partial:** event-based tasks, email and external settings | robust scheduler/queue, idempotent delivery, retry/dead-letter, audit, agency-by-agency configuration, minimal safe API |
| Reliability / deployment | **Partial:** regression and browser CI, isolated SaaS tests, backups/restore scripts | restored production-like clone, recovery evidence, capacity/load testing on target host, security audit, accessibility and monitoring |

## Fixed acceptance gates for the *single* v1.0 release

1. **Functional baseline:** four independent portals and public marketing use the same authoritative property/person/tenancy/case/invoice identifiers. No contradictory statuses or manual re-entry.
2. **Life cycle:** lead → property onboarding → listing → applicant/viewing → tenancy → renewal/notice → checkout survives reload and has negative-permission tests.
3. **Repair life cycle:** resident → guided AI/rules → agent review → contractor → quote/owner authority → appointment → completion → resident resolution → invoice/recorded external payment; urgent/decline/reopen/variation/timeout/duplicate branches are checked.
4. **Financial controls:** rent charges/receipts, arrears, fees and landlord statements have correct amount/date ownership; no claims of verified payments without reconciliation evidence. Legal/accounting review gates regulated processing.
5. **Compliance:** valid requirement mapping per property/jurisdiction, document lifecycle, accurate expiry warnings and externally checked contractor credentials.
6. **Automation:** scheduled cases, missed appointments, contractor and approval follow-ups, compliance renewals; errors/retries never duplicate important actions.
7. **AI:** safe fallback, no autonomous legal/financial/safety decisions, auditable model provenance, synthetic real-model and vision checks, human oversight, clear explanation of why an action is suggested.
8. **Security:** server-side role/property/agency scoping for every endpoint, file, export and notification; CSRF, secret handling, user lifecycle and privacy testing.
9. **Usability:** desktop and Android-width browser journeys for all roles; labelled controls, loading/errors, working buttons and no hidden or broken flows.
10. **Operations:** automated regression + Chromium acceptance, model-load and concurrency tests, backups with a validated separate restoration, monitoring, alerts and capacity measurements.
11. **Commercial readiness:** clear agency subscription/onboarding, invoicing/billing only if actually integrated, support/export/deletion procedure and appropriate legal terms.
12. **Release:** only after *every* gate above is explicitly marked PASS with links to tests and human review where needed, take production backup, verify rollback on an isolated replica, then execute **one** reviewed versioned deployment. No unreviewed interim production changes.

## Build order *on the same branch*

- **A. Evidence and data spine:** structure/IDs, property/tenancy relationships, source-backed repair diagnostic object and audit records, common Agent Desk.
- **B. Lifecycle and portals:** complete applicant, landlord and tenant flows, staff/trades, forms and exception paths.
- **C. Operations:** repair/job/visit, compliance, inspections, finance, communications, task automation.
- **D. AI and integrations:** text/vision diagnosis, landlord/tenant summary, action suggestions linked to evidence, reliable notification queue.
- **E. Independent acceptance:** realistic synthetic 2-agency/2-property scenarios, role denial, real browser/AI/vision tests, restoration and load.
- **F. One launch:** only after all previous areas pass; release review and signed-off production operation.

### Progress convention

`IMPLEMENTED` means the code exists. `UNIT-TESTED` means isolated tests pass. `BROWSER-TESTED` means real browser interaction is demonstrated. `ACCEPTED` requires all stated criteria. **Never mark a feature ACCEPTED solely because a green test job appears.**

### Active work in this branch

- [x] Baseline experimental AI repair interview with genuine Ollama text/Chromium run, safety fallback and no vision claim.
- [x] Five-platform comparative evidence and single-release criteria documented.
- [ ] Complete the remaining v1.0 feature and operations gates.
- [ ] Final single release deployed (must remain unchecked until explicit deployment).
