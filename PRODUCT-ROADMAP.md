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

- [ ] Property search
- [ ] Property detail page
- [ ] Photos / gallery
- [ ] Rent / deposit information
- [ ] Availability
- [ ] Enquire
- [ ] Request viewing
- [ ] Application
- [ ] Progress into tenant pipeline

## 9.2 Landlord acquisition

- [ ] Clear landlord value proposition
- [ ] Management services
- [ ] Let-only / management offer
- [ ] Pricing
- [ ] Landlord enquiry
- [ ] Valuation request
- [ ] Registration
- [ ] Progress into landlord CRM pipeline

## 9.3 Trades acquisition

- [ ] Contractor value proposition
- [ ] Trade categories wanted
- [ ] Coverage expectations
- [ ] Registration
- [ ] Credential upload
- [ ] Progress into contractor approval pipeline

---

# 10. Agent Desk — the operating cockpit

The Agent Desk should become the most important screen in Roger.

The opening question is:

> **What needs the agent today?**

## 10.1 Daily command centre

- [ ] Urgent maintenance
- [ ] Safety-critical items
- [ ] New tenant enquiries
- [ ] New landlord enquiries
- [ ] New trades applications
- [ ] Approvals waiting
- [ ] Quotes waiting
- [ ] Appointments today
- [ ] Overdue actions
- [ ] Rent arrears
- [ ] Tenancies ending soon
- [ ] Compliance expiring soon
- [ ] Unread conversations

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

- [ ] Search people
- [ ] Search properties
- [ ] Search cases
- [ ] Search jobs
- [ ] Search documents
- [ ] Search by email / phone / reference

## 10.3 Global timeline

- [ ] See every important event chronologically
- [ ] Filter by property
- [ ] Filter by person
- [ ] Filter by case
- [ ] Filter by event type

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

- [ ] Unified inbox
- [ ] Attach communication to person
- [ ] Attach communication to property
- [ ] Attach communication to tenancy
- [ ] Attach communication to case
- [ ] Agent reply from one place
- [ ] Draft assistance
- [ ] Templates
- [ ] Message status
- [ ] Read / unread
- [ ] Follow-up reminders
- [ ] Internal notes
- [ ] Email integration
- [ ] SMS integration
- [ ] WhatsApp integration if appropriate
- [ ] Telephone call notes

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

- [ ] Photos on maintenance reports
- [ ] Attachments
- [ ] SLA timers
- [ ] Appointment scheduling linked to jobs
- [ ] Automatic reminders
- [ ] Contractor arrival / completion updates
- [ ] Tenant confirmation
- [ ] Reopen if unresolved
- [ ] Before / after evidence
- [ ] Better job history
- [ ] Contractor performance history

---

# 13. Money / financial engine

This is one of the biggest missing areas.

## 13.1 Rent ledger

- [ ] Rent due schedule
- [ ] Amount due
- [ ] Amount received
- [ ] Date received
- [ ] Balance
- [ ] Arrears
- [ ] Partial payments
- [ ] Adjustments
- [ ] Notes

## 13.2 Agency fees

- [ ] Management fee
- [ ] Letting fee
- [ ] Renewal fee if applicable
- [ ] Other charges
- [ ] VAT handling if applicable

## 13.3 Maintenance money flow

- [ ] Quote
- [ ] Standing authority limit
- [ ] Landlord approval
- [ ] Invoice
- [ ] Payment status
- [ ] Cost attached to property
- [ ] Cost attached to landlord statement

## 13.4 Landlord statements

- [ ] Rent received
- [ ] Agency fees
- [ ] Maintenance deductions
- [ ] Other deductions
- [ ] Net landlord amount
- [ ] Statement period
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

- [ ] Compliance requirement types
- [ ] Required-by-property rules
- [ ] Document link
- [ ] Issue date
- [ ] Expiry date
- [ ] Status
- [ ] Expiring soon
- [ ] Expired
- [ ] Missing
- [ ] Reminder schedule
- [ ] Agent action
- [ ] Renewal appointment
- [ ] Replacement document
- [ ] Audit history

Potential compliance records:

- [ ] Gas Safety
- [ ] EICR
- [ ] EPC
- [ ] Smoke / CO alarms
- [ ] Deposit protection
- [ ] Right to Rent
- [ ] Tenancy agreement
- [ ] Inventory
- [ ] Landlord authority / management agreement
- [ ] Trades credentials / insurance

Legal requirements must be reviewed against current jurisdiction before production use.

---

# 15. Documents

Documents should become proper objects attached to the right entity.

- [ ] Property documents
- [ ] Tenancy documents
- [ ] Tenant documents
- [ ] Landlord documents
- [ ] Trades documents
- [ ] Job documents
- [ ] Compliance documents
- [ ] Version history
- [ ] Verification status
- [ ] Expiry date
- [ ] Access rules
- [ ] Search
- [ ] Download
- [ ] Replace / supersede
- [ ] Audit trail

Eventually move document files out of the JSON database into proper file/object storage.

---

# 16. Appointments / diary

- [ ] Viewing
- [ ] Inspection
- [ ] Contractor visit
- [ ] Valuation
- [ ] Check-in
- [ ] Check-out
- [ ] Key handover
- [ ] Compliance visit
- [ ] Agent appointment

Needs:

- [ ] Calendar view
- [ ] Agenda view
- [ ] Participants
- [ ] Confirmation
- [ ] Decline / reschedule
- [ ] Reminders
- [ ] Outcome
- [ ] Link to property
- [ ] Link to case / job
- [ ] External calendar integration later

---

# 17. Tasks and automation

Roger should gradually move from passive storage to proactive operation.

- [ ] Task object
- [ ] Owner
- [ ] Due date
- [ ] Priority
- [ ] Related property/person/tenancy/case/job
- [ ] Status
- [ ] Reminder
- [ ] Recurring task

Examples:

- [ ] Chase landlord approval
- [ ] Chase contractor quote
- [ ] Check tenant after repair
- [ ] Renew EPC
- [ ] Arrange gas inspection
- [ ] Follow up landlord prospect
- [ ] Follow up tenant application
- [ ] Tenancy renewal reminder
- [ ] Rent arrears follow-up

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

## Priority 3 — CRM / acquisition pipelines

**Priority 2 implementation:** the Agent Desk command centre, waiting-on sections, upcoming appointments, overdue-date checks and unified record search are implemented in `stage-clone/agent.html`. The overdue view uses explicit due fields and past confirmed appointments; it does not infer deadlines from record age. Search preserves focus through the 15-second refresh. HTML parsing and JavaScript syntax checks pass.


- [x] Tenant prospect pipeline — enquiry, viewing, application, referencing, approval, offer, conversion, closed
- [x] Landlord prospect pipeline — lead, conversation, valuation, proposal, terms, signed, onboarding, active, closed
- [x] Trades applicant pipeline — applicant, credentials, checked, approved, available, suspended, rejected

## Priority 4 — Property / tenancy lifecycle

**Property lifecycle implementation:** Agent Desk properties now move through validated states. Public `/api/public` serves only explicitly advertised properties with a complete description and safe marketing fields; private owner/tenant data is excluded. Existing property records without a state default to onboarding, and the site's sample fallback remains when no live listing qualifies.

**Lifecycle design:** [State machines and dependencies](docs/lifecycle-state-machines-pr4.md). Tenant tenancy stages, management-agreement evidence and trades performance history remain unimplemented. The tenant lifecycle depends on implementing Tenancy records and date-bound access relationships.


**Priority 3 implementation:** the Agent Desk now has separate tenant, landlord and trades pipelines. Stage changes persist on the source enquiry/registration, append history and write an audit event. Registration approval remains a separate permission gate. Five endpoint regression tests pass.


- [x] Property state machine — agent-approved transitions and public listing gate
- [ ] Tenant lifecycle
- [ ] Landlord lifecycle
- [ ] Trades lifecycle

## Priority 5 — Communications

- [ ] Unified communication timeline
- [ ] Inbox
- [ ] Email integration

## Priority 6 — Money

- [ ] Rent ledger
- [ ] Agency fees
- [ ] Landlord statements
- [ ] Invoice/payment states

## Priority 7 — Compliance

- [ ] Compliance records
- [ ] Expiry tracking
- [ ] Reminders

## Priority 8 — Technical migration

- [ ] PostgreSQL
- [ ] Proper file storage
- [ ] Security hardening
- [ ] Test suite
- [ ] Backups

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

## 1A — People model

**Design complete:** [Canonical People model](docs/people-model-1a.md). The design separates Parties (individuals and organisations), role assignments, login accounts, and prospect/application records. It uses stable IDs for relationships and prevents email matches from granting access or silently merging identities.

Next: **1B — Property model**, including how Parties own, occupy, manage and work at properties.
