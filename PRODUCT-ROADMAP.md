# Roger — Product Roadmap

Roger is a **single-agent estate agency operating system**.

Its job is to bring **landlords, tenants and tradespeople under one roof**, while allowing **one estate agent to coordinate the entire operation**.

The product has two clear faces:

- **Front end = advertising and acquisition**
- **Back end = management and orchestration**

This document is the working roadmap. We will tackle it one item at a time and update the checklist as Roger evolves.

---

# 1. North Star

Roger should feel like one connected system, not four separate portals.

```text
                         PUBLIC / ADVERTISING
                  ┌─────────────────────────────┐
                  │ Properties to rent          │
                  │ Attract landlords           │
                  │ Recruit trades              │
                  │ Capture enquiries           │
                  └──────────────┬──────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │       AGENT DESK        │
                    │                         │
                    │   ONE AGENT CONTROLS    │
                    │      EVERYTHING         │
                    └─────┬────────┬──────────┘
                          │        │
                ┌─────────┘        └──────────┐
                ▼                             ▼
          LANDLORDS                         TENANTS
        properties/money                homes/issues/rent
                │                             │
                └───────────┐     ┌───────────┘
                            ▼     ▼
                             TRADES
                       repairs/quotes/jobs
```

Everything should run on one shared operational spine:

```text
PEOPLE
  ↓
PROPERTIES
  ↓
TENANCIES
  ↓
CASES / EVENTS
  ↓
JOBS / TASKS
  ↓
MONEY
  ↓
DOCUMENTS
  ↓
COMMUNICATIONS
  ↓
AUDIT / HISTORY
```

---

# 2. Core product rules

- [ ] The **public site exists to advertise and acquire business**.
- [ ] The **private portal exists to manage properties and relationships**.
- [ ] The **Agent Desk is the orchestration layer for the whole system**.
- [ ] Landlord, Tenant and Trades portals are role-specific views into the same underlying data.
- [ ] Do not create duplicate workflow engines for each role.
- [ ] A real-world event should be stored once and surfaced differently depending on role.
- [ ] AI assists with triage, routing, drafting and reminders.
- [ ] AI must not replace human control over legal, safety, credential or money decisions.
- [ ] Every important action should leave an audit trail.
- [ ] The agent should be able to answer: **What needs my attention today?**

---

# 3. Current strengths

Roger already has useful foundations:

- [x] Public property / advertising front end
- [x] Landlord registration
- [x] Trades registration
- [x] Tenant enquiries
- [x] Role-based authentication
- [x] Agent portal
- [x] Landlord portal
- [x] Tenant portal
- [x] Trades portal
- [x] Cases
- [x] Message threads
- [x] Maintenance jobs
- [x] Trade assignment
- [x] Quote requests
- [x] Quote approval / decline
- [x] Landlord approval flow
- [x] Standing authority concept
- [x] Trades credential gating
- [x] Appointments
- [x] Invitations
- [x] Documents
- [x] Audit log
- [x] AI / Jev triage
- [x] Docker deployment
- [x] Persistent runtime storage
- [x] HTTPS
- [x] Automatic deployment from GitHub

---

# 4. Biggest architectural gap

Roger currently has a strong **case / repair / job** spine, but the central estate-agency relationship is still missing as a first-class model.

The core relationship should be:

```text
LANDLORD
   │
   ▼
PROPERTY
   │
   ▼
TENANCY
   │
   ├── TENANT
   ├── RENT
   ├── DEPOSIT
   ├── DOCUMENTS
   ├── INSPECTIONS
   ├── COMPLIANCE
   ├── MAINTENANCE
   └── COMMUNICATION
```

The next major architectural objective is therefore:

- [ ] Make **People**, **Property** and **Tenancy** first-class objects.
- [ ] Link all cases, jobs, money, documents and communication back to those objects.

---

# 5. Build order

## PHASE 1 — Foundation: People, Property, Tenancy

### 1.1 People
Create a shared person / organisation model instead of treating names as loose strings.

- [ ] Person ID
- [ ] Name
- [ ] Email
- [ ] Phone
- [ ] Role(s)
- [ ] Address
- [ ] Preferred contact method
- [ ] Account status
- [ ] Notes
- [ ] Created / updated dates
- [ ] Link a person to one or more properties
- [ ] Allow one person to hold multiple roles where appropriate
- [ ] Distinguish individuals from companies

### 1.2 Properties
Turn properties into full operational objects.

- [ ] Property ID
- [ ] Full address
- [ ] Landlord link
- [ ] Current tenant / tenancy link
- [ ] Beds / type / rent
- [ ] Marketing details
- [ ] Photos
- [ ] Property status
- [ ] Management status
- [ ] Maintenance history
- [ ] Compliance summary
- [ ] Document list
- [ ] Financial summary
- [ ] Activity timeline

### 1.3 Property lifecycle
Introduce explicit property states:

- [ ] Prospect
- [ ] Onboarding
- [ ] Ready to market
- [ ] Advertised
- [ ] Application
- [ ] Let agreed
- [ ] Occupied
- [ ] Notice given
- [ ] Checkout
- [ ] Void
- [ ] Remarketing
- [ ] Offboarded

Public listings should be driven directly by property state.

Example:

```text
property.status = advertised
→ automatically show property on public website
```

### 1.4 Tenancies
Make tenancy a first-class object.

- [ ] Tenancy ID
- [ ] Property
- [ ] Landlord
- [ ] Tenant(s)
- [ ] Start date
- [ ] End date
- [ ] Rent amount
- [ ] Rent frequency
- [ ] Deposit amount
- [ ] Deposit scheme / reference
- [ ] Agreement status
- [ ] Tenancy status
- [ ] Move-in date
- [ ] Notice date
- [ ] Checkout date
- [ ] Linked documents
- [ ] Linked cases
- [ ] Linked inspections
- [ ] Linked rent ledger

---

# 6. Tenant lifecycle

Roger should manage the complete tenant journey:

- [ ] Enquiry
- [ ] Viewing
- [ ] Application
- [ ] Referencing
- [ ] Approved
- [ ] Offer / let agreed
- [ ] Agreement
- [ ] Deposit
- [ ] Move-in
- [ ] Active tenancy
- [ ] Renewal
- [ ] Notice
- [ ] Checkout
- [ ] Deposit resolution
- [ ] Former tenant

The goal is:

```text
PUBLIC ENQUIRY
    ↓
PROSPECT
    ↓
VIEWING
    ↓
APPLICATION
    ↓
APPROVED
    ↓
TENANCY
    ↓
TENANT PORTAL
```

- [ ] Avoid manually re-entering a prospect as a tenant.
- [ ] Preserve the history from first enquiry onward.

---

# 7. Landlord lifecycle

The landlord journey should be equally complete:

- [ ] Lead
- [ ] Initial conversation
- [ ] Valuation / appraisal
- [ ] Proposal
- [ ] Management terms
- [ ] Signed agreement
- [ ] Property onboarding
- [ ] Compliance collection
- [ ] Ready to market
- [ ] Active landlord
- [ ] Portfolio management
- [ ] Offboarding

Goal:

```text
PUBLIC LANDLORD ENQUIRY
        ↓
LANDLORD PROSPECT
        ↓
PROPOSAL
        ↓
SIGNED CLIENT
        ↓
PROPERTY ONBOARDING
        ↓
LANDLORD PORTAL
```

- [ ] A landlord registration should naturally become a real landlord record.
- [ ] A landlord should be able to own multiple properties.
- [ ] Portfolio-level reporting should be supported.

---

# 8. Trades lifecycle

Trades should move through a controlled contractor pipeline:

- [ ] Applicant
- [ ] Credentials submitted
- [ ] Credentials checked
- [ ] Approved
- [ ] Available
- [ ] Assigned
- [ ] Quote requested
- [ ] Quote submitted
- [ ] Approved
- [ ] Work started
- [ ] Work completed
- [ ] Invoice submitted
- [ ] Paid / closed
- [ ] Performance history
- [ ] Suspended / rejected

Trade profiles should eventually include:

- [ ] Company
- [ ] Contact
- [ ] Trade categories
- [ ] Coverage area
- [ ] Gas Safe / licence information where relevant
- [ ] Insurance
- [ ] Expiry dates
- [ ] Documents
- [ ] Jobs completed
- [ ] Average response time
- [ ] Rating / internal notes

---

# 9. Public front end / advertising engine

The public site should become three acquisition funnels.

## 9.1 Tenant acquisition

- [x] Property search
- [x] Property detail page
- [x] Photos / gallery
- [x] Rent / deposit information
- [x] Availability
- [x] Enquire
- [x] Request viewing
- [x] Application
- [x] Progress into tenant pipeline

## 9.2 Landlord acquisition

- [x] Clear landlord value proposition
- [x] Management services
- [x] Let-only / management offer
- [ ] Pricing
- [x] Landlord enquiry
- [x] Valuation request
- [x] Registration
- [x] Progress into landlord CRM pipeline

## 9.3 Trades acquisition

- [x] Contractor value proposition
- [x] Trade categories wanted
- [x] Coverage expectations
- [x] Registration
- [ ] Credential upload
- [x] Progress into contractor approval pipeline

**Priority 9 implementation:** the public front end is now a three-funnel acquisition screen. Tenant visitors can search available homes, open a property detail modal, see rent/deposit/availability, and submit enquiry, viewing or application requests into `/api/enquiry` with property context preserved. Landlords can send valuation and management enquiries into the landlord CRM pipeline or open the full registration form. Trades can submit contractor interest with categories, coverage and credential notes, or open the full registration form. Real pricing tables and credential document upload remain open.

---

# 10. Agent Desk — the operating cockpit

The Agent Desk should become the most important screen in Roger.

The opening question is:

> **What needs the agent today?**

## 10.1 Daily command centre

- [x] Urgent maintenance
- [x] Safety-critical items
- [x] New tenant enquiries
- [x] New landlord enquiries
- [x] New trades applications
- [x] Approvals waiting
- [x] Quotes waiting
- [x] Appointments today
- [x] Overdue actions
- [x] Rent arrears
- [x] Tenancies ending soon
- [x] Compliance expiring soon
- [x] Unread conversations

Suggested structure:

```text
TODAY
────────────────────────
Urgent
Waiting on me
Waiting on landlord
Waiting on tenant
Waiting on trades
Upcoming
Overdue
Recently resolved
```

## 10.2 Global search

- [x] Search people
- [x] Search properties
- [x] Search cases
- [x] Search jobs
- [x] Search documents
- [x] Search by email / phone / reference

## 10.3 Global timeline

- [x] See every important event chronologically
- [x] Filter by property
- [x] Filter by person
- [x] Filter by case
- [x] Filter by event type

**Priority 10 implementation:** the Agent Desk overview now includes a Today cockpit with explicit counts for urgent maintenance, safety-critical cases, new tenant enquiries, landlord enquiries, trades applications, approvals, quotes, today's appointments, overdue actions, rent arrears, tenancies ending soon, compliance deadlines and unread conversations. Global search covers people, properties, cases, jobs, communications, registrations, appointments, documents, compliance records and contact references. The activity log is filterable by property, person, case/reference and event type.

---

# 11. Communications hub

Internal threads are only the first step.

The long-term goal:

```text
EMAIL
SMS
PORTAL
WHATSAPP
PHONE NOTE
        ↓
     ROGER
        ↓
PROPERTY / PERSON / TENANCY / CASE
        ↓
ONE TIMELINE
```

- [x] Unified inbox
- [ ] Attach communication to person
- [x] Attach communication to property
- [ ] Attach communication to tenancy
- [x] Attach communication to case
- [x] Agent reply from one place
- [ ] Draft assistance
- [ ] Templates
- [x] Message status
- [x] Read / unread
- [x] Follow-up reminders
- [x] Internal notes
- [x] Email integration
- [ ] SMS integration
- [ ] WhatsApp integration if appropriate
- [ ] Telephone call notes

**Priority 11 implementation:** the Communications hub groups cases as conversations with property and contact context, supports portal replies and SMTP replies from one screen, and stores agent-only internal notes. Cases now have an agent read marker, mark-read/mark-unread controls, unread counts in the inbox and Today cockpit, and follow-up dates that flow into overdue attention. Manual IMAP sync remains the email bridge. Party/tenancy attachment, draft assistance, templates, SMS, WhatsApp and phone-call notes remain open.

Principle:

> All communications about a property should eventually become one chronological story.

---

# 12. Maintenance engine

This is already one of Roger's strongest areas.

The complete lifecycle should be:

```text
Tenant reports issue
        ↓
AI triage
        ↓
Safety check
        ↓
Agent review
        ↓
Approval needed?
      /       \
    no         yes
    ↓           ↓
dispatch     landlord
              approval
      \       /
       contractor
           ↓
         quote
           ↓
         work
           ↓
        invoice
           ↓
      completion
           ↓
    tenant confirmation
           ↓
         close
```

Remaining gaps:

- [x] Photos on maintenance reports
- [x] Attachments
- [ ] SLA timers
- [x] Appointment scheduling linked to jobs
- [ ] Automatic reminders
- [ ] Contractor arrival / completion updates
- [x] Tenant confirmation
- [x] Reopen if unresolved
- [ ] Before / after evidence
- [ ] Better job history
- [ ] Contractor performance history

**Priority 12 implementation:** tenants can now attach up to four image/PDF evidence files when reporting a maintenance issue; the files are stored as private document records and linked to the case and job. Resolved repairs show tenant controls to confirm the fix or reopen the case as unresolved, and both actions are audited. Appointment booking was already linked to cases. SLA timers, automatic reminders, contractor arrival/completion updates, before/after completion evidence, richer job history and contractor performance history remain open.

---

# 13. Money / financial engine

This is one of the biggest missing areas.

## 13.1 Rent ledger

- [x] Rent due schedule
- [x] Amount due
- [x] Amount received
- [x] Date received
- [x] Balance
- [x] Arrears
- [x] Partial payments
- [x] Adjustments
- [x] Notes

## 13.2 Agency fees

- [x] Management fee
- [ ] Letting fee
- [ ] Renewal fee if applicable
- [x] Other charges
- [ ] VAT handling if applicable

## 13.3 Maintenance money flow

- [x] Quote
- [x] Standing authority limit
- [x] Landlord approval
- [x] Invoice
- [x] Payment status
- [x] Cost attached to property
- [x] Cost attached to landlord statement

## 13.4 Landlord statements

- [x] Rent received
- [x] Agency fees
- [x] Maintenance deductions
- [x] Other deductions
- [x] Net landlord amount
- [x] Statement period
- [ ] Downloadable statement
- [ ] Payment status

Long-term flow:

```text
TENANT RENT
    ↓
RENT LEDGER
    ↓
AGENCY FEE
    ↓
MAINTENANCE COSTS
    ↓
LANDLORD STATEMENT
    ↓
LANDLORD PAYOUT
```

**Priority 13 implementation:** the Money tab has rent schedules, receipts, partial payments, adjustments, arrears, management-fee snapshots, quote/invoice/payment states, landlord approval above standing authority and landlord statement snapshots with rent, fees, maintenance and net payout totals. Letting fees, renewal fees, VAT, downloadable statements and landlord payout/payment status remain open.

---

# 14. Compliance engine

Compliance should become proactive instead of being only document storage.

Each property should have a compliance dashboard.

Example:

```text
12 Arlington Road

Gas Safety              ✅
EICR                    ✅
EPC                     ⚠ expires soon
Smoke alarms            ✅
Deposit protection      ✅
Right to Rent           ✅
Tenancy agreement       ✅
Inventory               ✅
Landlord authority      ✅
```

Build:

- [x] Compliance requirement types
- [ ] Required-by-property rules
- [x] Document link
- [x] Issue date
- [x] Expiry date
- [x] Status
- [x] Expiring soon
- [x] Expired
- [x] Missing
- [x] Reminder schedule
- [x] Agent action
- [ ] Renewal appointment
- [x] Replacement document
- [x] Audit history

Potential compliance records:

- [x] Gas Safety
- [x] EICR
- [x] EPC
- [x] Smoke / CO alarms
- [x] Deposit protection
- [x] Right to Rent
- [x] Tenancy agreement
- [x] Inventory
- [x] Landlord authority / management agreement
- [x] Trades credentials / insurance

Legal requirements must be reviewed against current jurisdiction before production use.

**Priority 14 implementation:** the Compliance tab records requirement types, issue/expiry/reminder dates, missing evidence, document links, replacement/superseded history, derived status and due reminders in the Agent Desk. Requirement applicability rules and renewal appointment automation remain open.

---

# 15. Documents

Documents should become proper objects attached to the right entity.

- [x] Property documents
- [x] Tenancy documents
- [x] Tenant documents
- [x] Landlord documents
- [x] Trades documents
- [x] Job documents
- [x] Compliance documents
- [x] Version history
- [x] Verification status
- [x] Expiry date
- [x] Access rules
- [x] Search
- [x] Download
- [x] Replace / supersede
- [x] Audit trail

Eventually move document files out of the JSON database into proper file/object storage.

**Priority 15 implementation:** documents now support property, tenancy, party, job and case links; role-based access lists; expiry dates; verification state; private downloads; searchable Agent Desk library; and replacement/supersede metadata with version increments and audit history. Uploaded file bodies remain outside JSON in the private content-addressed store.

---

# 16. Appointments / diary

- [x] Viewing
- [x] Inspection
- [x] Contractor visit
- [x] Valuation
- [x] Check-in
- [x] Check-out
- [x] Key handover
- [x] Compliance visit
- [x] Agent appointment

Needs:

- [x] Calendar view
- [x] Agenda view
- [x] Participants
- [x] Confirmation
- [x] Decline / reschedule
- [x] Reminders
- [x] Outcome
- [x] Link to property
- [x] Link to case / job
- [ ] External calendar integration later

**Priority 16 implementation:** appointments now have explicit diary types, participant roles and linked people, reminder times, confirmation/reschedule/cancel/missed/completed states, outcomes, and property/case/job relationships. The Agent Desk includes a dedicated Appointments tab with booking, a seven-day calendar and searchable agenda. External calendar sync remains a future integration item.

---

# 17. Tasks and automation

Roger should gradually move from passive storage to proactive operation.

- [x] Task object
- [x] Owner
- [x] Due date
- [x] Priority
- [x] Related property/person/tenancy/case/job
- [x] Status
- [x] Reminder
- [x] Recurring task

Examples:

- [x] Chase landlord approval
- [x] Chase contractor quote
- [x] Check tenant after repair
- [x] Renew EPC
- [x] Arrange gas inspection
- [x] Follow up landlord prospect
- [x] Follow up tenant application
- [x] Tenancy renewal reminder
- [x] Rent arrears follow-up

**Priority 17 implementation:** Roger now has agent-owned tasks with title, owner, priority, due date, reminder time, recurrence, status, description and links to property, person/organisation, tenancy, case and job records. The Agent Desk includes a Tasks tab, quick templates for the common operational follow-ups, search/filtering and dashboard surfacing for urgent, due-soon and overdue tasks.

---

# 18. Notifications

Roger needs real outbound notification capability.

- [ ] In-app notifications
- [ ] Email
- [ ] Reminder emails
- [ ] Agent alerts
- [ ] Landlord approval request
- [ ] Tenant appointment notification
- [ ] Trades job notification
- [ ] Compliance reminder
- [ ] Rent / arrears reminder

Later:

- [ ] SMS
- [ ] WhatsApp where appropriate

---

# 19. AI layer

AI should be useful but subordinate to the workflow.

Current:

- [x] Basic triage
- [x] Category
- [x] Urgency
- [x] Safety
- [x] Keyword fallback

Future:

- [ ] Suggested next action
- [ ] Draft responses
- [ ] Thread summarisation
- [ ] Extract structured facts from messages
- [ ] Detect duplicate issues
- [ ] Detect urgency
- [ ] Detect safety risks
- [ ] Suggested trade category
- [ ] Summarise property history
- [ ] Summarise landlord account
- [ ] Morning Agent Desk briefing
- [ ] Flag overdue / abnormal situations
- [ ] Search across the system in natural language

Guardrails:

- [ ] No autonomous legal decisions
- [ ] No autonomous safety sign-off
- [ ] No autonomous contractor credential approval
- [ ] No autonomous large payment approval
- [ ] Human-visible reasoning / evidence for important recommendations

---

# 20. Technical foundation

The current Python + JSON implementation has been useful for proving the product.

It should not remain the final data architecture once Roger starts carrying real agency data.

## 20.1 Database

- [ ] Design relational schema
- [ ] Move from `stage.json` to PostgreSQL
- [ ] Preserve IDs and history
- [ ] Migration script
- [ ] Backups
- [ ] Restore procedure
- [ ] Database transactions
- [ ] Indexes
- [ ] Concurrency-safe writes

Core relationships:

```text
Person
 ↕
Property
 ↕
Tenancy
 ↕
Case
 ↕
Job
 ↕
Invoice
 ↕
Document
```

## 20.2 Files

- [ ] Move uploaded document bodies out of JSON
- [ ] Proper persistent file/object storage
- [ ] File metadata in database
- [ ] Secure downloads
- [ ] Virus scanning later
- [ ] Backup policy

## 20.3 Authentication / security

- [ ] Production-grade user/account management
- [ ] Password reset
- [ ] Account invitations
- [ ] Secure cookies
- [ ] CSRF protection
- [ ] Session management
- [ ] Login audit
- [ ] Role permissions
- [ ] Object-level permissions
- [ ] Account disable
- [ ] Rate limiting
- [ ] Security headers
- [ ] Backups
- [ ] Secrets management

## 20.4 Reliability

- [ ] Automated tests
- [ ] Workflow tests
- [ ] Role-permission tests
- [ ] Health checks
- [ ] Error logging
- [ ] Monitoring
- [ ] Backup verification
- [ ] Deployment rollback

---

# 21. UX cleanup

The portals should increasingly feel like one coherent product.

- [ ] Shared design language
- [ ] Shared navigation patterns
- [ ] Mobile usability
- [ ] Consistent statuses
- [ ] Consistent action wording
- [ ] Empty states
- [ ] Loading states
- [ ] Errors that explain what to do next
- [ ] Search everywhere it matters
- [ ] Filters
- [ ] Sorting
- [ ] Pagination where needed
- [ ] Accessibility
- [ ] Keyboard navigation

---

# 22. Six engines of Roger

The mature product can be understood as six connected engines:

| Engine | Purpose |
|---|---|
| Advertising | Bring tenants, landlords and trades into the system |
| CRM | Turn strangers into prospects, clients and portal users |
| Tenancy | Manage the landlord-property-tenant relationship |
| Operations | Cases, repairs, inspections, appointments and tasks |
| Money | Rent, fees, approvals, invoices and landlord statements |
| Compliance | Documents, certificates, deadlines and obligations |

Above all six sits:

# THE AGENT DESK

Roger is not intended to replace the estate agent.

Roger exists to let **one estate agent operate the entire agency with leverage**.

---

# 23. Immediate priority queue

We will tackle these in order unless a real operational need changes the priority.

## Priority 1 — Core data model

- [x] **1A. Design People model** — [design](docs/people-model-1a.md)
- [x] **1B. Design Property model** — [design](docs/property-model-1b.md)
- [x] **1C. Design Tenancy model** — [design](docs/tenancy-model-1c.md)
- [x] **1D. Define relationships between them** — [design](docs/core-relationships-1d.md)
- [x] **1E. Map existing Roger data into the new model** — [mapping](docs/existing-data-map-1e.md)

## Priority 2 — Agent Desk

- [x] Build “What needs me today?” — Agent Desk command centre
- [x] Waiting-on states — approvals, trade work/quotes and appointment replies
- [x] Overdue items — explicit due dates plus past confirmed appointments needing an outcome
- [x] Upcoming items — confirmed appointments in the next seven days
- [x] Unified search — current properties, cases, jobs, registrations, appointments and documents; legacy names/contact values included

**Priority 2 implementation:** the Agent Desk command centre, waiting-on sections, upcoming appointments, overdue-date checks and unified record search are implemented in `stage-clone/agent.html`. The overdue view uses explicit due fields and past confirmed appointments; it does not infer deadlines from record age. Search preserves focus through the 15-second refresh. HTML parsing and JavaScript syntax checks pass.

## Priority 3 — CRM / acquisition pipelines


- [x] Tenant prospect pipeline — enquiry, viewing, application, referencing, approval, offer, conversion, closed
- [x] Landlord prospect pipeline — lead, conversation, valuation, proposal, terms, signed, onboarding, active, closed
- [x] Trades applicant pipeline — applicant, credentials, checked, approved, available, suspended, rejected

**Priority 3 implementation:** the Agent Desk now has separate tenant, landlord and trades pipelines. Stage changes persist on the source enquiry/registration, append history and write an audit event. Registration approval remains a separate permission gate. Five endpoint regression tests pass.


## Priority 4 — Property / tenancy lifecycle

**Property lifecycle implementation:** Agent Desk properties now move through validated states. Public `/api/public` serves only explicitly advertised properties with a complete description and safe marketing fields; private owner/tenant data is excluded. Existing property records without a state default to onboarding, and the site's sample fallback remains when no live listing qualifies.

**Lifecycle design:** [State machines and dependencies](docs/lifecycle-state-machines-pr4.md). Tenant and Tenancy stages use Party ID links, source enquiry, agreement state, explicit dates and property-state synchronization. Landlord registrations link to Party records, and management agreements capture property scope, terms, signed evidence and active/ended states. Trades credentials must be marked checked before approval; suspended trades are excluded from new assignments. Portal account linking, portfolio reporting, credential expiry reminders and trades performance history remain open. Thirty-eight endpoint regression tests cover these workflows; Python compilation, HTML parsing and JavaScript syntax checks pass.

- [x] Property state machine — agent-approved transitions and public listing gate
- [x] Tenant lifecycle — prospect through active, notice, checkout and former tenant
- [x] Landlord lifecycle — approved registration to linked Party, signed management authority, onboarding and active gate
- [x] Trades lifecycle — credential check, approval, availability and suspension gates

## Priority 5 — Communications

- [x] Unified communication timeline — case messages grouped with contact and property context
- [x] Inbox — filter by text and property; reply into the existing case thread
- [x] Email integration — agent-triggered IMAP inbox sync and SMTP replies with case audit history

**Priority 5 implementation:** communications are grouped by case and property; exact contact email matching attaches incoming messages to the newest matching case or creates a new email case. SMTP replies go only to the email already on the case, and mail actions are recorded in the timeline and audit log. Setup: [outbound and inbound email](docs/outbound-email-setup.md). Provider OAuth, automatic polling, bounce/delivery tracking and attachments remain future work.

## Priority 6 — Money

- [x] Rent ledger — scheduled charges, partial receipts, adjustments and derived arrears
- [x] Agency fees — percentage snapshots on rent received under active full-management terms
- [x] Landlord statements — immutable period snapshots of rent, fees and paid maintenance
- [x] Invoice/payment states — existing maintenance approval and paid transitions remain linked to jobs

**Priority 6 implementation:** signed tenancies can generate an idempotent schedule (up to 36 periods) using the rent frequency. Receipts cannot exceed the outstanding balance; adjustments require reasons and cannot reduce charges below receipts. Active management agreements snapshot fees on receipts. Period statements capture recorded rent, fees and paid maintenance, and prevent duplicate generation for the same landlord/period. This is manual recordkeeping; Roger does not verify bank receipts or transfer funds. Statements and fee calculations require an active management agreement linked to the property.

## Priority 7 — Compliance

- [x] Compliance records — property requirement, dates, notes and linked document
- [x] Expiry tracking — current, expiring soon, expired and superseded states
- [x] Reminders — explicit reminder dates surfaced in Agent Desk attention

**Priority 7 implementation:** agents can record missing evidence or dated documents by property and requirement. New records supersede older versions without deleting history. Expiry status and due reminders use saved dates and appear in the command centre. The workflow does not decide legal applicability, validate documents, or send automatic reminders. See [compliance workflow](docs/property-compliance-priority7.md).

## Priority 8 — Technical migration

- [ ] PostgreSQL — production store cutover and relational migration
- [x] Proper file storage — private content-addressed file store, legacy extraction utility and backup support (deployment must point `ROGER_FILES_DIR` at durable storage)
- [x] Security hardening — atomic JSON replacement and mode 0600 for stage/user snapshots and document files
- [x] Test suite — GitHub Actions workflow plus endpoint, storage and backup tests
- [x] Backups — validated private archive, SHA-256 manifest and restore runbook

**Priority 8 progress:** file-backed writes are atomic, snapshots and uploaded files use owner-only permissions, and CI runs the regression suite. The backup utility archives validated stage/user snapshots and the configured document directory outside the live data directory. New uploads are stored as private content-addressed files; a legacy extractor moves existing bodies out of JSON. PostgreSQL has an opt-in runtime backend and migration bridge, but the application still defaults to JSON until a real database target is provisioned and verified.

---

# 24. Working method

For each roadmap item:

1. Define the real-world workflow.
2. Identify who uses it.
3. Define the data needed.
4. Define state transitions.
5. Define permissions.
6. Define Agent Desk actions.
7. Define what each role sees.
8. Implement the smallest complete version.
9. Test it as Agent, Landlord, Tenant and Trades where relevant.
10. Mark the item complete here.
11. Move to the next item.

---

# 25. Next item

**Priority 1 design set complete:** People, Property, Tenancy, relationship rules and the existing-data map are in `docs/`. Agent-managed Party and Tenancy records now use stable IDs, while legacy names remain untouched and are not used to grant new access.

**Completed on this branch:** Agent Desk daily command centre and search; tenant, landlord and trades prospect pipelines; property lifecycle and public listing gate; tenant/tenancy lifecycle with agreement and dated move-in/notice/checkout transitions.

**Priority 5 complete:** Agent Desk has a communications inbox, case/property/contact context, portal replies, SMTP outbound email, and manual IMAP inbox sync. Email credentials are deployment configuration and are not stored in Roger data.

**Priority 6 complete:** Rent schedules and receipt tracking, active-agreement fee snapshots, landlord statement snapshots and the maintenance invoice/payment lifecycle are available in the Agent Desk.

**Priority 7 complete:** property compliance records, replacement history, expiry states and manual reminders are available in the Agent Desk.

**Priority 8 progress:** CI, atomic local persistence, private document files, migration tooling and operator-run backups are in place. PostgreSQL is the remaining technical foundation item; cutover needs a provisioned database and a verified restore path.

**Priority 9 progress:** the public advertising page now works as three acquisition funnels. Tenants can search homes, view property details and submit enquiry, viewing or application requests with property context. Landlords and trades can send funnel-specific enquiries into the existing CRM/approval pipelines and still reach the full registration forms. Pricing tables and credential document upload remain open.

**Priority 10 progress:** the Agent Desk now has a Today cockpit for urgent work, safety risk, new enquiries/applications, waiting approvals, quotes, appointments, arrears, ending tenancies, compliance deadlines and unread conversations. Global search is live across the main operational objects, and the activity log can be filtered by property, person, case/reference and event type.

**Priority 11 progress:** the Communications hub now has unread/read state, one-place portal/email replies, internal notes and follow-up dates on case conversations. Messages remain tied to cases and properties; direct Party/tenancy threading, draft help, templates, SMS, WhatsApp and telephone notes remain open.

**Priority 12 progress:** tenant maintenance reports can now carry private image/PDF evidence files into the case, document store and job record. Tenants can confirm a resolved repair or send it back as unresolved, with both decisions audited. SLA timers, automatic reminders, contractor arrival/completion updates, before/after completion evidence and performance history remain open.

**Priority 13 progress:** the existing Money tab already covers rent schedules, receipts, arrears, partial payments, adjustments, management-fee snapshots, maintenance quote/invoice/payment states, landlord approval above standing authority and statement snapshots. Downloadable statements, payout/payment status, letting fees, renewal fees and VAT remain open.

**Priority 14 progress:** compliance records now cover common requirement types, linked documents, issue/expiry/reminder dates, missing evidence, replacement history, derived statuses and Agent Desk reminders. Required-by-property rules and renewal appointment automation remain open.

**Priority 15 progress:** the document library now supports property, tenancy, person/organisation, job and case links; role access rules; verification status; expiry dates; private downloads; searchable Agent Desk records; and replace/supersede version history. Files remain in the private content-addressed store.

**Priority 16 progress:** the appointments diary now supports all planned appointment types, participant roles and linked people, confirmations, decline/reschedule flow, reminder times, outcomes, property links and case/job links. The Agent Desk has a dedicated calendar-plus-agenda view. External calendar sync remains open for a later integration pass.

**Priority 17 progress:** task records now cover owners, due dates, priority, reminders, recurrence, status and related property/person/tenancy/case/job links, with an Agent Desk task board and common follow-up templates.

Next: **Priority 18 — Notifications**, with PostgreSQL cutover parked until a database is provisioned.
