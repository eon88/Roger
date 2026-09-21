# Workflow design — TENANT dashboard ("My Home")

**Persona:** stressed working parent on a phone (Daniel Mensah, 16 Parkside Mews). One-handed, zero jargon tolerance. Needs, in order: *was I heard? → am I safe? → who's coming and when? → is it actually done? → how do I reach a human? → can I prove this later?*
**Reality base:** `stage-clone/serve.py` v2 (756 lines), `tenant.html` (152 lines), `stage.json` @ 2026-09-21, `audit/tenant-audit.md`, `audit/CONSOLIDATED-AUDIT.md`. Sandbox treated read-only; nothing in it was changed.
**Design rule inherited:** extend the state machine, never fork it. Tenant moves act on the **case**, never the job (job actions are closed to tenant by `ROLE_API`, serve.py:99 — keep it).

## Day in the life
They cook dinner with a phone propped nearby; a drip becomes a 10-second report, then nothing.
Ten minutes later they refresh: did anyone hear me? A name and a promise beat any apology.
At 10pm the lock breaks: they need 999/0800 numbers and a human line *before* the form, not after.
If a van is coming, they need who, when, and a safe place to leave the gate code — not a voicemail dance.
Two days of a silent card turns trust into blame; so every silence gets a visible countdown and a chase button.

## Objects & states today (from code)
### Case (type `issue`) — the tenant's spine
Statuses the backend writes (serve.py): `new, reported, dispatched, quoted, in_progress, awaiting_approval, resolved, declined, closed`. `sync_case` (serve.py:296) now propagates job events: accept→`in_progress`, submit_quote→`quoted`, decline_quote→`dispatched`, complete→`awaiting_approval`/`resolved`, landlord approve→`resolved`, reject→`declined` (+ hidden `agent_task` case). `closed` is never auto-overwritten. Tenant-facing badge vocabulary already exists in `tenant.html:64-74` (`STATUS_LABEL`) — **gap: `quoted` has no label**, so the raw machine word leaks.

### Job (tenant receives scoped copy — every field except `email`)
`open → assigned → (quote_requested → quoted) → in_progress → paid | awaiting_approval → paid | rejected`; `pending_verification` is an agent sub-loop. Tenant has **zero job-action rights** by `ROLE_API` — correct; all tenant moves in this doc are case moves.

### Thread (`case.thread`)
Messages `{author, role, text, to[], at}`; tenant's scoped view keeps msgs with `"tenant" in to` **or** authored by tenant (serve.py:218). `POST /api/case-action` with `reply|inform` is open to tenant (serve.py:101). **The backend already talks to tenants** (accept/assign/quote/complete/landlord messages all include `"tenant"` in `to`) — and `tenant.html` never renders `c.thread`. Invisible replies are the #1 fix, zero backend cost.

### Objects that do NOT exist but this design needs
`appointment` (who/when/access), case-level SLA clock (`first_reply_by`, `bumped_at`), `rating`, `documents`, attachments, `tenant_confirmed_at`, `away_until`. All tagged NEEDS below.

### Leaks & trust bugs found in the scoped payload / role guards
- `authority` (£150 standing limit) is included in the tenant's `/api/stage` (serve.py:220) — internal rule, remove (audit T5 lineage).
- `/api/case-action` guards are **missing inside handlers**: a tenant can POST `close` (no role check, serve.py:719) and `add_tradesperson` (709) — the ROLE_API allows all four roles to the endpoint; branch-level guards don't exist.
- `handle_tenant_issue` trusts `body.name` (serve.py:453) — a signed-in tenant can file into *another* tenant's list (audit T6 persists).
- `close` audit hardcodes `actor:"agent"` (727); `reopen` posts "Case reopened **by the agency**." (730) whoever clicks. Reopen also resets to `new` and leaves the paid job untouched → broken revisit loop.
- `/api/job-action` actor falls back to `body.tradesperson` when unauthenticated (503) — legacy; tenant never touches it.

### What the tenant UI has today (complete list of buttons)
One: **"Send report"** (`tenant.html:36`). Plus a real safety banner with 0800 111 999 + office phone (16), promise strips (118-120), "Being handled by X" line (104), docs toast stubs (111), 20s polling (149). That's the whole dashboard — the static-dashboard complaint, quantified.

## Action matrix — the tenant's 18 moves
### Move catalog (18 designed; frequency-ordered — top of card first)

| # | Move | Status today | Object acted on |
|---|------|--------------|-----------------|
| M1 | Report a problem | EXISTS (`/api/tenant/issue`) | case |
| M2 | See progress over time (timeline + countdown) | PARTIAL (status sync exists, no thread render) | case |
| M3 | Ask a question inside the case | BACKEND EXISTS (`case-action reply`), NO UI | thread |
| M4 | Chase an ageing report ("still waiting") | NEEDS | case |
| M5 | "It's worse now" — escalate to urgent | NEEDS | case |
| M6 | Leave access info / gate code | NEEDS | appointment |
| M7 | Confirm or refuse a proposed visit slot | NEEDS | appointment |
| M8 | "Nobody came" — report a missed visit | NEEDS | appointment |
| M9 | "Still not right" — not-fixed reopen loop | NEEDS (`reopen` exists, broken for tenant) | case + new job |
| M10 | "All fixed" — confirm done | NEEDS | case |
| M11 | Rate the fix (one tap + optional line) | NEEDS | case |
| M12 | Request a different tradesperson | TEMPLATE on M3 + NEEDS flag | case |
| M13 | Withdraw a report ("sorted itself") | NEEDS (tenant-close unguarded + misattributed) | case |
| M14 | Reopen a closed case (≤14 days) | PARTIAL (`reopen` exists, wrong author + state) | case |
| M15 | Pause: away dates / no-come-today window | NEEDS | case + appointment |
| M16 | See money & proof trail (invoice, dates, refs) | DATA EXISTS (jobs scoped), NOT RENDERED | job (read) |
| M17 | Reach a human fast | EXISTS (banner + footer tel/email) | — |
| M18 | Open documents (tenancy, deposit cert) | STUB TOASTS; object missing | document |

### Matrix — case status × tenant move (✓ allowed · ✗ DEAD END today · — absent by policy)

| Tenant-visible state (badge copy) | M2 | M3 | M4 chase | M5 escalate | M6 access | M7 slot | M8 missed | M9 not-fixed | M10 fixed | M11 rate | M13 withdraw | M14 reopen | M15 pause | M16 money |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Reported** — "the agent has it" (new/reported, non-maintenance) | ✓ | ✓ | ✓ after clock breaches | ✓ | — | — | — | — | — | — | ✓ | — | ✓ away-dates | — |
| **Queued** — dispatched/quoted, `assigned_to:null` — say honestly: "a person is being assigned — we'll show their name here" | ✓ | ✓ | ✓ after clock | ✓ | prep ✓ | — | — | — | — | — | ✓ | — | ✓ | ✓ (quote amount once `quoted`) |
| **Assigned** — "{name} is on it" | ✓ | ✓ | ✓ after clock | ✓ | ✓ | ✓ if proposed | — | — | — | — | ✗ (visit already arranged; use M7/M15) | — | ✓ | ✓ |
| **On the job** — in_progress | ✓ | ✓ | — (visit arranged; M8 replaces chase) | ✓ | ✓ | ✓ | ✓ | — | — | — | — | — | ✓ window/away | ✓ |
| **Signed off** — awaiting_approval | ✓ | ✓ | — | — | — | — | — | — | ✓ (early confirm sets `tenant_confirmed_at`) | — | — | — | ✓ | ✓ amount + "landlord usually replies in 2 working days" |
| **Done** — resolved | ✓ | ✓ | — | — | — | — | — | ✓ primary | ✓ primary | ✓ after M10 | — | — | ✓ | ✓ final |
| **Being rearranged** — declined | ✓ | ✓ | ✓ after clock | ✓ | — | — | — | — | — | — | ✓ | — | ✓ | ✗ (reason visible, no move — today's dead end; fix = agent names next step + date, template A8) |
| **Closed** | read-only timeline | ✓ | — | — | — | — | — | ✓ within 14 days (→M9) | — | ✓ if unanswered prompt persists | — | ✓ | — | ✓ forever (proof) |

Every state, any time: M1 (a *new* problem), M17 (phone), M3. Safety overlay in every state: emergency strip with 0800 111 999 / 999 inside the case sheet when `triage.urgency>=2`.

### Specs for the NEW moves (pre → post → side effects; M1/M2/M3/M16/M17 are render/data deltas in NEEDS)

**M4 CHASE.** Pre: case not terminal, `now > first_reply_by` (or `now - submitted_at > SLA`; SLA from urgency table in Handoffs). Post: `case.bumped_at=now`, agent queue sorts bumped first. Effects: posts thread msg (B1 template) + agent-visibility strip; ack to tenant = A-C2. One bump per clock breach; second breach shows the phone line louder, not a sadder button.
**M5 ESCALATE.** Pre: not closed; tenant taps "This is dangerous today" (+ one line). Post: `triage.urgency=2`, `tenant_escalated=true`, `first_reply_by=now+4h`. Effects: template A-X1 posted; audit `case_escalated` actor=tenant. (Today a tenant must file a duplicate report — the audit saw exactly that.)
**M6 ACCESS NOTE.** Pre: case has appointment proposed/confirmed. Post: `appointment.access_note` written, masked (`••••`), shown until `visit_date+1d` then purged. Effects: appears in trades' scoped view; never in landlord's.
**M7 SLOT.** Pre: appointment status `proposed`. Actions: "That works" → `confirmed` (A-A4 ack); "Different time" → `declined` + free-text box → agent/trades re-propose. Effects: thread posts both ways.
**M8 MISSED VISIT.** Pre: appointment `confirmed`, `now > visit_end`, nobody tapped "done". Post: status `missed`. Effects: template A-M1; agent rebook task; counts against the trades profile (audit log only).
**M9 NOT FIXED (the reopen loop).** Pre: case `resolved`, or `closed` ≤14 days. Tenant taps "Still not right" + one line. Post: case → `dispatched` with new label "another visit needed"; a **new job** `revisit_of=<old job id>`, `status:open`, copied message+triage; old job's history stays intact (evidence). Effects: template A-N1; audit `tenant_reopen` actor=tenant name. This extends, not forks, the machine: `dispatched` already exists.
**M10 CONFIRM FIXED.** Pre: case `resolved` (or `awaiting_approval`). Post: `tenant_confirmed_at=now`. Effects: A-F1; agent may now close with reason knowing the tenant agreed (audit note 494 proves agents want this: "tenant confirmed fixed").
**M11 RATE.** Pre: `tenant_confirmed_at` set, within 30 days. Post: `case.rating={score:1..3, note, at}`. Effects: visible to agent; never on landlord approval cards (money and satisfaction stay separate).
**M12 DIFFERENT PERSON.** Via M3 with quick-template B-D1; sets `case.swap_requested=true` so it's a queue state, not just prose.
**M13 WITHDRAW.** Pre: case before `in_progress`. Post: `closed`, `closed_reason="withdrawn by tenant"`, audit actor=tenant (fix the hardcoded "agent" first). Effects: A-W1.
**M14 REOPEN-CLOSED.** Backend primitive exists but: keep `reopen` agent-only for admin; tenant path = M9 (≤14 days). When tenant-authored, message must read "Case reopened by Daniel (you said it's still not right)" — never "by the agency".
**M15 PAUSE.** Pre: any non-safety case (`tenant_escalated`/`urgency>=2` CANNOT be paused — justified absence: gas, damp, locks and electrics stay live). Post: `case.away_until=ISO`. Effects: appointment proposal engine skips the window; strip shows "resting until {date} — emergencies always come".
**M16 MONEY/PROOF.** Render-only: jobs in tenant scope already carry `invoice_pence`, `completed_at`, `paid_at`. Card line: "Fixed {date} · cost £{x} · paid {date} · ref #case/{job}". No approval object is needed; the amount is enough proof for a tenant.

## Dead ends today (the pain list, quoted)
Quoted from the live surfaces (post-v2 code; audit items already fixed — real phone banner, session auth, scoped API, status sync — are NOT re-listed):

1. **The portal shouts into a void.** `accept` posts "...will get in touch to arrange access" `to=("tenant",)` (serve.py:511), `assign`, `submit_quote`, `complete`, landlord decisions all address `"tenant"` — and `tenant.html` **never renders `c.thread`**. There is no inbox. (Grep: `thread` appears 0 times in tenant.html's render code.)
2. **One button, ever.** "Send report" is the only control; after the report lands, the tenant's entire vocabulary is re-typing a *new* report. Every cell marked ✗ in the matrix is the product shrugging.
3. **`quoted` leaks as a raw badge.** `STATUS_LABEL` (tenant.html:64) has no `quoted` key → the card shows the machine word `{quoted}`-style fallback.
4. **declined is a black hole.** Badge: "the landlord declined that quote — your agent will come back to you" (71) — no date, no name, and the `agent_task` case that actually got created (serve.py:676) is invisible to the tenant.
5. **reopen resets to `new` and strands the paid job** (serve.py:728-731) — a first-fix-that-failed produces a status-lying case and no revisit job. Message says "by the agency" whoever clicks.
6. **Tenant can already break the record:** `close` and `add_tradesperson` are reachable via `/api/case-action` with no branch-level role guard, and `close`'s audit misattributes to "agent" (727). `body.name` in `/api/tenant/issue` (453) lets a tenant file into another tenant's book.
7. **No access primitive at all:** no name+phone of the visitor, no window, no gate-code field. "will get in touch to arrange access" is the whole feature.
8. **Docs are toasts.** "being digitised", "once document delivery lands" (tenant.html:111) — and the £180/£45 invoice data the tenant needs as proof is sitting right there in their scoped jobs, unrendered.
9. **"Expect contact within 4 hours" (tenant.html:118) is a promise the backend cannot keep or check** — no clock, no breach indicator, no enforcement; a 9-day-old emergency looks pixel-identical to a 9-minute-old one.
10. **No undo of anything tenant-side, because nothing tenant-side exists** beyond sending. Withdrawals, corrections, "wrong flat" reports currently require the phone.

## Handoffs & SLAs — what the UI PROMISES vs what the backend enforces
### Where work enters and leaves the tenant

| # | Handoff | Artifact crossing | Suggested SLA | Chase path when breached |
|---|---------|-------------------|---------------|--------------------------|
| H1 | tenant → agent (report) | case + auto-job (maintenance) | **emergency ≤4h** first human reply; soon ≤1 working day; no-rush ≤3 working days | countdown on card hits zero → M4 button appears; bump sorts case to top of agent desk |
| H2 | tenant → agent (not-fixed) | reopen + `revisit_of` job | callback ≤4h; revisit ≤2 working days | M4 again; second breach surfaces phone strip |
| H3 | agent → trades (assign/accept) | job + "who's coming" | trades contacts tenant ≤2h (emergency) / next working day; visit proposed ≤1 working day | agent sees `assigned` with no appointment >1 day |
| H4 | trades → tenant (appointment) | proposed slot | tenant answers ≤1 working day, else auto re-propose | card glows "they're waiting on you" |
| H5 | trades quote → agency | quote in thread | price decision ≤2 working days | "Waiting on the agency to approve." already posts (562) — add countdown |
| H6 | invoice → landlord | approval | ≤2 working days | tenant strip says who's holding it (A-A5), not why |
| H7 | done → tenant confirm | M10/M11 prompt | prompt persists until answered; **auto-close at 14 days, rating N/A** | home's "waiting on you" bucket |
| H8 | chase bump → agent | `bumped_at` | reply ≤4h from bump | phone |

### Promised vs enforceable, today (verbatim sources)

| UI promise (tenant.html) | Backend enforcement |
|---|---|
| "Expect contact within 4 hours." (:118, urgency≥2) | **None.** No timer, no `first_reply_by`, no breach UI, no agent notification. |
| "usually sorted within a few days" (:119) | None. |
| "usually within a week" (:120) | None. |
| "we will reply within one working day" (email, :55) | None. |
| "Mon–Sat 8am–8pm, and a person will answer" (:54) | Demo phone; no rota object. |

**Rule for this design:** a promise with no clock is deleted or given a clock in the same pass. `first_reply_by = submitted_at + SLA(urgency)` is written at case creation (one field), and every tenant strip renders either a countdown ("your agent owes you an update by Thu 5pm") or a breach state ("this is late — we've flagged it; chase?"). Until the field exists (NEEDS-4), chase is honestly framed as "ask what's happening", not "enforce".

### Handoff hygiene inherited from the machine (keep)
- Rejection never dies: landlord reject spawns `agent_task` (676) — the tenant version gets *words*, not silence (A-A7).
- Every state change posts a thread message + audit entry; the tenant timeline is a *read* of what already exists.

## Undo / reassign / dispute / pause
| Move | How the tenant does it | How the tenant *un*does it | Limits |
|---|---|---|---|
| Report (M1) | form | Withdraw (M13) before a visit is arranged; after, a thread note "we've double-reported" + agent dedupes (case 498 closed as "Duplicate" proves the pattern) | no edit of the original text — the thread is evidence; corrections are appended, never overwritten (policy) |
| Ask (M3) | reply box | add a correction message; no deletion (audit trail doctrine, README rule 5) | — |
| Chase (M4) | button | nothing to undo; a bump is cleared by any agent reply | max 1 bump per clock breach |
| Escalate (M5) | button + line | tenant can de-escalate in thread ("actually it's fine now") — agent-only flip of `urgency` back; tenant never lowers a safety flag silently (law/safety stays human) | one-way up |
| Slot confirm (M7) | button | "Different time" available until the window starts; after, M8 missed-visit | — |
| Not fixed (M9) | button + detail | tap M10 again after the revisit; each failed fix adds a job, the count itself is the escalation | ≤4 revisits, then agent must call |
| Confirm fixed (M10) | button | M9 within 14 days — the undo IS the reopen loop | 14 days, then new report referencing the old |
| Withdraw (M13) | button | reopen via M14/M9 path; agent re-opens anything | before `in_progress` only |
| Reassign | **agent's move, not tenant's** — by design (pool, credentials, £). Tenant right: request a different person (M12/B-D1), honoured no-questions, sets `swap_requested` | swap can be reversed by agent | safety-flagged jobs: agent decides |
| Dispute price | not a tenant veto — money is landlord's decision (Operating Model). Tenant *facts* ("not fixed", "damage got worse while waiting") travel via M9/M5; UI deliberately has no "complain about £" button that messages the landlord directly, even though `to=["landlord"]` is technically open (702) | — | policy over capability |
| Pause (M15) | away dates / "not today" on a proposed slot | remove `away_until` any time | **emergency/safety jobs cannot be paused by the tenant** — one-line justification: gas, damp spreading, no heat, no lock are never optional |

## Message templates (tenant-facing policy: fact → next step → a button)
**Policy for tenant-facing text:** one plain sentence of fact, one of what happens next, and a button if the tenant can act. No engine names, no percentages, no uppercase tags, no "system" voice that could be a bot. These strings are the `post_msg` payloads to implement.

### Inbound (agency → tenant) — A numbers; ★ = exists in serve.py today, rewrite marked
- **A1 Report received, no rush** (NEW, auto-posted at case creation): "Got it — your reference is #{id}. This isn't an emergency, so a person will get back to you within three working days. Every update lands on this page."
- **A2 Report received, soon**: "Got it — reference #{id}. We've marked this as needing attention soon; expect a call or message by the end of tomorrow."
- **A3 Report received, emergency**: "We've flagged #{id} as urgent. Your agent will call you within 4 hours. If anyone is in danger right now, don't wait for us: gas smells or no heat — leave and call 0800 111 999 (free, 24 hours); fire, crime or injury — 999; anything else — the office on 0121 496 0123."
- **A4 Person being assigned** (replaces "a job is open for it" while `assigned_to:null` — fixes T3 false reassurance): "We're finding the right person for this. Their name will appear here the moment they're on it."
- **A5 ★ Assigned** (rewrite of serve.py:543 "{who} has been put on this job by the agency."): "{name} is handling this. We'll tell you as soon as a visit time is arranged — keep an eye on this page."
- **A6 ★ Booking taken** (rewrite of 511 "took this job and will get in touch"): "{name} has taken the job and will be in touch to arrange access. Not often home? Tap 'Times that work' below."
- **A7 ★ Awaiting sign-off** (keep the standing-authority pattern the audit praised, 631): "The fix is done. The bill of £{x} is over our automatic limit, so {landlord} signs it off — usually within two working days. Nothing needed from you yet; we'll ask you to check the work before we close."
- **A8 ★ Declined** (replace silent "declined" badge; landlord-reject path 674): "The cost for this job wasn't approved, so we're rearranging it. Your agent will update you by {day} 5pm. You don't need to do anything."
- **A9 Done** (on M10 auto or paid+confirmed): "Work paid and finished. Did it fix it properly? — two buttons: **All fixed** / **Still not right**."
- **A10 Visit proposed** (appointment object): "Can {name} come {day}, between {from} and {to}? **That works** / **Different time**. Your gate code, if you give us one, is only shown to whoever's coming and is cleared the day after."
- **A11 ★ Quote** (rewrite of 561, which currently says "Waiting on the agency to approve"): "The quote is £{x}. Once the price is agreed the work starts. We'll tell you either way."

### Outbound (tenant → case thread) — B numbers; buttons post these verbatim
- **B1 Chase**: "It's been {n} days and nothing has moved. Can you tell me what's happening?" (+auto note to agent queue: "Tenant has chased — a reply is owed by {time}.")
- **B2 Escalate**: "This is worse today: {detail}. Please treat it as urgent."
- **B3 Not fixed**: "The visit happened, but it's still not right: {detail}. Please send someone back."
- **B4 Confirmed fixed**: "Yes, that's fixed. Thank you."
- **B5 Rating**: three taps — *easy / it was fine / it was a faff* + optional one line. Stored on the case; shown to the agent desk, never on the landlord's money card.
- **B6 Access note**: "Gate code {code}. {Where to leave tools/keys, pets, etc.}" (masked after write).
- **B7 Slot refusal + times**: "That time doesn't work. Times that do: {list}."
- **B8 Missed visit**: "Nobody came today."
- **B9 Different person**: "We'd feel better with a different tradesperson, if that's possible." (no reason required, ever)
- **B10 Withdraw**: "This has sorted itself / we reported it twice. Please close it."
- **B11 De-escalate**: "Actually it's fine again now." (agent must agree to drop the flag — law/safety stays human)

Replies authored by the tenant must render with their own name (the `post_msg` author plumbing at 306-315 already uses the session user — the case-action audit lines and `close`'s hardcoded `"agent"` need the same treatment).

## Screens this implies
One dashboard, `/tenant`, three views (all mobile-first, paper/pine theme of `dash.css`):

- **S1 Home (scroll)** — order = frequency: (1) safety banner (exists, keep first); (2) **"Waiting on you"** bucket — cases where M7/M8/M10/M11 prompts are open, with the buttons *inline on the card* (a stressed parent answers a tap, not a navigation); (3) **active cases**: badge + plain strip + countdown "update owed by Thu 5pm" + next-action button per the matrix (Chase when breached / Times that work / Not fixed…) + "Being handled by {name}" (exists) + visit strip when an appointment is confirmed; (4) report box (exists — add the "this is dangerous today" tick → B2); (5) closed cases with rate prompt; (6) documents (real links, not toasts); (7) sticky human contact: office number, hours, "call now".
- **S2 Case sheet** (tap a card; no new route needed — expandable card is fine): full report text (un-truncated — fixes T10), reference number + timestamps with times, **timeline = the scoped thread rendered chronologically with status events interleaved**, job card (name + "will call you" / confirmed appointment card with **That works / Different time / Nobody came**), access-note field (masked), money line (A7/A16 data), action row per matrix state, question box (B-* templates as quick chips + free text), emergency strip when urgency≥2.
- **S3 Close-out sheet** (auto after M10): one-tap rating (B5) → receipt-like summary "reported {date} · fixed {date} · {n} visit(s) · ref #case-{id}" → "Keep for my records" (printable history is the deposit-proof need).

Sections that stay: home card, footer promises (now backed by clocks). Nothing new goes on the public site.

**Rendering rules (the anti-static contract):** every card state has at most one primary button; silence beyond SLA always renders as breach + chase, never as a frozen strip; all dates show day+time; thread messages show author name and ago-time (the `when()` helper exists, tenant.html:77).

## NEEDS: backend primitives missing
Tagged by builder priority. Items with code refs are surgical edits, not new systems.

| NEEDS | Tag | What | Where it lands |
|---|---|---|---|
| N1 | **CRITICAL** | Render `case.thread` + case sheet (timeline, ask box, per-state buttons) — no new API; scoped thread already arrives (serve.py:218) | tenant.html |
| N2 | **CRITICAL** | `not_fixed` case-action (tenant): case→`dispatched`, create job `{revisit_of: old_job_id, status: open}`, post B3/A-N1, audit `tenant_reopen` actor=tenant. Fixes the reopen-strands-paid-job bug (728-731) | serve.py `/api/case-action` |
| N3 | **CRITICAL** | **Appointment object** `{id, case_id, job_id, when_from, when_to, contact, phone, status: proposed/confirmed/declined/missed/done, access_note}` + endpoints: trades/agent propose; tenant confirm/decline/missed/access-note. Today's "will get in touch" (511) is the entire access feature | serve.py + scoping (trades need it, landlord must not see `access_note`) |
| N4 | **CRITICAL** | SLA clock: `first_reply_by` computed from `triage.urgency` at case creation; `bumped_at` written by `chase` action (tenant, allowed only past breach); agent-desk sort by bump/urgency. Makes the "4 hours" promise (tenant.html:118) enforceable or delete it | serve.py |
| N5 | **CRITICAL** | `confirm_fixed` (+`tenant_confirmed_at`) and `withdraw` case actions with **correct authorship**: `close`/`reopen` audit actor from session (727), reopen text names the reopener; add branch-level role guards so tenant can't `close`-as-agent or `add_tradesperson` (709,719) | serve.py |
| N6 | **CRITICAL** | Identity: `handle_tenant_issue` overrides `name`/`email` from session user (453) — stops filing into another tenant's book (T6) | serve.py |
| N7 | **CRITICAL** | `escalate` case action: urgency→2, `tenant_escalated` flag, B2/A-X1, reset `first_reply_by` to +4h. Alternative to duplicate emergency reports | serve.py |
| N8 | **CRITICAL (cheap)** | Copy/label fixes: add `quoted` to STATUS_LABEL; never show "passed/handled" language while `assigned_to:null` (A4 strip); drop `authority` from tenant scope (220) | serve.py:220, tenant.html:64 |
| N9 | NICE | `rating` field `{score 1-3, note, at}` on case, accepted via M10-adjacent call; agent-desk readout | serve.py |
| N10 | NICE | Documents object (tenancy agreement, deposit cert, job receipt PDFs) + "prove it later" export from existing case/job data (invoice fields already in tenant scope) | serve.py |
| N11 | NICE | Outbound notification when thread msg lands (email/SMS) — tenants aren't sitting on the page polling | serve.py + job runner |
| N12 | NICE | Photo attachment on report/thread (evidence quality for mould/damp) | serve.py storage |
| N13 | NICE | `away_until` (M15) + `swap_requested` (M12) flags | serve.py |

Order of build: N8+N1 first (pure rendering, no state machine risk) → N5/N6 (attribution+identity, security) → N2/N7 (reopen+escalate on the case machine) → N4 (clock) → N3 (appointment, the only new object) → nices.

## Acceptance checklist (one line per move, QA-ready)
One line per move; QA drives two browser tabs (tenant ↔ agent) on live data + direct POSTs, then restores stage.json from `/tmp/stage-snapshot-before-audit.json`-style backup.

1. **M1 Report** — tenant types "boiler's dead" → card appears ≤20s with ref number, plain strip (no JEV/%/CATEGORY strings anywhere: `grep -E 'JEV|FALLBACK|URGENCY|SAFETY RISK|CATEGORY' tenant.html` → 0 hits), and the same case visible on /agent.
2. **M2 Progress** — agent assigns job → tenant card badge moves "a person is being assigned" → "{name} is on it" without reload; timeline shows both the status line and the assign message, with day+time stamps.
3. **M3 Ask** — tenant posts a question → appears in card timeline attributed "Daniel Mensah", visible on /agent thread, NOT in landlord scoped `/api/stage` (unless `to` includes landlord).
4. **M4 Chase** — a case past `first_reply_by` shows a countdown-at-zero + Chase button; tapping writes `bumped_at`, pins case to top of agent desk, tenant sees "reply owed by {time}"; a fresh case shows no chase button.
5. **M5 Escalate** — tapping "dangerous today" flips the strip to the emergency copy + 4h clock; audit shows `case_escalated` actor=tenant name; no new duplicate case was created.
6. **M6 Access** — tenant saves gate code → renders masked on tenant card, visible in trades scoped view, absent from landlord view, purged from responses >1 day after the visit.
7. **M7 Slot** — proposed appointment shows **That works / Different time**; confirm → status `confirmed` on both tenant and trades views; decline → agent sees it un-confirmed and re-proposes.
8. **M8 Missed** — after window, "Nobody came" is tappable → appointment `missed`, agent rebook note in thread, tenant strip says a new time is coming.
9. **M9 Not fixed** — on a resolved case, "Still not right" + detail → case badge "another visit needed", NEW job with `revisit_of` = old job id, old job still `paid`, thread has B3 + agent sees it; tenant never files a duplicate case.
10. **M10 Confirm** — "All fixed" sets `tenant_confirmed_at`, agent close button shows "tenant confirmed" hint; closing posts A9/A-F1 wording.
11. **M11 Rate** — rating tap stores on case; appears on agent case card; `GET /api/stage` as landlord shows no rating field.
12. **M13 Withdraw / M14 Reopen** — withdrawn case closes with `closed_reason` "withdrawn by tenant" and audit actor = the tenant's name (not "agent"); reopen ≤14 days posts "Daniel reopened this — {detail}", >14 days offers new-report-with-reference instead.
13. **M15 Pause** — away dates suppress appointment proposals; a case with `urgency>=2` shows "this can't wait while you're away — your agent will call" and accepts no pause.
14. **M16 Money/proof** — closed cases list shows "ref #case-{id} · reported {date} · fixed {date} · cost £{x} · paid {date}" straight from scoped jobs; print/CSV export matches on-screen totals.
15. **M17 Human** — office number + hours + 999/0800 reachable in ≤1 tap from every case sheet.
16. **Guardrails** — tenant POST `close`/`add_tradesperson`/`job-action` → 403; tenant POSTs issue with forged `name` → record carries session name; tenant-scoped `/api/stage` has no `authority`, no other tenant's cases, no tradesperson emails.
17. **Stress** — 20s polling survives an agent tab mutating the same case mid-read (no render corruption); every strip sentence ends in a countdown, a named person, or a button.
18. **Regression voice** — run `audit/jev_human_review.py` after copy lands; tenant strips must not introduce machine telemetry again.
