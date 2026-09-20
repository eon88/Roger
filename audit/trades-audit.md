# Tradesperson Audit — Stage Portal Demo
**Persona:** R. Doyle Gas & Heat — one-man plumbing/gas business, fully booked, working from a phone in a van.
**Audited:** Sun 20 Sep 2026, ~20:13–20:20 UTC, live at http://127.0.0.1:8901 (`/trades`, `/landlord`, `/agent`, `/tenant`, `/register/trades`), plus source: `trades.html`, `serve.py`, `dash.css`, `landlord.html`, `agent.html`, `tenant.html`, `stage.json`.
**Scores: Usability 4/10 · Workflow 2/10.**

---

## Task 1 — The open-jobs board & the gas emergency (job-3)

The card, quoted exactly as rendered:

> **I can smell gas in the kitchen since this morning. My toddler plays on…**
> Flat 2, 14 Alder Road · Richmond
> `DISPATCH · jev` `maintenance CATEGORY` `Emergency URGENCY` `98% SAFETY`
> **[Take this job]**

I took the job (I am Gas Safe and 98% safety is what I'm for) — **but here is everything I did not know at the moment of clicking:**

1. **No full description.** The message is hard-truncated at 70 chars (`trades.html:49` `j.message.slice(0,70)`). The cut-off words are "the floor there" — the single most safety-relevant detail (a child at floor level near a possible gas leak). There is no expand, no detail page, anywhere on my board. The in-progress card truncates too, and without even the ellipsis: "My toddler plays on".
2. **No postcode.** Parkside jobs show "Twickenham · TW1"; the gas job shows only "Flat 2, 14 Alder Road · Richmond" — `stage.json` has no postcode field for `alder`. I cannot route this.
3. **No tenant name or phone.** Priya Shah exists in `stage.json` (case 494 `name`) but is never rendered on the trades board. I cannot call ahead, cannot ask "has anyone turned the gas off at the meter?", cannot confirm someone will be home. For a gas emergency the standard instruction is evacuate + call the National Gas emergency line — I have no way to know that was done.
4. **No access instructions.** Gate code? Which entrance for Flat 2? Floor? Is the toddler home alone right now?
5. **No required-trade / certification field.** Nothing says "GAS WORK — Gas Safe engineer required". The job is categorised only as `maintenance`. The system let me take it because my *name* contains "Gas & Heat", not because the platform checks it. See Task 4.
6. **No appointment, date, or expected arrival window.** Emergency = "now"? Who decides? Nothing to accept *as a commitment*.
7. **No cost authority before booking.** The standing-authority fine print only appears *after* I accept (`limitNote()` is inside the in-progress card, `trades.html:58`). I don't know who is paying me or their limit until I'm already committed.
8. **No parking notes, no photos, no agent job notes.**

Accept is one click, no confirmation dialog, no summary of what I'm committing to (`trades.html:68`).

## Task 2 — Completing the job at £60 and what "paid" means

After accepting job-3, the in-progress card showed the fine print at the moment of decision, quoted exactly:

> "Invoices up to £150 are settled automatically under the agent's standing authority. Above it, the landlord approves first."

- 12px, muted grey `#6f675c` on card `#fffdfa` — **measured contrast 3.77:1, fails WCAG AA (4.5:1)**. A van driver in sunlight will not read it, and it appears *after* the accept click, not before.
- Entered `60` in the invoice box, clicked "Job done — submit invoice". **Feedback: none.** No toast, no confirmation, no "invoice sent to X" — the page silently re-renders and the card reappears under "Completed & settled" with a green **`paid`** badge, "Flat 2, 14 Alder Road · Richmond · £60.00".

**Does "paid" mean money in the bank? No.** `serve.py:204–205`: for invoices ≤ limit the server just sets `job["status"] = "paid"` in the same request. There is no payment processor, no bank reference, no settlement date, no `paid_at` timestamp, no payout schedule. It is a promise rendered as a badge.

**Paperwork: none exists.**
- No invoice document/number/PDF; the "invoice" is one integer `invoice_pence` on the job record.
- No VAT anywhere — no gross/net split, no VAT registration field, no "invoice to" entity. A VAT-registered sole trader cannot produce compliant paperwork from this portal.
- No receipt or statement view for the tradesperson; no export.

**Cross-role comparison of the same job (job-3, £60):**
- `/landlord` (hard-coded as T. Blackwood): shows **nothing** — the gas flat belongs to S. Okoye and the page filters by one landlord persona. Even for their own jobs, landlords never see who the tradesperson is.
- `/agent`: **the Agent Dashboard has no jobs or invoices section at all** — only Overview / Registrations / Cases / Properties (`agent.html:136–141`). The choreographer cannot see that job-3 was booked to me, completed, or billed. Worse, **cases never transition**: case 494 (the gas report) still reads `open` on the agent board after the job was paid, and every case card shows "From: Daniel Mensah **(undefined)**" — the email field is missing for tenant-reported issues.
- `/tenant`: status labels exist for the whole lifecycle ("a tradesperson is on it", "sorted — thanks" — `tenant.html:47`) but they map **case** status, which never changes, so Priya Shah still sees "with the agent" for a job I finished. The good idea is wired to the wrong object.
- The landlord approval card (seen live for another job: "£160.50 — repair approval … *Above the £150 standing authority — that's why it reached you and not just the agent*") is genuinely well explained — **the transparency is aimed at the payer, never at the person doing the work.**

## Task 3 — The £180 job stuck in landlord sign-off (job-1) — and a live rejection

Live data moved during the audit (other roles were auditing concurrently):

- **job-1 (£180)**: was awaiting sign-off at task handover; I found it **`paid`** — `appr-1` shows T. Blackwood approved at 19:55:48Z. Even so: the trades view shows only the badge "paid" — **no expected payment date was ever shown while pending, and none exists now that it's "paid".**
- **job-6 (£220, bathroom ceiling, billed under my identity)**: appeared on my board mid-audit as `landlord sign-off pending`, then **flipped to `declined by landlord`** (`appr-2` rejected 20:15:38Z). £220 of work → £0, silently.

What exists for a tradesperson carrying an awaiting-approval invoice:
| Need | Found? |
|---|---|
| Expected payment date / SLA | **Nothing.** Badge only: "landlord sign-off pending" |
| Escalation if landlord never approves | **Nothing.** No timer, no agent-chases, no auto-approve |
| Partial release / advance | **Nothing** |
| Reason for rejection | **Nothing.** `handle_landlord_action` (`serve.py:209–221`) accepts only `{id, action}` — no reason field exists in the API |
| Appeal / re-submit / "did the work anyway" path | **Nothing.** `rejected` is terminal |
| Who to chase | **Nothing.** Landlord name isn't even shown to me |

**Risk carried:** I buy parts and spend labour hours before knowing anyone above the £150 cap has agreed to pay. The agent's standing authority protects small jobs; above it, the tradesperson is the unsecured creditor of a landlord they cannot contact, and a silent "Reject" click wipes the invoice. The operating model says money promises must be real — this is the worst place they aren't.

## Task 4 — Role gating: a legal/safety workflow hole

**Demonstrated live:** as "R. Doyle Gas & Heat" I clicked **Take this job** on job-4, the **front-door lockout** (locksmithery). One click, no warning, no category check — it's now in my "In progress".

- `trades.html:39` hard-codes `ME`; `accept()` (`trades.html:68`) posts any job id with any tradesperson string.
- `serve.py:182–184`: `accept` sets `status="in_progress"` and `assigned_to = data.get("tradesperson", "Unknown")`. **No authentication, no credential check, no category match** — a curl POST with `tradesperson: "Totally A Gas Engineer Ltd"` would book the 98%-safety gas job.
- The trades registration form (`/register/trades`) collects only free text: "Trade, coverage and experience". **No structured trade categories, no Gas Safe register number, no expiry, no verification.** The one Gas Safe mention in the system is a landlord/agent reading a free-text blurb (`stage.json` reg-2).
- Jobs carry no `required_trade` or `certification_required` field; the jev triage has `category: maintenance` only.

**Why this is high severity:** under the Gas Safety (Installation and Use) Regulations 1995, gas work must be done by a Gas Safe registered engineer; a portal that dispatches a "smell gas — toddler on the floor" job to whoever clicks first creates the paper trail of an unlawful booking, and the agent (the choreographer) never even sees the dispatch (Task 2: no jobs view). Per the operating model, law/safety decisions must stay human — the system's job is to *gate and record* credentials, which it doesn't.

## Task 5 — Scheduling & reality: what's missing, prioritised

1. **P0 — Tenant contact + access info** (name, phone, door code, who's home). Without it every job is a guess; for the gas job it's a safety issue.
2. **P0 — Appointment / response window + status ("on my way", "running late", ETA)** — the entire scheduling dimension is absent: no dates anywhere on my board (`created_at` exists in data but is never shown to trades).
3. **P0 — Full job description + photos** — 70-char truncation everywhere, no detail view, no attachments; triage text is the only brief.
4. **P0 — Trade/certification requirement on the job** (see Task 4).
5. **P1 — Payment terms visible before accepting** (who pays, standing authority, my rate agreement, expected settlement date).
6. **P1 — Complete address incl. postcode + parking notes.**
7. **P1 — Agent notes / prior attempts on the case** (is this the third radiator bleed?).
8. **P2 — Un-accept / "can't make it" and job reassignment** — once taken, a job is mine forever; no release button.
9. **P2 — Invoice artefacts**: VAT breakdown, invoice number, PDF, "billed to", paid-on date, statement of accounts.
10. **P2 — Tenant-facing "engineer coming: name + reg + phone"** (GDPR-consented), plus case-status sync so tenants stop seeing "with the agent" after completion.

## Task 6 — UI / field-use review

**Measured in-browser (computed styles + contrast maths), `/trades`:**
- `.fineprint` 12px, **3.77:1 — fails AA** (the most financially important text on the page).
- `.badge` (pending/warn) 11px, **3.80:1 — fails AA**; badge text is the *only* payment-status signal.
- `.jev-strip .metric span` labels **9px with opacity .75** — microtext.
- `.meta` 13px 5.49:1 (passes), `.btn.primary` 13px 6.42:1 (passes), body 15px.
- No dark mode; warm paper palette is low-glare but the serif display font (Fraunces) at 17px for job titles is pretty, not sunlight-legible.

**Mobile 390×844 (CDP emulation):** no horizontal overflow; tabs wrap; header eats 130px (~15% of viewport) before any job appears; buttons are **35px tall — below the 44px touch minimum** for greasy-fingered van use. Usable, but built for a desk.

**The tab bar problem:** every dashboard carries `Front / Tenant / Landlord / Agent` — from my job board I can click into the landlord's approval queue and **approve or reject my own invoices** (`decide()` is an unauthenticated POST, `landlord.html:71`). Fine for a demo; in production it's identity fraud. There is no sign-out, no session, no "you are viewing as".

**Jargon & inconsistency:** section labels "BOOK", "YOUR STAGE", "VERIFY & GET PAID" are theatre metaphors, not trade language. The same triage strip is labelled **"DISPATCH · jev"** (trades), **"SYSTEM ONE · jev"** (landlord), **"JEV TRIAGE · jev"** (agent), "PASSED TO THE RIGHT PERSON" (tenant). The agent view says **"SAFETY RISK 66%"**; mine says **"66% SAFETY"** — which reads as "66% safe" and undersells the danger of a lockout. Seeded jobs show engine `'?'` and mis-triage noise as fact (radiator banging = "Emergency"; drip = 90% safety).

**No feedback loops:** accept/complete produce no confirmation; the only "did it work?" signal is a card silently teleporting between sections.

---

## State I left the demo in (for other auditors)
- job-3 (gas): accepted by me, completed at £60 → `paid`.
- job-4 (lockout): **accepted by me, left `in_progress`** (role-gating evidence).
- job-6 (£220): found `awaiting_approval`, became `declined by landlord` during audit (external action, not mine).
- job-7 (£160.50 boiler): appeared/appr-3 approved during audit (external).
- No server processes touched.

## Delights (what genuinely works)
- One-tap booking with zero friction; board loads fast and mobile layout holds.
- Colour-coded urgency/safety strip is scannable at a glance.
- The standing-authority explanation on the landlord's approval card ("that's why it reached you and not just the agent") is exactly the plain-language transparency the trades side needs too.
- Decimal amounts (£160.50) handled correctly end-to-end.
- Rejection is at least *visible* on my board ("declined by landlord") — no silent disappearance.
- Tenant status vocabulary ("a tradesperson is on it") shows the right instinct — it's just wired to case status that never updates.

## Verdict
The portal turns a tenant report into a bookable job faster than any spreadsheet — but it books work **to anyone, blind, with no scheduling, no contact, no credentials, and a "paid" badge that means nothing until a human with an invisible button says so.** For a working gas engineer it is a demo toy: I'd take one emergency off it (because it was gas and it was my name on the board) and I'd never take a >£150 job on it at all.
