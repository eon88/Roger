# Roger repairs pilot — build/test handoff
Updated 11 October 2026 · Working branch: `feature/roger-fast-mvp-20261011`

## Scope
Focused England-first small-agency pilot. The repair process is built in stages and tested with synthetic cases. These are not a legal-compliance certificate or permission to handle real client money.

## Completed and code-tested
- [x] Tenant reports create a private case with evidence, not an immediate public job. Only an agent can review and dispatch a case, with a required reason. Repeated dispatch is blocked.
- [x] Agent sends quote request to an approved, account-linked trades Party. New work cannot be directly assigned or self-claimed without approval.
- [x] New repair quotes are approved **before** work starts. A signed active full-management mandate tied to the real property owner supplies that property's spending limit; a quote over it requires that landlord's explicit approval. Changes to the mandate invalidate pending owner approval.
- [x] Contractor identity for a new repair is resolved by linked Party ID, approved registration, checked credentials, relevant trade and current insurance. Revalidate before approval/start. Suspended/unlinked/expired contractors are blocked. An unverified claimed Gas Safe number does not authorise a gas job.
- [x] The contractor may start only when pre-work approval is recorded. An invoice above the approved amount is refused pending a separately approved variation process (not built yet).
- [x] Work completion, tenant confirmation/reopening, invoice submitted, invoice approved and **manually recorded external payment** are separate. An invoice cannot become paid merely because the agent or landlord approved it. No payment provider is connected.
- [x] Tenant, landlord and trades screens now reflect the main revised states.
- [x] Removed fictitious tenant email, office phone/email, fake verified gas engineer, and false emergency response-time promises from the pilot screens.
- [x] Synthetic four-role back-end end-to-end test; property-isolation and denial tests; existing four-role browser smoke.

## Task 01 — appointment and property access implementation (11 October 2026)

**Development only; not deployed.** This step is **partly accepted** pending the dedicated full browser journey and access-policy review.

- [x] Assigned and authorised contractor can propose a real job-linked visit; a second active visit is rejected.
- [x] Tenant explicitly accepts or requests a new time, including after a previous confirmation; rescheduling cancels earlier contact/access consent.
- [x] Wrong tenant, landlord, unrelated contractor or trade cannot confirm on behalf of the resident.
- [x] Agent has an accurate diary; contractor sees confirmed times and only consented access preferences; no key codes or entry credentials are collected.
- [x] Missed/no-access and parts-delay outcomes require a reason and do **not** complete the job, submit an invoice or close the repair.
- [x] Work authorisation is rechecked before confirming or changing a contractor visit; withdrawn approval blocks the visit.
- [x] New role, cross-property, wrong-job, time validation, consent, reschedule and delay regression tests. Standard Python tests and the existing four-role portal browser smoke pass.
- [ ] Run the dedicated full visit browser test (`node tests/visit_browser_smoke.cjs`) in isolated CI and record the run link. The script exists, but it is **not yet wired into the GitHub Actions workflow**; an attempted workflow edit was blocked. The existing browser smoke does not cover the full visit journey.
- [ ] Office review: confirm acceptable access instructions, tenant contact consent and any safe, offline key handover process. Never store lockbox codes in general appointment notes.

**Current status:** built on the feature branch with regression coverage; awaiting full browser proof and office acceptance. Do not call Task 01 DONE or proceed to Task 02 until those gates are met.

## Next P0 tasks (NOT DONE)
1. Appointments and access: propose/accept/reschedule/cancel/no-access, contact consent, key instructions and a parts-delay branch. Block misleading “scheduled” statuses.
2. Case control: single next person/action and due date, duplicate reporting/idempotency, internal/private vs shared notes, disputes, reopening after completed work.
3. Financial completion: itemised quotes, VAT, quote version/scope receipt, approved variations, invoice number/duplicate check, partial payments, credits, reconciliation. Keep all money external until a reviewed accounting route exists.
4. Contractor proof: evidence attachments, independent credential check (especially regulated trades), verification expiry, service-area checks and re-review. Gas dispatch remains blocked without explicit verified proof.
5. Office settings and delivery: real agency contact and emergency policy, notifications with failure/retry, audit, account invitations/access revocation, tested restore.
6. Database safety: PostgreSQL currently also uses shared JSON snapshots; implement transaction-safe concurrent updates and verify independent tenancy/agency access at API/file level.
7. True populated browser pilot for all four roles (current browser smoke checks portals and property submissions; the full repair path is unit-tested with synthetic fixtures but not yet with browser clicks).

## Release status
All work here is on the GitHub feature branch. **Not merged or deployed to the production Hostinger Roger.** Release only after security/data checks, fresh backup, passing CI and an explicit production decision. The live application remains on the previous deployed version.
