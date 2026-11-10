# Roger v1 — B02 authentication, authorisation and agency boundary matrix

**Scope:** single active development branch `feature/roger-v1-single-release-20261108`, draft PR #14. No production/staging changes, merge, installer or release.

## 1. Security contract

- Four portal roles are **agent**, **landlord**, **tenant**, **trades**. Applicants and leads are **public, untrusted submissions**, not authenticated fifth-role accounts. Only the agency owner `agency-admin` can invite or suspend additional agent accounts, after re-entering the current password.
- Account identity is the immutable `account_id`; resource access for non-agents resolves only to **active, role-matched Party IDs**. Names, matching emails, public property labels and shared contractor companies are never sufficient ownership evidence.
- Each session is bound to its username, account ID, role, agency identifier and password fingerprint. Pre-B02 unbound tokens, expired sessions, disabled accounts, cross-agency cookies, changed roles, altered accounts and rotated passwords fail closed.
- Authentication and agency permissions are server side; UI hiding is not an access boundary. All modifying POST handlers have an explicit public or role classification; new handler registration without one fails an automated test.
- An agent's full `/api/stage` is for that agency's authenticated agents only. Landlords, tenants and trades always receive projections, not the raw business snapshot.

## 2. Complete route inventory

### Public GET — no account data

`/`, `/login`, `/signin`, `/invite`, `/invite.js`, `/staff-reset`, `/for-agents`, `/register/landlord`, `/register/trades`, `/dash.css`, `/favicon.svg`, `/sample-home.jpg`, allowlisted assets under `/_next/static/`, `/api/agency-info`, `/api/public-site`, `/api/public`, `/api/whoami` (anonymous result only without a session). Public invitation token lookup is **POST-body-only**, never a URL query/path.

### Protected GET

| Routes | Access | Further per-record condition |
| --- | --- | --- |
| `/agent` | agent | Own agency |
| `/landlord` | landlord | Party-linked only when loading data |
| `/tenant` | tenant | Party-linked only when loading data |
| `/trades` | trades | Verified Party-linked only when loading data |
| `/security`, `/change-password` | authenticated four roles | Own active session and password where required |
| `/api/stage` | all four roles | Agent raw; other roles redacted by Party/property/case/job assignment |
| `/api/deposits` | agent, tenant | Tenant's tenancy Party IDs |
| `/api/inventories` | agent, tenant, landlord | Tenant tenancy or owner property |
| `/api/tenancy-policy` | agent, tenant | Tenant must own the tenancy |
| `/api/agent/briefing`, `/api/trades-pool`, `/api/compliance`, `/api/landlord-statements`, `/api/rent-ledger`, `/api/tasks`, `/api/newsletter-subscriptions` | agent | Entire current agency only |
| `/api/landlord/rent-ledger` | landlord | Owned property only; no office notes/agency fees |
| `/api/appointments`, `/api/notifications` | all four roles | Party participant/job assignment and intended recipient |
| `/api/office-settings` | all four roles | Unpublished details visible only to agent |
| `/api/documents`, `/api/document/{id}`, `/api/document/{id}/file` | all four roles | Agent or explicit Party, tenancy, case, job and document-role links |

### Public POST — CSRF/rate/body protections still apply

`/login` (credentials and optional TOTP), `/logout` (revoke presented token),
`/api/public`, `/register/landlord`, `/register/trades`,
`/api/enquiry`, `/api/prospect-intake`, `/api/newsletter`, `/api/agent-demo`,
`/api/invite/validate`, `/api/invite/accept`,
`/api/security/staff/reset/accept` (one-use reset token, no anonymous agent privilege creation).

### Protected POST — exhaustive handler categories

| Role | POST routes |
| --- | --- |
| Agent only | `/api/registration-action`, `/api/contractor-verification`, `/api/office-settings`, `/api/access-revoke`, `/api/prospect-action`, `/api/newsletter-action`, `/api/property-action`, `/api/party-action`, `/api/tenancy-action`, `/api/deposit-action`, `/api/management-agreement-action`, `/api/email-reply`, `/api/email-sync`, `/api/rent-ledger-action`, `/api/bank-reconciliation-action`, `/api/bank-reconciliation-preview`, `/api/landlord-statement-action`, `/api/compliance-action`, `/api/property-registration-action`, `/api/task-action`, `/api/agent/property-submission`, `/api/invitation`, `/api/invitation-action`, `/api/document`, `/api/document-action`, `/api/security/staff/invite`, `/api/security/staff/suspend`, `/api/security/staff/reset` |
| Landlord only | `/api/landlord-action`, `/api/landlord/property-submission` |
| Agent + tenant | `/api/repair-diagnose`, `/api/tenant/issue`, `/api/tenancy-policy-action`, `/api/inventory-action` |
| Agent + trades | `/api/job-action`, `/api/appointment` |
| All four roles, object-scoped | `/api/case-action`, `/api/appointment-action`, `/api/notification-action` |
| All four roles, own account only | `/api/change-password`, `/api/security/mfa/start`, `/api/security/mfa/confirm`, `/api/security/mfa/disable`, `/api/security/sessions/revoke` |

The **actual authoritative POST mapping** is `H.ROLE_API`, `H.PUBLIC_POST` and `H.do_POST.handlers` in `stage-clone/serve.py`. `tests/test_b02_endpoint_security_inventory.py` compares the handler dispatch AST against the role/public sets and fails if a new handler bypasses classification.

`/api/stage` is the only full-snapshot agent read, and only an agent may inspect all records inside that agency; there is **no separate export, public staff directory, analytics endpoint or automatic background-job API** in this v1 branch. Manual email synchronisation is agent-only; the job/case handlers are synchronous and server-authorised.

## 3. Document, upload and content boundaries

- Only agent writes can upload/document-classify, with original property, tenancy, case and job linkage checks and authenticated server permissions; arbitrary private file paths are never public static assets.
- Download requires authenticated role and matching links, and sends **`Content-Disposition: attachment`**, `application/octet-stream`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: sandbox`, `Cache-Control: no-store` and a sanitised filename. This prevents uploaded HTML/SVG/script from executing as Roger-origin content.
- Metadata is allowlisted. `storage_key`, base64 document bytes, unreviewed internal notes and uploader-private fields are never returned in `safe_document`.
- Landlord and tenant `/api/stage` responses return specific property/case/job fields only: no private bank details, access codes, payment reference history, internal notes, stored attachments, private tenant contact or agent-only messages.

## 4. Account lifecycle and MFA

- **Staff invitation:** only active `agency-admin` with their *current* password; verified recipient address; unique, hash-only 48-hour token; URL **fragment**; single-use; creates `agent` role only inside the issuing agency's PostgreSQL transaction. No account can create its own staff invitation.
- **Staff suspension:** same administrator reauthentication, written reason, disable target (never self-admin), revoke every target session inside one users/stage transaction.
- **Staff password reset:** admin issues 30-minute hash-only single-use reset URL after identity verification and written reason. Recipient sets new strong password through token POST. Old password and every old session cease to work; any existing MFA remains enabled. Break-glass agency-admin recovery remains **operator-only** via `stage-clone/agency_recovery.py`; there is no unsecured public “forgot password” bypass.
- **Self password change:** existing password, 14–128 character strong replacement, fresh salt/scrypt, revoke every own session. **Self session revocation** requires present password, selectable other sessions vs all sessions.
- **Authenticator:** standard 6-digit, 30-second TOTP (SHA1/RFC6238), ±1 time-step tolerance with consumed time-step replay denial; enrolment and disable require the current password, confirm requires a valid code and revokes all prior sessions. Both the key and the OTP stay out of public/stage/log payloads.
- **Policy:** `ROGER_REQUIRE_AGENT_MFA=1` makes an agent without enrolled MFA see only `/security` and its own enrolment and revocation endpoints until a valid factor is configured. Login directs that user to the enrolment page. **Off by default on this isolated branch.** An operator must plan a staged MFA rollout before enabling the setting on any existing agency.
- **Known release caveat:** per-IP (five attempts/5 minutes) and per-account (ten attempts/15 minutes) throttles currently live **per process**, so multi-instance durable rate limiting and managed encryption/key rotation for stored TOTP secrets remain B26 deployment prerequisites. This is not presented as production-certified IAM.

## 5. Security evidence and acceptance

Regression tests cover unauthorised GET/POST role calls, cross-property and foreign-agency tokens, joined occupancy and joint-owner Party scope, stale sessions, forgotten password, staff lifecycle, consumed TOTP steps, active account suspension, failed payment/attachment permissions, unexpected error-message confidentiality and private static/download denial.

The independent SaaS CI runner now exercises **real** two-agency PostgreSQL enrolment, foreign invite/reset-token rejection, staff reset and suspension, and continuing tenant isolation in `tests/saas_invite_integration.py`. The browser suite checks four portals and login/logout/navigation, and unit tests reject newly unclassified POST routes.

**Acceptance is confined to tests on a single isolated development commit.** There is no production migration, send-mail integration, live external identity-provider binding, data movement, certificate issuance or automatic release implied by B02. The single packaged release and production-grade rate-limit/MFA key-management review belong to B26.
