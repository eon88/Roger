# Agent Audit — Stage Portal (/agent)

**Auditor persona:** the solo estate agent — one person, ~30 properties, several landlords (T. Blackwood, S. Okoye, M. Ferreira), tenants reporting daily. Phone-first, terrified of missing a gas-safety deadline or letting a landlord down.
**Date:** 2026-09-20 (evening). **Build audited:** http://127.0.0.1:8901 (serve.py + agent.html, live stage.json).
**Method:** drove the real browser (session `audit-agent`) through all four tabs, submitted a trades registration through the public form, approved it, inspected every case card's action affordances via DOM, emulated a 390–547px phone viewport, simulated a dead API, and probed HTML-injection safety. Every complaint below cites what I actually clicked or read.

**Scores: Usability 3/10 · Workflow 2/10**

---

## 1. Registrations — approving a gas tradesman is a leap of faith

### What the form actually captures
I went to `/register/trades` and inspected the live form. Fields: **Name, Email, "Trade, coverage and experience" (one 3000-char free-text box), a honeypot "Website", and a consent checkbox.** That's it.

To approve a gas engineer I need, at minimum:
- **Gas Safe Register number** (9 digits, verifiable at gassaferegister.co.uk — legally required for gas work),
- **Public liability insurance** amount + expiry date,
- **References** (who else uses them),
- **Trade/qualification categories** (CP12 gas safety certs vs boiler repair vs plumbing),
- **Coverage area and response time** for emergencies.

None of this has a field. I wrote "Gas Safe registered engineer, number 555 123 45 … public liability insurance £2m, references from two local letting agencies" into a free-text box, and the agent card renders it as one grey blob: `Gas Safe 999 888 77, covers TW1, CP12 engineer, insured.` There is **no structured field, no verification link, no checklist, no expiry tracking**. Approving a gas tradesman on this evidence is exactly the kind of thing that ends an inquiry after a carbon-monoxide incident.

### The form is also broken end-to-end
My first submission attempt **failed in the UI**: the page displayed a raw parse error in red text:

> `Unexpected token '<', "<!DOCTYPE "... is not valid JSON`

I hooked `window.fetch` and re-submitted: the cloned front page POSTs to **`/api/public`**, which the dev server only serves as GET — it returns a 404 HTML page, hence the parse error. The real endpoint `POST /register/trades` works fine (my curl registration `reg-3` landed instantly). **A real tradesperson cannot register through the public site at all.** The agent never even sees the pending item.

### Approve feedback and audit trail
With `reg-3` pending, I clicked **Approve** on the agent card. Observed:
- **No toast, no confirmation, no undo.** I queried `.toast,[role=alert],[role=status]` immediately after the click: `[]`. The card just vanishes on re-render.
- **No history.** The Registrations tab renders only `status === 'pending'`. After approving, the string "Curl Test Gas" appears nowhere in the DOM and the word "approved" appears nowhere. If I approve the wrong one, or need to prove to a landlord *when* and *why* I vetted a tradesman, the UI cannot tell me — `actioned_at` exists in stage.json but is never displayed.
- The **empty state** ("No pending registrations") renders a broken icon — the inline SVG duplicates its magnifier path twice, so it draws as two overlapping magnifying glasses.
- The honeypot `website` field, when filled by a bot, would render on my card as `Website: <a href>` — presenting spam-bait as a business website.

**Fixes:**
1. Fix the form's submit URL to `POST /register/trades` (or add the POST route server-side); show a friendly success state, not a JSON parse error.
2. Add structured fields: **Gas Safe number (validated 9-digit, with a deep-link to the Gas Safe register lookup)**, insurance provider/amount/expiry, trade checkboxes (gas / electric / plumbing / …), references (2 name+contact rows), typical response time.
3. Approve/Reject → confirmation sheet ("Approve Kowalski Gas Services? They will be eligible for gas work at your properties") + toast + **undo for 10s**.
4. Add a "Decided" sub-list (approved/rejected with date + who decided) — audit trail, not just a queue.
5. Only show `website` if it's not the honeypot; escape all free-text.

---

## 2. Cases — "human decision required", but the human can do nothing

Case **490** ("The boiler has stopped working and we have a newborn baby — is this urgent?", triaged `Emergency · URGENCY 2 · 90% SAFETY RISK · Routed: human decision required`). I enumerated every button, link and input on every case card via DOM:

```json
{ "title": "Case #490 — enquiry", "buttons": ["Close"], "links": [], "inputs": 0 }
```

**One button. Close.** That is the entire decision space. As the agent, the things I need and *cannot* do:

| Need | Exists? |
|---|---|
| Contact the tenant (call/email/reply) | ❌ No phone/email action. Worse: every tenant-reported case renders **`From: Daniel Mensah (undefined)`** — the issue form never collects email and the template prints raw `undefined`. Case 490 shows a placeholder `alice@example.com` for a tenant named "Alice Tenant" who doesn't exist in the system. |
| Dispatch/assign a tradesperson | ❌ No "Assign trade" button anywhere on /agent. Dispatching exists (jobs auto-create) but is invisible and uncontrollable from here. |
| Note a decision ("called tenant, engineer booked for 9am") | ❌ No notes field, no activity log on the case. |
| Escalate / flag / mark urgent | ❌ No flags. |
| See the property | ❌ Cards show no address. Case 490's `property_id: "p-1"` matches **no property in the database**. With 30 properties I'd have to open the tenant's message and guess which house it is. |
| See if a job already exists for this case | ❌ (see §3) |
| Reopen a closed case | ❌ Closed cases vanish from every view; only `close` exists, no `reopen`. |

I tested **Close** on the trivial case 495 (the repaint question): same pattern as Approve — **no toast, no confirmation, no undo, no closed list**; the card silently disappears and "open cases" decrements. Closing a newborn-boiler emergency with zero record of *why* is precisely the failure mode this portal is supposed to prevent. (I restored 495 to `open` afterwards; data intact.)

**Fixes:**
1. Per-case action bar: **Call tenant · Reply · Assign trade → · Add note · Flag safety**. Even "Assign trade" hitting the existing `/api/job-action` accept path would unlock the workflow.
2. Show **property address + landlord** on the card; validate `property_id` at intake (reject/flag `p-1`).
3. Collect tenant email (or phone) in `/api/tenant/issue`; render `undefined` never — fall back to "no contact given, chase via portal".
4. Close must ask "Why are you closing this?" (resolved / duplicate / no access / not our property) and write it to an audit trail; add a "Closed" filter with reopen.
5. Sort by urgency+safety, not arrival — right now the **gas-leak case 494 sits mid-list between a paint question and a lockout**, all styled identically.

---

## 3. Tracing case 492's lifecycle — impossible from the agent's seat

The intended thread: **492 (tap leak, "cabinet going soft") → job-1 auto-dispatched → R. Doyle completes with £180 invoice → above £150 standing authority → approval appr-1 to landlord T. Blackwood → approved 19:55:48 → job paid.** All of it is real in stage.json.

On `/agent`, I searched the live DOM for `job-1`, `job`, `invoice`, `approv`, `paid`, `awaiting`: **every check returned false.** The Cases tab still shows "Case #492 — open" with only a Close button — no indication work was dispatched, done, invoiced, escalated, approved and paid. Case 493 (job-2, £45 auto-settled under authority) looks *identical* to 492.

Where the other halves live:
- **Jobs** render only on `/trades` — hardcoded identity "R. Doyle Gas & Heat".
- **Approvals** render only on `/landlord` — hardcoded "T. Blackwood".
- **Tenant thread** only on `/tenant` — hardcoded "Daniel Mensah", and it matches cases by **name string** (`c.name===ME`), so "Alice Tenant"'s case 490 is invisible to Daniel.

So to follow one case I must **visit three other actors' dashboards wearing their hardcoded identities** (there's no way to be "me, the agent, looking at everyone"), or read raw `/api/stage` JSON. The tenant page even *advertises* the model — "Everything here moves through one case book — your reports, the agent's follow-up, the landlord's approvals" — but the agent, the choreographer of that book, **has no copy of it**.

Contradiction spotted: case 492's strip says **"Routed: human decision required"** (safety 0.9), yet the backend auto-dispatched job-1 anyway. The routing note and the automation disagree, so I can't trust either.

**Fixes:**
1. A **case thread view**: one card per case with an event timeline (REPORT → triage → DISPATCH job-1 → INVOICE £180 → ESCALATE (over £150) → APPROVE landlord → PAID), fed by joining `cases`/`jobs`/`approvals` on `case_id`/`job_id` — the data already supports it.
2. Status chip on the case card: `job-1 · paid £180` / `job-3 · awaiting a tradesperson`.
3. Align the router note with reality: if maintenance auto-dispatches, say "Auto-dispatched to trade network — you approved nothing yet".

---

## 4. Overview — four numbers do not make a working day

The entire Overview tab is:

```
PENDING REGISTRATIONS 0 | OPEN CASES 9 | PROPERTIES 4 | STANDING AUTHORITY £150
```

For planning my week this is nearly worthless:
- **"Open cases 9" doesn't tell me one of them is a gas leak** (494, safety 98%) and one is a paint question (495). No urgency/safety breakdown, no red count.
- **No jobs KPIs**: unassigned jobs (job-3 gas-leak job and job-4 lockout job are literally `open` with `assigned_to: null` — nobody has taken the gas leak!), awaiting-landlord-approval count, money settled this week.
- **No deadlines at all** — the thing I'm most terrified of. No CP12 gas safety certificate expiries, EPC expiry, deposit protection deadlines, contract renewals. The Properties tab has none either (just photo, beds, rent, landlord, tenant).
- **No rent collection view, no correspondence log** (every reply happens off-portal; nothing records that I ever contacted anyone).
- **"Standing authority £150" is a config value presented as a KPI** — it changes ~never, and nothing explains what it authorises or whose money.
- Stats aren't clickable — "Open cases 9" doesn't take me to the filtered list.
- **No freshness**: I hooked `fetch` and idled 6s — zero re-fetches. If a tenant reports a gas leak while my dashboard is open, I will never see it until I manually reload. No badge, no sound, no push. For a phone-first solo operator this is the killer.

**Fixes:**
1. Replace with a triaged action strip: **"2 emergencies · 3 need you today · 1 waiting on landlord · 2 jobs unassigned · £225 settled this week"** — each clickable into a filtered Cases view.
2. Add a **Compliance** stat: "CP12s due in 30 days: 3" with a per-property expiry table (even seeded fake dates would demo the point).
3. Poll `/api/stage` every ~15s (or SSE) + `document.title` badge + Notification API ping for safety-flagged items.
4. Rename the authority tile: "Auto-settle limit: £150 per invoice (invoices above it go to your landlord)" — or move it into a Settings panel.

---

## 5. UI scan — jargon, mobile, errors, security

**Jargon a human wouldn't get (all seen verbatim on /agent):**
- `STANDING AUTHORITY £150` — no explanation anywhere on the agent page (ironically, the *landlord* page explains it well: "Above the £150 standing authority — that's why it reached you and not just the agent").
- `JEV TRIAGE · jev` and `JEV TRIAGE · stub` — engine internals leaked as a brand. "stub" means the AI call failed and a keyword matcher answered — but it's styled identically to the real engine, so I can't tell which triage to trust. Case 493 ("radiator banging") was stubbed to **"Emergency"** (keyword "radiator/heating") and looks as urgent as the real jev-scored gas leak.
- `SAFETY RISK 66%` / `93%` — these are noul yes-probabilities ("is there plausible risk"), but a human reads "66% safety risk" as *severity*. Lockout case 496 showing "66%" invites "so it's only two-thirds dangerous?".
- `CONFIDENCE 100%` — invites over-trust; nothing says what it's confidence *of*.
- `Routed: auto-booking permitted` — permitted for whom? The agent can't act on it (no booking button).
- `SYSTEM ONE` tag on the landlord page — model architecture as UI copy.

**Mobile (emulated 390–547px, screenshots taken):**
- Header/nav CSS has no `flex-wrap` (`.header{display:flex;justify-content:space-between}`, `.nav{display:flex}`) → **the Cases and Properties tabs are clipped off the right edge** at phone widths; the primary tabs of my job are unreachable without horizontal scrolling. agent.html has **zero `@media` queries** (grep: only `max-width:1200px` on the shell).
- Stats cards stack acceptably; jev strips wrap into a tall 3-row block (~150px per case) — usable but bloated; Close buttons measure 73×42px (passable).
- No pull-to-refresh hint; combined with no polling, phone use = stale data.

**Error/empty states:**
- I simulated a dead API (`fetch` → reject) and reloaded: **the page renders header + nav and a permanently blank body. No error, no retry button, no "stale data" banner.** On bad signal I can't distinguish "nothing to do" from "the portal is down" — dangerous for emergencies.
- `(undefined)` emails on every tenant case (see §2).
- Broken duplicated-path SVG in the registrations empty state.
- `api()` throws are unhandled (`load()` has no try/catch) — any 500 silently freezes the last render.

**Security (verified, not theoretical):** registration `details` and case `message` are interpolated into `innerHTML` unescaped. I POSTed a probe registration containing `<img src=x onerror="window.__xss=1">`; on `/agent` the **script executed** (`window.__xss === 1`, bold tag rendered). Anyone who can submit a registration or a tenant issue can run arbitrary JS in the agent's dashboard — including calling `/api/registration-action` or exfiltrating the whole stage.json (every landlord, tenant, email). (Probe `reg-4` removed from stage.json after the test.)

**No route to the agent at all:** "Sign in" → `/signin` just re-renders the public lettings page. There is no login, no role selector, no link to `/agent` anywhere in the UI — the agent must know the URL by heart.

---

## Priorities (if only five things get fixed)

1. **P0 — XSS / innerHTML injection** in registrations and cases (escape all user text).
2. **P0 — Public registration + enquiry forms are broken** (`POST /api/public` 404 → raw JSON error shown to the applicant).
3. **P1 — Case thread visibility on /agent** (jobs/approvals joined to cases; status chips; per-case timeline) — without it the agent can't choreograph anything.
4. **P1 — Real case actions** (contact, assign trade, note, justified close) — "Close" is not a workflow.
5. **P1 — Mobile nav wrap + live refresh + emergency-first Overview** — the phone-first solo operator currently can't see the Cases tab or a new gas leak at all.

## What I genuinely liked
- The triage strip's **colour language** (red hot / amber warm) reads instantly — right instinct, wrong labels.
- **"no rush — reply when convenient"** (case 495) is the best line of copy in the product.
- The landlord page's standing-authority fine print is exactly the explanation the agent dashboard lacks — lift it across.
- Auto-dispatch of a job from a maintenance REPORT is the right choreography; it just happens invisibly to the agent.
- Clean, calm visual design; en-GB timestamps with day/month/hour:minute are actually useful.
- The data model already supports the full thread (case_id → job → approvals) — the fix is a view, not a rewrite.
