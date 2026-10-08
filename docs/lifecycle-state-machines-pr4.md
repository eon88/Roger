# Roger lifecycle state machines — Priority 4

This document records lifecycle boundaries for properties, tenants, landlords and trades. It distinguishes implemented workflow from target workflow so a prospect-stage label is not mistaken for a legal tenancy or an approved account.

## Property

**Implemented in the current branch** by `/api/property-action` and Agent Desk property controls.

`prospect → onboarding → ready_to_market → advertised → application → let_agreed → occupied → notice_given → checkout → void → remarketing → advertised`

Valid alternatives are explicitly constrained in the server transition map: onboarding/ready-to-market may return or offboard; advertised/application/let-agreed may return to marketing or void; notice may be withdrawn to occupied; void may remarket or offboard; offboarded is terminal. A direct jump is rejected with 409.

Public visibility requires all of:

- `lifecycle_status = advertised`
- non-empty marketing description
- valid title, area, bedroom count and rent

The public endpoint returns only the safe marketing projection. No tenant or landlord fields are included. Existing records without a status are treated as onboarding. When no live listing qualifies, the public site's labelled sample fallback remains.

## Tenant

**Prospect stages implemented:** `enquiry → viewing → application → referencing → approved → offer → converted`, with `closed` available from any stage. These stages are agent-maintained pipeline notes on the original enquiry record and preserve its message, submitted contact details and consent.

**Tenancy lifecycle implemented on this branch:** an agent can create a tenancy application linked to a Property, one or more landlord/tenant Party IDs, and an optional source enquiry. The record stores start/end dates, rent amount/frequency, deposit amount and separate agreement status. The workflow advances through application, referencing, approval, offer, agreement, deposit, move-in scheduled, active, renewal, notice, checkout, deposit resolution and former tenant; cancellation is available before move-in.

Move-in requires a signed agreement and a property at `let_agreed`. Activation moves the property to occupied; notice, checkout and former-tenant transitions move it through matching property states. Notice and checkout dates are explicit, signed agreement snapshots cannot be rewritten, and active occupancies suppress public listing visibility. Every transition is timestamped and audited.

Portal account linking and tenant access are still not implemented. A Party or Tenancy record does not grant portal access. Deposit scheme/reference metadata can be stored, but payment processing, rent ledger, reminders, and tenancy document workflows remain future work. Existing records are not auto-migrated from names; uncertain identity matches remain for agent review.

## Landlord

**Implemented on this branch:** an approved landlord registration can be explicitly linked to a Party without matching or merging by email. Agent Desk management agreements record one landlord Party, one or more properties, service type, fee, evidence note, signed date, status and transition history. A signed date and evidence note are recorded before activation; end dates cannot precede signature. The landlord prospect cannot reach `signed`, `onboarding` or `active` without the linked approved registration and matching agreement. Ending an agreement retains its record and audit history.

Property onboarding checklists, compliance collection, portfolio reporting, landlord portal access and finance statements remain future work. The `active` prospect label does not grant access or imply that those systems are complete.

## Trades

**Implemented on this branch:** trades applicants progress through `applicant → credentials_submitted → checked → approved → available`, with explicit valid transitions to `suspended` or `rejected`. An agent check is timestamped and attributed. The registration approval endpoint rejects an unchecked trades applicant. `approved` and `available` also require registration approval. Suspended registrations are removed from the assignment pool while their prior jobs remain intact. Agent Desk shows submitted trade categories, Gas Safe number, insurance expiry, coverage and check date where supplied.

Per-job states remain separate: assignment, quote request, quote decision, work, invoice and payment. Performance ratings, credential expiry reminders and a full contractor document vault remain future work.

## Cross-lifecycle rules

- Every state change is agent-initiated, timestamped and audited.
- Source submissions, signed documents and financial records are snapshots; state changes do not rewrite them.
- State changes do not by themselves grant portal access, approve spending, certify safety or create a legal agreement.
- Return paths, closures and offboarding are explicit; history is retained.
- Later reminders and overdue work require a real due date field, not age-based guesses.
