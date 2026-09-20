# Stage — MVP Ship Readiness (CMO assessment)

_Assessed 2026-09-20 22:46–22:52 by the ship-readiness persona (mvp-ship-readiness
playbook). Walked all four portals live in a browser as agent/tenant/landlord/trades
plus the public funnel. Report compiled by the parent session from the assessor's
full transcript (the assessor finished reconnaissance but its session died before
writing this file). Scores: 0–10, evidence-based._

## Verdict: **SHIP-CAREFUL**

The operating loop is genuinely good. What blocks real customers is the legal
surface (a stranger cannot tell who they're handing their home to) and pricing.
Five P0s below; none require building new features — mostly words, memberships,
and one hosting decision.

## Scorecard

| dimension | score | evidence (where the assessor looked) |
|---|---|---|
| Positioning & first sentence | 5 | Public home (`/`) communicates "homes to rent + register as landlord/trades" fine, but ZERO company identity: no entity name, address, phone, "who we are" — searched every public page for privacy/redress/deposit/fees keywords: absent on all |
| First-10-customers plan | 3 | Not in product; README states intent only. Birmingham landlord channels not named anywhere; no referral mechanic in product |
| Offer & pricing | 1 | Searched all pages: no management fee, no % figures, no package names. Landlord money screen shows "management fee… on the roadmap" — an unpriced service is a hobby |
| Trust & credibility stack | 2 | Emergency banner + phone number are good instincts; but no company number, no redress scheme badge, no data protection registration, no named team, fictional demo content unlabelled at the sign-up funnel itself |
| Compliance floor (UK lettings) | 1 | **Statutory absence**: letting agents in England MUST belong to a Government-approved redress scheme (The Property Ombudsman / Property Redress Scheme) and show membership on all communications — nowhere in product. Deposit protection scheme claimed in tenant copy ("held by TDS") without any workflow enforcing certificate upload/prescribed-info — legal claim, no enforcement. No privacy notice (GDPR/ICO), no Tenant Fees Act permitted-payments statement, no Right to Rent workflow, CP12/EPC tracked nowhere |
| Onboarding friction | 7 | Best dimension. Public → agent desk lands live; tenant report → numbered case + job in ~5 s; £210 invoice → landlord approval → tenant "sorted — paid" propagated across three portals in one walk. Registration funnel bug found (register pages redirected logged-out visitors to /login) — FIXED same evening, re-verified |
| Launch infrastructure | 2 | Tunnel URL, no backups, no error reporting, no email delivery, login had no rate limit (throttler added same evening, unit-tested), in-memory state behind single stdlib process |
| Sales assets & metrics | 1 | None exist: no price sheet, no pitch, no demo script, no week-1 metric definitions |

**One-sentence commercial lead insight:** *pitch the landlord-side money-approval
loop, because the approval card — evidence table, plain "above your £150 limit,
that's why you're being asked", instant propagation to tenant and trade — was the
single most persuasive screen in the product, and it answers the only question
landlords actually ask: "who touched my property, when, and why did it cost that."*

## Directives (max 15; each: imperative — evidence — acceptance)

**P0 — cannot take a real paying customer without these**

1. `[P0] trust — Join a redress scheme (Property Redress Scheme or TPO) and put the membership badge + name in the public footer and every email template — evidence: searched /, /signin, footer of all pages: zero identity/redress keywords — acceptance: a stranger can name the redress scheme from the landing page footer.`
2. `[P0] trust — Publish real company identity (legal name, trading address, phone that rings, email) on a footer strip across ALL surfaces incl. public bundle — evidence: / and /register/* render no entity information — acceptance: /sitemap-worthy footer contains entity name + address; screenshot review passes.`
3. `[P0] compliance — Add /privacy + /fees public pages (privacy notice, ICO registration number, Tenant Fees Act permitted payments statement, complaints procedure) linked from footer — evidence: absent; search all pages — acceptance: two new pages reachable logged-out, linked from every footer, text reviewed against ICO/TFA checklists.`
4. `[P0] compliance — Until an actual TDS/DPS account workflow exists, the product must not claim deposits are protected; keep honest "ask the office for your certificate" copy or wire a real upload of the prescribed-info document into the tenant docs card — evidence: tenant paperwork asserted TDS fact without enforcement (copy softened same evening; upload still absent) — acceptance: docs card either shows a real uploaded certificate or only conditional language.`
5. `[P0] pricing — Publish the landlord offer: named packages with management %, deposit-free rent-collection mechanics, signing fee £0 (TFA-compliant), one-page /pricing public — evidence: no price anywhere in product or README — acceptance: /pricing page exists, linked from landlord-ad CTA, and the agent can close a sale using only that page + a demo login.`

**P1 — before first ten**

6. `[P1] launch-infra — Move off the cloudflare tunnel to a named domain with TLS, process manager, and nightly stage.json backups (it is the whole database) — evidence: serving URL is a random trycloudflare hostname; single stdlib process; no backups found — acceptance: https://stage.<tld> with cert auto-renew, restart-survival test, backup cron visible.`
7. `[P1] onboarding — Label demo content for real walkthroughs or seed a client-branded sandbox: fictional tenants in a live funnel will confuse actual prospects during demos — evidence: /agent cases reference Daniel Mensah, Priya Shah; public listing says "sample" but landlord registration lands in the same queue — acceptance: a "DEMO SANDBOX" banner on seeded data only, real sign-ups unbannerred.`
8. `[P1] sales-assets — Build the 3-minute landlord demo: fixed story (report → dispatch → your approval card → sorted), scripted clicks, throwaway account — evidence: assessor had to invent the £210-invoice walkthrough on the fly — acceptance: scripted demo URL walkable by a stranger with zero narration prep.`
9. `[P1] launch-infra — Transactional email that delivers: enquiry receipts ("Reference reg-6, we'll call you") and approval requests to landlords — evidence: every flow ends silently inside the portal; no email anywhere — acceptance: public form submit sends a real receipt email within 10 s (verify via test inbox).`
10. `[P1] compliance — CP12/EPC expiry tracker on the agent desk with 60-day warnings (it is the agency's #1 fine risk) — evidence: Properties tab shows title/rent only — acceptance: agent overview gains a compliance tile; seeded fixture cert expiring in 45 days surfaces red.`
11. `[P1] onboarding — Real accounts + invite flow for landlords/tenants (agent creates; user sets own password) — evidence: identities are operator-seeded constants; /api/whoami display_name is the whole privacy boundary — acceptance: agent invites a landlord by email; that landlord sets a password and sees only their properties.`

**P2 — fast-follow**

12. `[P2] trust — Reviews/proof strip on public site once first tenancies sign (Google reviews embed or named testimonials with consent) — evidence: public page has zero social proof — acceptance: testimonial block live with real names + consent records.`
13. `[P2] product — Standing-authority editor for landlords (with audit of limit changes) — evidence: "Change limit" button correctly says "ring the office today" — acceptance: limit editable in /landlord settings, change logged to audit_log, Jev-free.`
14. `[P2] metrics — Define the north-star + kill criterion in README: signed landlords from first-10 push in 30 days (suggest 3; kill/reposition below 1) — evidence: README roadmap lists features, no numbers — acceptance: README gains a Metrics section with both numbers.`
15. `[P2] sales — Birmingham-first content pack (2 neighbourhood pages, landlord guide PDF) — evidence: zero marketing surfaces exist — acceptance: two /guides pages live, share-ready.`

## What's already strong (keep, don't sand off)

- Emergency-safety copy on the tenant flow (banner + phone-first framing) — the
  assessor called it "correct"; that's a liability win most MVPs never think of.
- The approval card with its evidence table — "the best screen in the product".
- Status propagation between all three portals during a live walk.
- Honest manual fallbacks ("ring the office") instead of broken buttons.
- Rate-limited login, server-scoped data, no leaks found: tenant saw 0 foreign
  properties, 0 audit_log, 0 invoices; XSS probes contained.

## Fixes shipped the same evening (by parent session, from this assessment)

1. Registration funnel was login-gated (killed the #1 lead flow) — opened, re-verified logged-out.
2. Deposit-protection claim softened to honest conditional copy.
3. Login brute-force throttle (5/5min/IP, unit-tested: blocks 6th, clears on success).
