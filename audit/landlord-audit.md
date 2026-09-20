# Landlord Audit — Stage portal demo
**Auditor persona:** T. Blackwood, owner of 16 Parkside Mews (£2,400/mo, let to Daniel Mensah) and 5 Holloway Yard (£1,800/mo, vacant). Full-time job; checks portal on the sofa twice a month. Hired an agency precisely so I don't think about boilers.
**Date:** 2026-09-20 · **Method:** live browser at http://127.0.0.1:8901 (session `audit-landlord`), plus source read of `landlord.html`, `tenant.html`, `trades.html`, `agent.html`, `serve.py`, `stage.json`.
**Scores: Usability 4/10 · Workflow 3/10**

---

## Executive summary
The portal asks me to sign off money with the *least* information of any role in the system. The tradesperson sees the invoice amount and the £150 rule; the agent sees triage confidence and routing; I see an amount and my tenant's sentence in quotes. There is no money view whatsoever — no rent ledger, no management fee, no repair spend, no balance owed to me. Decisions (approve or reject) vanish without a trace: no history, no confirmation, no receipt. The £150 standing authority is quoted at me in copy three times but I cannot change it, cannot see what was auto-settled under it, and get no notification of anything. And the header lets me "become" the tenant, the tradesperson or the agent with one click and no login — which also means anyone can become *me* and read my rents and approval queue.

The bones are good — the empty-state copy is the best line on the site, the amber "why you're being bothered" note is genuinely helpful, and it renders cleanly at 390px. But as a paying owner I would not feel respected, informed, or safe here.

---

## Task 1 — The £180 approval (appr-1)
**State found:** already decided. `stage.json`: `"id": "appr-1", "amount_pence": 18000, "status": "approved", "actioned_at": "2026-09-20T19:55:48"`. The Approvals tab showed the empty state: *"Nothing needs your signature. Small works under standing authority are handled by your agent."* There is **no record shown to me that appr-1 ever existed** — I cannot see what I approved, when, or that job-1 is now "paid". The tap-leak case below it still reads `16 Parkside Mews · open`.

**Live reproduction (to audit a real pending card):** I ran the full flow via the site's own APIs — tenant issue (case 498, "Bathroom ceiling is wet and the paint is blistering — water is dripping from the extractor fan.") → trades accept (job assigned to **R. Doyle Gas & Heat**) → invoice **£220.00** → escalation. The card I then saw verbatim:

> **£220.00 — repair approval**
> 16 Parkside Mews · requested 20 Sept
> "Bathroom ceiling is wet and the paint is blistering — water is dripping from the extractor fan."
> *Above the £150 standing authority* — that's why it reached you and not just the agent.
> [Approve] [Reject]

**Could I safely approve? No.**
- **Tradesperson named?** No. `assigned_to: "R. Doyle Gas & Heat"` exists in the job data (`serve.py` stores it) but `landlord.html` never renders it. I don't know who did the work or whether they're Gas Safe / insured.
- **Quote?** No. No quote-before-work, no line items, no invoice number, no way to request a second quote. The "invoice" is a free-text number the tradesperson typed into `/trades` (`<input type="number">` in `trades.html:56`) with no document attached.
- **Photo?** No. Grep across every HTML file: zero occurrences of "photo", "certificate", "quote", "evidence", "receipt", "Gas Safe".
- **Certificate?** No. Nothing for the £180 tap or the £220 ceiling; a gas/boiler job would legally need one and the portal has nowhere to put it.
- **Completion date?** No — only "requested 20 Sept". Was the work even done before I'm asked to pay for it? The job is already `awaiting_approval` (i.e. the tradesperson clicked "Job done") but the card doesn't say that.

**Fake-invoice paranoia — justified.** Anyone can POST `/api/tenant/issue` with `name:"Daniel Mensah"` (I just did, twice) and a maintenance message will auto-dispatch a job; when a tradesperson completes it over £150, a card with the *tenant's own words as the only evidence* appears in my Approve queue. A fraudulent job is indistinguishable from a real one on this card.

**Asymmetry across roles (same job, three views):**
| What each role saw live | Trades (`/trades`) | Agent (`/agent`) | Landlord (`/landlord`) |
|---|---|---|---|
| Invoice amount £220.00 | ✅ "£220.00 · landlord sign-off pending" | ❌ no jobs/approvals view at all | amount only, no invoice ref |
| Tradesperson identity | is them | ❌ | ❌ **not shown** |
| Property full address | ✅ "16 Parkside Mews · Twickenham · TW1" | ✅ | ✅ |
| Triage confidence / routing ("Routed: human decision required", "100% CONFIDENCE") | ❌ | ✅ | ❌ |
| The £150 rule explained | ✅ fineprint | ✅ stat tile "Standing authority £150" | ✅ amber note |
| Payment status of completed work | ✅ "paid" badges | ❌ |  |

The person **paying** gets the least evidence; the agent — whose "standing authority" is supposedly acting on my behalf — can't see jobs or approvals anywhere on their dashboard (`agent.html` has only Overview/Registrations/Cases/Properties). The story doesn't match between roles.

**Decision made:** I **rejected** appr-2 (£220) and **approved** appr-3 (£160.50, boiler job) purely to test the paths — see Task 5.

---

## Task 2 — Standing authority: copy-only control
The £150 limit appears exactly three times, all as static text:
1. `landlord.html` empty state: *"Small works under standing authority are handled by your agent."*
2. `landlord.html` amber note: *"Above the £150 standing authority — that's why it reached you and not just the agent."* (Good copy — it explains *why I'm being bothered*. Keep it.)
3. `trades.html` fineprint: *"Invoices up to £150 are settled automatically under the agent's standing authority. Above it, the landlord approves first."* — the tradesperson is told my limit **more clearly than I am given control over it**.

**What's missing (tested by looking for it everywhere):**
- ❌ No control to change £150. It lives in `stage.json → authority.standing_limit_pence` and no page renders an editor.
- ❌ No view of what happened *under* the limit. Concrete example: job-2, radiator banging, **£45 auto-paid to R. Doyle Gas & Heat** — it appears nowhere on my page. My radiator case still says "open". I paid £45 and the portal never mentions it.
- ❌ No notification settings (email/push "when something is auto-settled" or "when an approval waits >24h"). No "alerts" anything; grep for `notif|alert|threshold|change limit` hits only a JS `alert()` on the trades page.
- ❌ No monthly digest of agent-spent money. For a twice-a-month sofa check, a digest is the *only* realistic control surface, and it doesn't exist.

---

## Task 3 — Money view: absent. Headline finding.
Searched every page (`/`, `/landlord`, `/tenant`, `/trades`, `/agent`, register pages) and grepped all HTML for `fee|ledger|balance|statement|management`:
- **Rent in:** the only money I see is asking-rent per property: "£2400 /mo", "£1800 /mo" on the Properties tab. That's the *let price*, not what's collected.
- **Management fee out:** the word "fee" appears nowhere on the site. The front page promises "LETTINGS & PROPERTY MANAGEMENT" with no pricing.
- **Repairs spend this year:** nothing. £180 + £45 + £160.50 have been charged to my property in one evening and there is no total anywhere.
- **Balance owed to me:** no statement, no "rent collected − fees − repairs = your balance". Zero.
- **Receipts:** none; the "paid" status exists only on the *tradesperson's* page.

As a landlord, the entire financial relationship is invisible except the escalated invoices I'm forced to look at. I cannot reconcile a penny. This is the single biggest gap between "demo of a triage engine" and "portal an owner would sign up to".

---

## Task 4 — Status vocabulary
What my page actually said (verbatim from live render):
- Case badges: `open` on **all five** cases — including the tap leak whose job is already `paid` and the bathroom ceiling I just **rejected**. "open" tells me nothing about whether money moved.
- Triage strips: `SYSTEM ONE · jev` — and on two older cases literally `SYSTEM ONE · ?` (engine field missing → the UI prints a question mark; looks broken, inspires zero confidence).
- Urgency words: the banging radiator (job **already auto-paid £45**) is labelled **"Emergency"**; the active leak with 90% safety is **"Soon"**; my rejected £220 ceiling still screams **"Emergency"** next to an "open" badge. The words are not actionable and actively mislead.
- `SAFETY 93%` — percentage of what? No definition anywhere.
- Move labels: `APPROVE` / `VERIFY` / `your stage` — insider shorthand. "VERIFY" is on a section where I can verify nothing.
- The *same* triage is labelled four different ways across roles: landlord "SYSTEM ONE · jev", tenant "PASSED TO THE RIGHT PERSON · JEV LIVE", trades "DISPATCH · jev", agent "JEV TRIAGE · jev".

**Rewrites for the worst offenders:**
| Now | Should say |
|---|---|
| `SYSTEM ONE · ?` | `Checked by Stage assistant` (never render `?`) |
| badge `open` (paid job) | `Sorted — £180 paid 20 Sept` |
| badge `open` (my rejected job) | `Not approved — agent asked for options` |
| `Emergency URGENCY` (radiator) | `Response: today` / `within 48h` — promise a timeframe, not a feeling |
| `SAFETY 93%` | `Risk to residents: High` |
| `VERIFY` section title | `What's happening — no action needed unless flagged` |
| `your stage` | `My properties` |

---

## Task 5 — Trust probes: what does Reject actually do?
**I clicked Reject** on appr-2 (£220) in the real UI, then followed the thread:
- **Landlord:** card vanished → identical empty state as if nothing had ever happened. No "Rejected — the agent will find another option" confirmation, **no decision history anywhere**, and my VERIFY card for the same case still reads `open` + `Emergency`. From the sofa, Reject looks like it did nothing.
- **Backend:** `serve.py:214-219` sets approval `rejected` and job `rejected`. That's all. No re-dispatch, no agent task, no way for me to record a reason (no note field on the button).
- **Trades (`/trades`):** sees *"£220.00 — declined by landlord"* — filed under the heading **"Completed & settled"**, which is either insult or confusion for an unpaid tradesperson. At least the trade knows.
- **Tenant (`/tenant`):** still shows *"Bathroom ceiling… · with the agent"* — unchanged. `STATUS_LABEL` in `tenant.html:47` contains "not approved — ask your agent" but it maps *case* status, and cases never change status (`handle_landlord_action` touches jobs only). **The tenant is never told.** Daniel will chase a repair I already declined, and the agent is the only one who could tell him — but the agent's dashboard has no approvals view to even know I did it.
- **Approve path (appr-3, £160.50):** clicked Approve → card vanished (again no confirmation/receipt); trades badge flipped to `paid`; my case still `open`. So: approve and reject are visually indistinguishable outcomes for the landlord.

**Verdict:** rejecting "does something" only in the database. The human loop — me → agent → tenant/trades — is broken at three of four hops.

---

## Task 6 — UI / mobile / privacy
- **Mobile (390×844, emulated):** genuinely fine. Cards stack, the jev-strip wraps, Approve/Reject are thumb-sized, nothing overflows. Credit where due.
- **The role tabs:** the landlord header is `Front · Tenant · Trades · Agent` — one click and I'm "signed in as R. Doyle Gas & Heat" or the agent, no auth anywhere (`ME = "T. Blackwood"` is a hardcoded JS constant; `serve.py` has zero authentication). Two consequences: (a) as a demo of "what other roles see" it's clever; (b) as a product it **destroys the privacy story**: any visitor to `/landlord` sees my rents (£2,400/£1,800/mo), my approval amounts, and my tenants' full messages; the agent dashboard shows me *other landlords'* names, rents and cases (S. Okoye's gas-smell report, M. Ferreira's property). If my tenant can click "Landlord" and read my finances, the £150 "standing authority" premise — that someone is guarding my money — is theatre. At minimum the tabs need a "demo mode" banner; in production, real sessions.
- **Broken data in the shared view:** agent Cases list renders *"From: Daniel Mensah (undefined)"* for every tenant issue — `c.email` is undefined for issues and the template doesn't guard it.
- **Empty states:** the approvals empty state is excellent copy; the cases empty state ("No open work in your buildings.") is good. Both are undermined by the fact that *decided* approvals and *paid* jobs also land in these empty states — silence is ambiguous.
- **Timestamps:** approval cards show "requested 20 Sept" but no time; cases show no date at all on my page — I can't tell the 6-minute-old lockout from a week-old noise.

---

## Issue register (severity)
| # | Sev | Area | Issue |
|---|---|---|---|
| 1 | HIGH | workflow | Approval card has no evidence: tradesperson name, invoice ref, photos, certificates, completion date all missing → cannot safely approve; fake invoices indistinguishable (verified live) |
| 2 | HIGH | workflow | No money view: no ledger, fees, repair totals, balance, receipts anywhere (grep-verified across all pages) |
| 3 | HIGH | workflow | Decisions vanish: no approval/rejection history, no confirmation after Approve/Reject (verified live) |
| 4 | HIGH | ui | One-click role switching with hardcoded identities and zero auth → cross-landlord data exposure; "signed in as" is a lie |
| 5 | MED | workflow | Reject doesn't propagate: tenant still "with the agent", landlord case still "open/Emergency"; only trades sees it |
| 6 | MED | workflow | Standing authority is copy-only: no editor, no under-limit feed (£45 radiator invisible to me), no notifications, no digest |
| 7 | MED | ui | Status vocabulary: `SYSTEM ONE · ?`, permanent "open", "Emergency" on a £45-paid radiator, undefined "SAFETY %", four labels for one triage |
| 8 | MED | workflow | Agent dashboard has no jobs/approvals/finance view at all — the role between me and the trades can't see the money either |
| 9 | LOW | ui | "declined by landlord" filed under "Completed & settled"; agent shows "(undefined)" emails; no timestamps on landlord cases |
| 10 | LOW | workflow | No reject-reason field, no request-second-quote action, no way to dispute a paid under-limit job |

## Delights
- The amber line *"Above the £150 standing authority — that's why it reached you and not just the agent"* — explains the interruption, respects my time.
- *"Nothing needs your signature. Small works under standing authority are handled by your agent."* — the best sentence in the product.
- Clean mobile render at 390px; instant re-render after decisions (no reload).
- Properties tab is calm and scannable: rent, tenant, "vacant — being let".
- Trades page shows the £150 rule to the tradesperson — consistent expectation-setting on at least one boundary.

## Missing data / features (wishlist, in priority order)
1. Landlord statement: rent collected, management fee, repairs YTD, balance owed, per-property and portfolio-wide.
2. Evidence pack on approval cards: assigned tradesperson + registration, invoice number/PDF, before/after photos, certificates, completion timestamp.
3. "Decided" history tab (approve/reject log with amounts and outcomes).
4. Standing-authority settings: edit limit, notification channel, monthly auto-settled digest.
5. Case lifecycle statuses that actually change ("Sorted — £180 paid", "Declined — agent re-planning").
6. Rejection with reason → agent task → tenant-visible outcome.
7. Real auth/role scoping (or an honest "demo" watermark on the role tabs).
8. Second-quote request action for over-limit invoices.

## State left behind (demo mutations)
Created and decided during audit: case 498 + job-6 + appr-2 (£220, **rejected**); case 499 + job-7 + appr-3 (£160.50, **approved**). appr-1 was already approved before I started. Server untouched.
