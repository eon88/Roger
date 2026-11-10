# Roger v1.0 — B03 agency onboarding progress

**Branch:** `feature/roger-v1-single-release-20261108`
**Status:** PARTIAL / ACTIVE. Not accepted; not released. Production remains unchanged.
**Scope:** England-only residential lettings and management, no sales.

## B03 implementation added (10 November 2026)

- `stage-clone/agency_admin.py`: a dedicated agency profile with agency ID/hostname binding, agency and office business identity, colour branding, branches, explicit subscription/operational statuses, optimistic version checks, contact validation, and restricted host-operator lifecycle transitions. A fresh stack has no fictitious contacts or paid subscription.
- `ops/saas/provision_agency.py`: every fresh, dedicated PostgreSQL agency snapshot now receives its own profile and empty agency-event history; separate secrets and data remain independently provisioned.
- `stage-clone/serve.py`: administrator-only GET/POST agency profile API. Writes require current administrator password via existing B02 verified identity and always audit changes. Staff cannot edit plan/limits/status via this endpoint; safe public display name and brand colour are allowlisted.
- `stage-clone/agency-admin.html` and Agent Desk link: edit office identity, contacts, branding and named branches with a browser form. The package, limits and billing states are explicitly marked manual and operator-controlled.
- `stage-clone/agency_operator.py`: trusted, agency-bound operator command for plan, activation, suspension, reactivation, invoice record, overdue record and cancellation. The command checks the dedicated stack identity, requires written reasons, logs agency events and never deletes agency records or charges a card. Suspension/cancellation revoke current sessions. Cancellation requires an independently reviewed export/retention reference; supplying this reference does not produce the export.
- Runtime: suspended/cancelled instances deny public submissions and authenticated portal/API traffic, while a different agency stays available. Assigned plans enforce staff-seat limits on new invitations and property limits when new landlord submissions are approved. Unassigned legacy/pilot profiles remain backward-compatible.
- Tests: `tests/test_b03_agency_settings.py` and `tests/test_b03_operator_and_limits.py` cover configuration, injection/privileged-field rejection, plan validation, operator agency boundary, suspension, cancellation and data-retention guard. The pre-existing SaaS two-agency integration still runs in disposable GitHub Actions.
- Agent Desk: protect an active tenancy form from its 15-second automatic rerender. This fixes an independently observed browser-test interruption and needs fresh acceptance verification.

## Remaining B03 gates (do not check off yet)

1. **B03.01:** prove a complete new agency bootstrap, real address, emergency contacts and operator verification with a live browser and an independent second agency.
2. **B03.02:** enforce branch-level staff/property assignments and delegated permissions rather than merely storing descriptive branch fields. Confirm spending authorities are actually enforced.
3. **B03.03:** complete and test a traceable manual subscription/invoicing lifecycle, including plan changes, expiry, nonpayment policy and real limit enforcement for all applicable creation pathways. Never label invoices paid without reviewed external evidence.
4. **B03.04:** complete authorised agency data export/retention, support escalation and post-cancellation access/backup policy. Do not delete customer data automatically.
5. **B03.05:** test invitation URLs/expiry and revocation for tenant/owner/trades/staff from two independent agency hostnames under active, suspended and cancelled states.
6. **B03.06:** execute a fresh two-agency bootstrap/offboarding smoke and real PostgreSQL + attachment backup/restore on disposable isolated copies. Run same-SHA mandatory gate, including full browser and negative-case tests.

## Evidence / caution

- Initial B03 integration and tests through `46749e9d5914310ab229e967a3f1498e236e3265`: Python and isolated two-agency SaaS CI passed; full browser CI was failing in a tenancy-form rerender case, NOT a verified B03 acceptance. A focused form-refresh fix was committed as `8536f7826bed93b7d98c1bf5be9faed7842d319a`; follow-up browser and aggregate checks are required.
- Existing B01/B02 foundations remain accepted only for synthetic development, not production release.
- **No B04 work, merges, production DNS changes, Hostinger deployment or customer installation is authorised by these commits.**
