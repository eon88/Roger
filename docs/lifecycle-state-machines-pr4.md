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

**Tenancy stages still require a first-class Tenancy model:** `agreement → deposit → move_in → active → renewal`, then `notice → checkout → deposit_resolution → former_tenant`. A withdrawn notice returns to active; an unsuccessful application closes the prospect without creating a tenancy. Move-in, notice and checkout dates must be explicit. A tenancy transition must never be inferred from a free-text property tenant name or a prospect's pipeline stage.

Before implementing these states, Roger needs stable Party IDs, tenant-to-tenancy participation, a property-to-tenancy link, date history, document links, and account access derived from verified Party relationships. Current sample data has none of those records or dates; migration must leave uncertain identities unresolved for agent review.

## Landlord

**Prospect stages implemented:** `lead → conversation → valuation → proposal → terms → signed → onboarding → active`, with `closed` for withdrawn or declined prospects. These stage changes do not constitute an executed management agreement. Approval remains separate, and source registration data remains intact.

A future offboarding flow must end management authority while retaining property, tenancy, finance and audit history. Existing records do not encode signed agreement evidence, so Roger must not imply a contract exists from the `signed` label alone.

## Trades

**Applicant stages implemented:** `applicant → credentials_submitted → checked → approved → available`; `suspended` and `rejected` are controlled end/hold states. The pipeline stage does not replace the existing registration approval or credential gate. The API blocks `approved`/`available` until registration approval is recorded.

Per-job states remain separate: assignment, quote request, quote decision, work, invoice and payment. A trades profile can have many job histories; completing one job must not change its overall approval or availability state.

## Cross-lifecycle rules

- Every state change is agent-initiated, timestamped and audited.
- Source submissions, signed documents and financial records are snapshots; state changes do not rewrite them.
- State changes do not by themselves grant portal access, approve spending, certify safety or create a legal agreement.
- Return paths, closures and offboarding are explicit; history is retained.
- Later reminders and overdue work require a real due date field, not age-based guesses.
