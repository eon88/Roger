# Workflow design — TRADESPERSON ("R. Doyle Gas & Heat", one van, one phone, sunlit screen)

**Method:** reality-locked to `stage-clone/serve.py` (full read, 2026-09-21), `stage.json`, `trades.html`, `audit/trades-audit.md`, `audit/CONSOLIDATED-AUDIT.md`. No POSTs were made against the live sandbox.
**Rule of the persona:** every move must be doable in under 10 seconds standing up, one thumb, in daylight. If a move needs typing, it needs a reason field, not a paragraph.

## Day in the life (5 lines max)
06:40 van, coffee: board once — anything new for me, anything I'm stuck on. 2 minutes max.
Mid-job: one thumb-tap pings ("on my way", "arrived") so the tenant stops ringing the office.
11:30 between jobs: quote the two requests sitting on me — amount, one line parts/labour, send.
17:00: photograph the finish, type the invoice number, done. Anything >£150 I say nothing about; I expect a chase.
Friday: statement out for the accountant; set "fully booked, back Tue" so the office stops asking.

## Objects & states today (from code)
**Job** (`serve.py: handle_job_action`, lines 497–644). States today, verbatim from code:
`open → assigned (agent) | quote_requested (agent) → quoted (trades submits) → in_progress (start / accept / approve_quote) → awaiting_approval (complete >£150 / agent send_to_landlord) → paid | rejected (landlord reject)`; plus `pending_verification` (accept blocked by credential gate) and `release` back to `open`.

Job fields: `id, case_id, property_id, message, triage, required_trade, status, assigned_to, requested_by, gate_reason, override_by, quotes[] ({tradesperson,pence,note,at,status: pending|approved|declined}), approved_quote_pence, invoice_pence, created_at, completed_at, paid_at`.
- **`approved_quote_pence` is written (L570) and never read by any logic.** The variance rule does not exist. (Confirmed by grep.)
- No `timeline`, no `attachments`, no `availability`, no `access_notes` fields anywhere.

**Case thread** (`case.thread[]`): `{author, role, text, to[], at}`. `/api/case-action` accepts `reply|inform` from role `trades` (L101) — **the backend already lets a tradesperson speak; the UI never shows a thread or an input.** Scoped-view bug: trades only sees messages with `"trades" in to` (L242), so *their own posts to ("tenant",) vanish from their own inbox* — and every existing template for trades-adjacent events posts to `("tenant",)` only (accept L511, submit_quote L561).

**Scoped `/api/stage` for trades** (L232–248): jobs where `status=="open" OR assigned_to==me OR requested_by==me` (field keep-list includes quotes/approved_quote_pence/invoice_pence); `threads` dict keyed by case id; approvals where `evidence.tradesperson==me` **with `reason` stripped** (`reason_given` survives); properties **with `tenant` stripped**; `authority`. → Quote-requested and assigned jobs **already arrive in the trades payload; trades.html simply doesn't render them** (only `open`, `in_progress`, `pending_verification`, money states).

**Approval** (`approvals[]`): `pending → approved|rejected`, reject requires reason (L659), decided is terminal (`already decided` 409). Landlord rejection spawns an `agent_task` case (L676) — the "decisions never vanish silently" pattern this doc reuses for disputes.

**Credentials**: `TRADE_PROFILES` (in-memory): `{trades[], gas_safe: str|None}` — seeded `"VERIFIED-DEMO"`, no expiry. `credential_check` (L485) passes on **any truthy** gas_safe string. Registration form collects `insurance_expiry` + `gas_safe_number` (L379–381) but approval copies only the number (L410–414); **expiry is never stored on the profile, never checked, never shown** — to trades or the agent. `/api/trades-pool` (agent-only) returns `gas_safe: bool` — expiry invisible to everyone.

**Authority**: `standing_limit_pence = 15000`. `complete` (L606–639): invoice > limit → approval + `awaiting_approval`; ≤ limit → `paid` same request.

**Actions that do NOT exist in code despite being imagined in the brief**: `escalate_invoice` (no branch), decline-by-trades, status pings, photo upload, dispute, availability, statement export.

## Action matrix (object × state → moves)
Legend — **[HAS]** exists end-to-end · **[UI]** backend exists, screen missing · **[NEW]** needs a backend primitive (NEEDS ref in §NEEDS). `to:` = `post_msg` audience; every trades-authored post is `to=["agent","trades"]` unless stated (agent sees unscoped stage; `"trades"` keeps it visible to the author — see N4b).

### Board lane — job `open`
| # | Move | Preconditions | State / data effect | Notify (thread) | Status |
|---|------|--------------|--------------------|-----------------|--------|
| M1 | **Take this job** (`accept`) | session=trades; `credential_check` vs `required_trade` | → `in_progress` (or `pending_verification` if cert fails, with `gate_reason`); `assigned_to=me`; case→in_progress | tenant: T1 | [HAS] — fix: payment terms + urgency on card *before* tap (audit P1) |
| M2 | **Can't take it** (`decline`) | any open card | stays `open` for others; `job.declines+={by,reason,back_from}`; audit | agent: T2 | [NEW] N1 |
| M3 | Ask about it (box on card) | logged in | thread only | agent: T3 | [UI] N4 |

### Quote lane — `quote_requested` (agent asked *me*; `assigned_to=me` — payload already contains it)
| # | Move | Preconditions | Effect | Notify | Status |
|---|------|--------------|--------|--------|--------|
| M4 | **Submit quote** (`submit_quote` £ + parts/labour note ≤500) | `actor==assigned_to` | quote appended (pending) → `quoted`; case→quoted | tenant+trades: T4 | [UI] N3 — backend L554 works today, board never renders it |
| M5 | **Can't quote** (`decline`) | `quote_requested` | → `open`, `assigned_to` cleared; reason recorded | agent: T5 | [NEW] N1 |
| M6 | Clarify scope before pricing | — | thread only | agent: T3 | [UI] N4 |

### `quoted` (my quote is with the agency)
| # | Move | Preconditions | Effect | Notify | Status |
|---|------|--------------|--------|--------|--------|
| M7 | **Withdraw/revise quote** | all my quotes `pending` | quote→`withdrawn`, job→`quote_requested` | agent: T7 | [NEW] N12 (NICE) |
| M8 | **Re-quote after `decline_quote`** | agent declined (status back to `quote_requested`, `reason_given`-style reason in thread) | new pending quote → `quoted` | as M4 | [HAS] via M4 |
| — | otherwise: wait. DEAD for the day; card must *say* "agency deciding, SLA 1 working day". | | | | |

### `assigned` (agent put me on without a price round)
| # | Move | Preconditions | Effect | Notify | Status |
|---|------|--------------|--------|--------|--------|
| M9 | **Start job** (`start`) | `actor==assigned_to` | → `in_progress`; case→in_progress | agent log | [UI] N3 — backend L602 exists, no button on any card |
| M10 | **Hand it back before starting** (`release`+reason) | `assigned` | → `open`, `assigned_to=None`, reason stored | agent: T10 | [NEW] N6 (release is `in_progress`-only today, L532) |

### `in_progress` (job in hand)
| # | Move | Preconditions | Effect | Notify | Status |
|---|------|--------------|--------|--------|--------|
| M11 | **On my way** (`ping`) | mine | `job.timeline+={on_my_way,eta_min}`; NO status change | tenant(+trades): T11 | [NEW] N5 |
| M12 | **Arrived** (`ping`) | mine | `timeline+={arrived}` | tenant: T12 | [NEW] N5 |
| M13 | **Worked, closing up** (`ping` "done on site") | mine | `timeline+={done_on_site}` | tenant: T13 | [NEW] N5 |
| M14 | **Job done — invoice** (`complete` £ + photos + ref) | mine | variance check vs `approved_quote_pence` (N2) then: ≤ limit & in quote → `paid`+`paid_at`; else approval row → `awaiting_approval`; case sync | T14a/b/c per outcome | [HAS] bare — photo [NEW] N9, variance [NEW] N2 |
| M15 | **Hand it back mid-job** (`release`) | `in_progress` | → `open`, `assigned_to=None` — *add required reason* | agent: T10 | [HAS] (silent today; reason = small N6 extension) |
| M16 | Message tenant/agent (access, parts, "nobody home") | mine | thread; tenant sees it | tenant or agent: T3 | [UI] N4 |

### `pending_verification` (my booking held: no/expired credential)
| # | Move | Preconditions | Effect | Notify | Status |
|---|------|--------------|--------|--------|--------|
| M17 | **Send credentials to unlock** (`renew_credentials`) | `requested_by==me`, `gate_reason` shown | updates profile pending agent re-check; agent's existing `verify_approve` → `in_progress`, `verify_decline` → `open` | agent: T17 | [NEW] N11 (agent-side moves exist; trades-side does not) |

### `awaiting_approval` (invoice over the line, landlord's hands)
| # | Move | Preconditions | Effect | Notify | Status |
|---|------|--------------|--------|--------|--------|
| M18 | **Chase payment** | ≥3 working days since `approval.requested_at`, ≤1 chase per 3 days | agent_task case + nudge landlord; `chased_at` stored | agent+landlord: T18 | [NEW] N10 (card copy already promises a chase that does not exist) |
| M19 | Amend invoice (fat-finger fix) | `approval.status==pending` | `invoice_pence` + `amount_pence` updated; audit | agent: T19 | [NEW] N13 (NICE) |
| — | wait, with a visible countdown "day 4 of 7 — we chase". Landlord's name NOT shown (unchanged scoping). | | | | |

### `paid`
| # | Move | Preconditions | Effect | Status |
|---|------|--------------|--------|--------|
| M20 | **Receipt + running statement** | mine, paid | read-only money tab; CSV "for the accountant" | [UI-partial]: list computable from scoped jobs now; VAT artefacts [NEW] N14 |
| — | No undo on paid — money movement is a human correction (M16 to agent). One-line justification, doctrine §4. | | | |

### `rejected` (landlord declined my invoice)
| # | Move | Preconditions | Effect | Notify | Status |
|---|------|--------------|--------|--------|--------|
| M21 | **Dispute** (`dispute`) | `rejected`, reason required | job → `in_progress` + `disputed_note`; agent re-routes: `send_to_landlord` again (precond already allows in_progress+invoice) or sides with landlord and closes | agent: T21 | [NEW] N7 — today `rejected` is terminal: £220 of work → £0 with no comeback (audit Task 3) |

### Profile-level objects (not job states)
| # | Object × state | Move | Effect | Status |
|---|---------------|------|--------|--------|
| M22 | **Availability** (available / fully booked / off + `until` + note) | `set_availability` (trades self-serve) | on profile; `/api/trades-pool` surfaces it; agent's assign/request_quote get a "this trade is booked until X" warning; banner on my header | [NEW] N8 |
| M23 | **Credentials** (Gas Safe #, expiry, insurance expiry) | view own status + renew (M17 same primitive) | card shows "Gas Safe valid to {date}" or red "EXPIRED — bookings will be held"; agent pool shows expiry (gating) | [NEW] N11 |
| M24 | **Inbox** — read all threads on my cases | GET (already scoped) | thread panel on every card | [UI] N4 |
| M25 | **Reply in thread** (`case-action reply`) | any non-terminal job | `post_msg` under my session identity | [UI] N4 — backend L700 allows trades today |
| M26 | **Job detail sheet** — full message, triage, access notes, my quote history (`quotes[]` with statuses), timeline | open card | read-only | [UI] (message already un-truncated in current markup; access_notes [NEW] N17 NICE) |
| M27 | **Live board** — 20s poll + new-work badge + status-flip flash | — | already built | [HAS] keep |

**Frequency ordering for the screen:** M9/M11/M12/M14 (daily, thumbs) → M4/M1/M2 (daily, decision) → M24/M25 → M18/M21 (rare, critical) → M20/M22/M23 (weekly).

## Dead ends today (the pain list, quoted from current surfaces)
1. **The quote lifecycle is invisible.** `request_quote` sets `assigned_to=me` and the scoped `/api/stage` ships the job — `trades.html` renders only `open`, `in_progress`, `pending_verification`, money states. An agent asking "quote this boiler" produces **nothing on the trades screen until the job is approved and running**. The most money-shaped ask in the product has zero receiver.
2. **There is no "no".** No `decline` action exists anywhere in serve.py; `release` is gated `status=="in_progress"` (L532). An open job can be taken or ghosted; a quote request can't even be ghosted politely. Ghosting is the only decline vocabulary. (Audit P2: "once taken, a job is mine forever".)
3. **`quoted` and `assigned` are no-op states for the worker** — cannot revise a quote, cannot start (backend `start` exists, no button), cannot hand back before starting.
4. **Tradespeople cannot speak.** `/api/case-action` whitelists the `trades` role for `reply|inform` (L101) and threads are scoped to them (L242) — and the dashboard has **no thread view and no input box at all**. The API is editable; the UI is a wall. This *is* the user's "process editability low" complaint, verbatim.
5. **Inbox bug:** trades threads filter on `"trades" in to`; the accept (L511) and submit_quote (L561) templates post to `("tenant",)` only — so **my own quote text never appears on my own board**, and any reply I send to the tenant vanishes from my view.
6. **No between-acceptance-and-completion signal.** No `on my way / arrived` primitive; the tenant's "will anyone come?" question has no system answer that isn't a phone call to the office.
7. **Variance rule doesn't exist.** `approved_quote_pence` is written once (L570) and read by no logic. Quote £80, invoice £149 → auto-settles silently. Quote £80, invoice £500 → straight to the landlord without the agent who approved the price ever seeing the gap.
8. **No evidence.** No photo/attachment field, endpoint, or view anywhere in the stack — completion is one integer.
9. **The chase promise is a lie.** `trades.html:60,102` say "auto-chased at 3 days" / "auto-chased at 3 days" — serve.py has **no timer of any kind** (stdlib request handler, zero background threads). `awaiting_approval` can rot forever; no expected-payment date, no `who do I chase` (landlord name isn't in the trades payload — correct for privacy, but nothing replaces it).
10. **`rejected` is terminal.** £220 of done work → £0 with a badge. No dispute, no re-price, no conversation hook (the audit's "silent death" pattern, still present after v2 because landlord-reject creates an *agent* task, not a *trades* path).
11. **No VAT paperwork.** Invoice = `invoice_pence` integer. No number, no net/VAT split, no billed-to, no issued/settled dates (seeded jobs lack `completed_at`/`paid_at` entirely), no statement, no export. A VAT-registered sole trader cannot file from this portal (audit: "a promise rendered as a badge").
12. **Availability doesn't exist.** The audit persona is "fully booked" and the system treats him as permanently free; the agent's `/api/trades-pool` has no "ask me not" signal of any kind.
13. **Credentials have no clock.** `gas_safe: "VERIFIED-DEMO"` passes `credential_check` forever; `insurance_expiry` is collected at registration (L381) and then **never stored on the profile, never checked, never displayed — to the tradesperson or the agent**. An expired Gas Safe engineer keeps booking gas jobs; the gating that exists is name-truthiness, not validity.
14. **Money transparency aims at the payer, never the worker** (audit verbatim): the landlord's card explains "that's why it reached you"; the tradesperson gets a bare badge — no why, no when, no who-next.

## Handoffs & SLAs
Direction convention: **→ me** = work arrives on my board; **→ them** = I produce the artifact someone else waits on. SLAs are suggestions to the human; the system's job is to *count and chase*, which needs the timer primitives in N10.

| Handoff | Trigger | Artifact | SLA | Chase path (needs N10) |
|---|---|---|---|---|
| Agent → me | `assign` / `request_quote` | job card in For-me lane, with `required_trade`, triage, full text | acknowledge (start / quote / decline) within **2 working days**; emergency (`urgency≥2`): **4 working hours** | day 3: card turns amber "overdue — the office sees this"; day 5: job auto-returns to board (`open`), thread says so |
| Me → Agent | `submit_quote` | pending quote (£ + parts/labour) | approve/decline within **1 working day** (before weekend or site visit) | my card shows "agency deciding · day 1 of 1"; stale > 1 day → amber |
| Me → Agent/Landlord | `complete` + invoice ≤ £150 | settled job + statement line | **same day** (auto under standing authority — enforced today, L634) | n/a |
| Me → Landlord (via agent) | `complete` invoice > £150 or > approved quote (N2) | approval row w/ evidence (tradesperson, dates — exists L620) | landlord sign-off **3 working days** | my Chase button (M18) at day 3 → agent_task + landlord nudge; day 7 → agent calls the landlord |
| Agent → me | `approve_quote` | "you can start" thread post (exists L573, to tenant+trades) | start within agreed window | — |
| Agent → me | `decline_quote` / `decline_invoice` | reason in thread (decline_quote has one, L581) | I re-quote within 2 working days or say "not touching it" (M5) | unanswered 2 days → job back to board |
| Gate hold → Agent | blocked accept | `pending_verification` + `gate_reason` (exists L515) | agent verify_approve/decline within **4 working hours** (safety trade) | my Credentials tab shows "waiting on office · sent {when}" |
| Rejected → Agent | landlord decline (agent_task exists L676) or my dispute M21 | dispute note + job back in agent's hands | agent calls/texts me within **1 working day** | thread escalation to "this is now about the money" |
| Me → Agent | `decline` with `back_from` date | availability fact on my profile | agent re-dispatches to pool within 1 working day | my name greyed on the agent's pool until `back_from` (N8) |

**Standing-authority sentence, trades side** (lift of the praised landlord copy, shown on every card *before* accept and on every invoice box): *"You're working for the agent, not the tenant. Anything up to £150 settles the day you file it — that's the agency's standing authority, no landlord needed. Above it, the landlord signs off first: that's why this one waits and the £60 one didn't."*

## Undo / reassign / dispute / pause
The four moves prototypes forget, per state. "—" = deliberately absent, one-line reason.

| Job state | Undo | Reassign | Dispute | Pause |
|---|---|---|---|---|
| `open` | — (nothing done yet) | agent `assign`s someone (exists) | — | **Decline with reason + back-date (M2)** *is* the pause: sets availability expectation |
| `quote_requested` | `decline` clears me off it (N1) | agent re-`request_quote` to another pool member (exists) | decline_quote reason already in thread; I can argue back via M25 before re-quoting | same as open |
| `quoted` | **withdraw_quote (M7, N12)** | agent can still `assign` elsewhere from `quoted` (L536 allows) — tell me in thread first (etiquette, not gate) | — | — |
| `assigned` | **hand back w/ reason (M10, N6)** | agent `assign` (L536 allows `assigned`? — it lists open/quote_requested/quoted/pending_verification; **extend to `assigned`** — small N6 fix) | ask "why me?" via thread | — |
| `in_progress` | **release (M15, exists)** — add required reason so the agent knows why it's back | agent takes it back via release+assign; no worker-to-worker swap (GDPR + pool trust) — suggest-someone on decline instead (N15) | "the access promise changed / tenant won't open" → thread, agent mediates (office phone exists today; keep it) | job-level pause **absent on purpose**: domestic repairs are hours not weeks; availability (M22) is the pause primitive, per-person not per-job |
| `pending_verification` | `verify_decline` returns job to board (exists) | agent routes to a verified trade (exists) | I send fresh credentials (M17, N11); if the gate is wrong (I *am* Gas Safe) the thread + "flag wrong gate" = same primitive | held until agent decides — the pause is the state |
| `awaiting_approval` | **amend_invoice before decision (M19, N13)** | — | not yet — nothing decided | countdown + **Chase (M18)** replaces silent waiting |
| `paid` | — **money is a human correction**: message the agent (M25), never self-reverse a settlement | — | over/underpayment after settlement: thread, then agent raises on the next statement line | — |
| `rejected` | — | — | **dispute (M21, N7)**: reason required; job → `in_progress` + agent re-routes (send_to_landlord precondition already fits). Never terminal-silent again. | — |
| *(global)* | undo of `decline` = re-take job from board (M1) | — | — | **set_availability (M22, N8)**: off / fully booked + return date; agent pool shows it, assign warns |

## Message templates (exact `post_msg` payloads — van voice, no fluff)
Exact payloads for `post_msg` / template strings. `{me}`=tradesperson display name, `{job}`=job id, `{addr}`=property short title, `{date}`=dd MMM. Voice rules: first person, one or two sentences, amount always with reason, no theatre metaphors, no "please be advised". `to:` audiences per N4b — every trades post includes `"trades"` so the author sees it, and `"agent"` (agent is unscoped but the label documents intent).

**T1 · accept** (replaces L511, adds ETA slot + fixes audience):
> {me} has taken {job} — expected on site {window}. Access anything that changes, ring the office: 0121 496 0123. `to:["tenant","trades"]`

**T2 · decline open** (M2):
> Can't take {job} — {reason: too far | too busy | not my trade | not enough info}. {me} `{back_from: back {date} | }` `to:["agent","trades"]`

**T3 · question on any card** (M3/M6/M16 — free text, capped 500):
> Question before I commit: {text} `to:["agent","trades"]` (use `to:["tenant","trades"]` for access-on-the-day: "I'm outside — which door?")

**T4 · submit_quote** (replaces L561 — keeps tenant line, adds the parts/labour shape + validity):
> Quote for {job}: £{amount} — {note e.g. "labour 2h + pump £64"}. Parts ordered once it's approved. Price good for 14 days. Waiting on the agency. `to:["agent","tenant","trades"]`

**T5 · decline quote request** (M5):
> Can't price {job} — {reason: can't see the fault without a visit | out of my trade | can't get parts this side of your deadline}. Pass it on, no problem. `to:["agent","trades"]`

**T7 · withdraw quote** (M7):
> Pulled my quote on {job} — I mis-read the scope. New number shortly. `to:["agent","trades"]`

**T10 · hand back (assigned or mid-job, reason required)** (M10/M15):
> Handing {job} back — {reason: access fell through | parts won't land in time | genuinely not my trade}. Sorry for the swap. `to:["agent","trades"]` (+`"tenant"` if already on site booked)

**T11 · on my way** (M11):
> Heading to {addr} now — about {eta} minutes. `to:["tenant","trades"]`
**T12 · arrived** (M12): `> On site at {addr}.` `to:["tenant","trades"]`
**T13 · done on site** (M13): `> Finished at {addr}. Invoice going in today.` `to:["tenant","trades"]`

**T14a · invoice settled** (≤ limit, ≤ quote — the transparency aimed at the *worker* for once):
> Work done. Invoice £{amount} — under the £150 standing authority, so it settles today from the agency. No landlord needed. `to:["agent","tenant","trades"]`
**T14b · invoice to landlord** (> limit):
> Work done. Invoice £{amount} is above the £150 standing authority, so the landlord signs it off first — usually 3 working days, then I chase. Reference {invoice_ref}. `to:["agent","tenant","trades"]`
**T14c · variance flag** (> approved quote, N2):
> Heads up: invoice £{amount} is above the approved quote £{quote} by £{gap} — {note: found rotten surround once open}. The agency approves the difference before it goes to the landlord. `to:["agent","trades"]` + approval evidence carries `"variance": {quote_pence, invoice_pence}`

**T17 · credentials sent to unlock a held booking** (M17):
> Gas Safe re-registered — number ending {last4}, valid to {date}. Waiting on the office to clear the hold on {job}. `to:["agent","trades"]`

**T18 · chase** (M18, only after day 3):
> Chasing {job}: invoice £{amount} has waited {n} working days for sign-off. Parts cost me up front. `to:["agent","landlord","trades"]`
**T19 · amend invoice** (M19):
> Correction on {job}: I billed £{wrong}, it's £{right} — {reason}. New number attached to the same sign-off. `to:["agent","trades"]`

**T21 · dispute a declined invoice** (M21):
> I don't accept this decline: {reason: the work is done, photos are on the job | price was agreed in writing on the quote}. The {job} work happened — tell me what happens next. `to:["agent","trades"]` (tenant NOT told until decided)

**T22 · availability** (M22):
> {me}: {fully booked until {date} | off until {date}} — {note optional}. Anything on the board is going to someone else until then. `to:["agent","trades"]` + sets profile, no job state touched.

**Existing posts to KEEP as-is** (already well-worded): approve_quote "Quote of £X approved — {who} can start." (L573); decline_quote "Quote declined — {reason}. Please re-quote or a different trade will be asked." (L581); landlord decision line (L664–667). **Timer post (N10):** "Quote request on {job} went unanswered for 5 days — back on the board." `to:["agent","trades"]`.

## Screens this implies (trades.html restructure)
One page (`/trades`, `trades.html`), three tabs, sticky header strip. Screens listed as affordances; visuals follow `dash.css` conventions + the audit's 44px/AA-contrast floor (that's fine-ux-polish's job, not this doc's).

**Header strip (always visible):** availability chip (green *available* / amber *booked until {date}* / grey *off*) → tap opens availability sheet (M22); credential dot (Gas Safe ✓ to {date} / ⚠ expiring / ✗ expired) → tap opens Credentials (M23); new-work badge on the 20s poll (M27).

**Tab 1 — Work** (default). Lanes top-to-bottom by frequency:
1. **For you** — `quote_requested` + `assigned` + `quoted` jobs where I'm named. Card = full message, address+area+`required_trade` tag, urgency strip, then the ONE action: [Give a price →] amount+note sheet (T4) / [Start →] (M9) / amber "agency deciding · day 1 of 1" chip for `quoted` with [Withdraw] (M7). Every card carries [Can't do this] → reason chips (T2/T5) — the polite no, two taps.
2. **In hand** — `in_progress` + `pending_verification` (held cards show `gate_reason` + [Send credentials] M17). In-hand card = ping row **[On my way] [Arrived] [Done]** (T11–13, big buttons) + invoice box + [Job done — invoice] (M14) with photo slots + optional invoice ref + the standing-authority sentence inline BEFORE submitting + [Hand back] (M15). Thread expander + reply box on every card (M24/M25).
3. **Available work** — `open` board (today's section, improved): terms line and urgency **before** [Take this job] (M1), [Can't take it] beside it (M2), full text, `required_trade`/Gas-Safe tag (exists in payload).
4. **Waiting on money** — `awaiting_approval` + `rejected`: countdown "day 4 — we chase at 7", [Chase] enabled per N10 rule (M18), on `rejected`: declined reason (already visible via `reason_given`) + [Dispute] (M21).

**Tab 2 — Money** (M20): statement table of my jobs — job, address, invoice, issued (`completed_at`), settled (`paid_at`), status; running totals; [Export CSV] labelled "for the accountant"; per-row [Receipt] once N14 invoice artefacts land. `awaiting_approval`/`rejected` rows mirror Tab 1 lanes 4.

**Tab 3 — Me:** availability sheet (radio: available / fully booked / off + return date + note, T22) · Credentials (Gas Safe number + expiry — read-only, [Renew] = T17 flow; insurance expiry same; status explained in one line: "expired = gas bookings go on hold, the office releases them") · Payment terms recap (standing-authority sentence).

**Job detail sheet** (M26): slide-up from any card — full text, triage, access notes (N17), my quote history with statuses (`quotes[]` in payload today), timeline (pings), full thread.

Nothing on this screen is a landlord or agent surface: no role tabs (audit's identity-fraud vector stays closed — server already scopes `/api/stage`, keep it that way).

## NEEDS: backend primitives missing
All additions live inside the existing machines — `/api/job-action` branches and `serve_scoped_stage` — no forked statuses, no new servers (stdlib only, lazy-evaluated timers). Builder: every item names its hook point in `serve.py`.

| # | Sev | Primitive | Hook / shape |
|---|-----|-----------|--------------|
| N1 | **CRITICAL** | `decline` action | New branch in `handle_job_action`: valid from `open`/`assigned`/`quote_requested`, `actor` session trades; body `{id, action:"decline", reason(enum), note≤300, back_from?ISO}`. From open: job stays open, `job.declines+=[...]`, post T2. From assigned/quote_requested: also `assigned_to=None`, status→`open`. Audit `job_declined_by_trades`. Today there is no "no" (dead end 2). |
| N2 | **CRITICAL** | Variance rule on `complete` | In `complete` (L606): `if job.get("approved_quote_pence") and pence > approved_quote_pence + max(2000, 10% of quote)` → force approval route regardless of standing limit, approval gets `sent_by_agent:false, variance:{quote_pence, invoice_pence}`, post T14c, audit `invoice_variance_flagged`. `approved_quote_pence` is written (L570) and never read today — the £80-quote-£149-invoice silent slip is live. |
| N3 | **CRITICAL** | Render `assigned`/`quote_requested`/`quoted` | `trades.html` only: the scoped payload already carries these jobs (L237). "For you" lane + [Give a price]→`submit_quote`, [Start]→`start`, decision chip. Zero backend change; highest pain-per-line. |
| N4 | **CRITICAL** | Thread UI + visibility fix | (a) UI: render `stage.threads[case_id]` + reply box → existing `/api/case-action reply` (trades whitelisted, L101). (b) Bug: L242 filter becomes `"trades" in to or t["author"]==me`; templates T4/T1/T11–13 include `"trades"` in `to`. Without (b) my own words vanish from my inbox. |
| N5 | **CRITICAL** | Status pings | Actions `ping` with `{kind: on_my_way|arrived|done_on_site, eta_min?}`: `job.setdefault("timeline",[]).append({kind, at, eta_min})` + `post_msg` T11–13; no status change. Add `timeline` to the trades field keep-list (L233) and the tenant view. |
| N6 | **CRITICAL** | Release everywhere + reassign hole | `release` (L532) accepts `assigned` and `quote_requested` too, requires `reason`, posts T10. Agent `assign` precondition (L536) currently excludes `assigned` — add it so a mis-assignment is fixable without a release round-trip. |
| N7 | **CRITICAL** | Dispute | Action `dispute` from `rejected`: `{reason required ≤300}` → `job.status="in_progress"`, `job.disputed={by,reason,at}` (approval row stays `rejected` — decided is decided), post T21, audit. Agent re-routes with existing `send_to_landlord` (precondition `in_progress`+invoice already fits, L585) or human-closes. Kills the terminal-£0 (dead end 10). |
| N8 | **CRITICAL** | Availability | Per-trade field `{availability: available|fully_booked|off, until?ISO, note}` — **store in `stage.json["trades_state"][company]`, not in-memory `TRADE_PROFILES`** (survives restart; that's also the home for N11). Action `set_availability` (trades self or agent-on-behalf) posts T22. `approved_trades()`/`/api/trades-pool` returns it; `assign`/`request_quote` add a non-blocking warning field `"trade_unavailable_until"`. |
| N9 | **CRITICAL** | Photos/attachments | `POST /api/job-attachment` `{id, data_urls:[≤4 base64 ≤1.5MB]}` writes `uploads/{job}/{n}.jpg`, stores `job.attachments=[{path,name,at,kind:"completion"|"message"}]`; serve under `/uploads/` (auth: same role scope as stage). `complete` accepts `attachments` inline; tenant/agent case views render thumbnails. Add to keep-list. Nothing exists today (dead end 8). |
| N10 | **CRITICAL** | Chase + honest timers | No cron needed — lazy eval in `serve_scoped_stage`: compute `days_pending` (skip weekends) from `approval.requested_at`; expose `chase_allowed`. Action `chase` (≥3 wd, ≤1/3wd via `chased_at`) → agent_task case (L676 pattern) + post T18 to landlord. Quote-request SLA: if `quote_requested` >5 days untouched → auto-`open` on next request touching the job + timer post (Handoffs table). Until built, delete the "auto-chased at 3 days" copy — it lies (dead end 9). |
| N11 | **CRITICAL** | Credential clock | Copy `gas_safe_number`→`trades_state[name].gas_safe_expiry` from registration `insurance_expiry`/new `gas_safe_expiry` input at approval (L410–414). `credential_check` (L485) fails when `expiry < today` (reason: "Gas Safe expired {date}"). `/api/trades-pool` sends the **date**, not the bool — agent gating. Action `renew_credentials` (trades, {number, expiry}) → updates profile `pending_recheck` + post T17; agent's existing registration/verify decision clears it. Move `TRADE_PROFILES` itself into `stage.json` so it stops evaporating on restart. |
| N12 | NICE | `withdraw_quote` | `quoted` + all pending: quote→`withdrawn`, status→`quote_requested`, T7. |
| N13 | NICE | `amend_invoice` | `awaiting_approval` + approval pending: update `invoice_pence` + `amount_pence`, T19, audit. Blocks M19 only. |
| N14 | NICE | VAT artefacts | On `paid`: `job.invoice={number:"INV-{seq}", net_pence, vat_pence (20% if profile.vat_registered), gross_pence, billed_to:"<agency entity>", issued_at:completed_at, settled_at:paid_at}`. Money tab computes statement client-side from scoped jobs; `[Export CSV]` = same rows. Backfill `completed_at/paid_at` on seeded jobs (5 jobs lack them). Production blocker when real money moves; demo-OK without. |
| N15 | NICE | Suggest-a-colleague | `decline` body + `suggest:company` (from pool); agent sees "not me — try X". |
| N16 | NICE | ETA | Already in `ping` payload (`eta_min`) — surfaces on tenant card when tenant view renders timeline. |
| N17 | NICE | Access notes | `job.access_notes` + `parking_notes`, agent-filled at `assign`/`request_quote` (extend those payloads), rendered on every trades card — closes the audit's "gate code? which entrance?" without exposing the tenant (privacy scoping stays). |

## Acceptance checklist (one testable line per move)
Each line is one browser/curl scenario as `R. Doyle Gas & Heat` (unless noted). All reads via GET `/api/stage` after the action.

1. **M1** Open board → [Take this job] on a plumbing job → card moves to *In hand*, `status=in_progress`, tenant thread shows T1 line with office number.
2. **M1-gate** As an uncertified identity, take the gas job → `pending_verification`, `gate_reason` on my card, agent notified; `verify_approve` (agent) → mine, `in_progress`.
3. **M2** [Can't take it] → "too busy" + back Fri → job still `open`, thread shows T2 with my reason, agent pool chip reads *booked until Fri* (via N8 link), audit `job_declined_by_trades`.
4. **M4** Agent `request_quote`s a boiler (as agent) → job appears in my *For you* lane with full message → [Give a price] £420 + "labour 3h + flue £96" → status `quoted`, quote visible to me (author-visibility fix), case `quoted`.
5. **M5** [Can't quote] "no access for a week" → job back `open`, `assigned_to` cleared, agent sees reason in thread.
6. **M7** After quoting, [Withdraw] before agent decides → job `quote_requested`, quote `withdrawn`, old number gone from approval path.
7. **M8** Agent declines my quote (reason "price not right") → chip flips to "agency declined — re-quote"; resubmit £350 → `quoted` again.
8. **M9** Agent assigns a job to me → [Start] on my card → `in_progress`; **M10** same state → [Hand back] with reason → `open`, reason in thread.
9. **M11–13** In-hand job → tap [On my way] → tenant's thread shows "about 20 minutes"; [Arrived] → "On site at …"; job `status` **unchanged** (`in_progress`) and timeline visible in my detail sheet.
10. **M14-settle** Complete with £60 (approved quote £55 +10% tol) → `paid`, `paid_at` set, statement row, T14a.
11. **M14-variance** Approved quote £80, invoice £149 → **must NOT auto-settle**: `awaiting_approval`, approval row carries `variance`, agent got T14c.
12. **M14-landlord** Invoice £210 → `awaiting_approval`, T14b names the £150 line and expected 3 wd; landlord's own card unchanged.
13. **M15** [Hand back] mid-job with reason → `open`, `assigned_to` null, tenant sees "the office will re-arrange", agent thread has the reason.
14. **M17** Held gas job → [Send credentials] with number+expiry → profile `pending_recheck`, agent verify lane shows expiry date; expired date entered → next gas accept also held.
15. **M18** Approval aged 3 wd → [Chase] enabled → posts T18, creates `agent_task` case, second tap same day refuses; aged 2 wd → button exists, greyed with "day 2 of 3".
16. **M19** Amend £140→£145 while pending → approval `amount_pence` = 14500, decided after still settles the new amount.
17. **M20** Money tab lists paid jobs with issued/settled dates; CSV downloads with header row; totals equal sum of `invoice_pence` on my paid jobs.
18. **M21** `rejected` job → [Dispute] with reason → job `in_progress` + `disputed` note, agent can `send_to_landlord` again; no dispute without a reason (400).
19. **M22** Set *off until 29 Sep* → header chip amber; as **agent**, opening the pool shows the flag and `assign`/`request_quote` return a warning in the response body while still allowing the human override.
20. **M24/25** Reply box on any card → message appears in tenant/agent views iff addressed to them; my own posts visible on my board (N4b).
21. **M26** Any card opens detail sheet: full text (no ellipsis), `required_trade`, access notes, quotes history with statuses, timeline.
22. **M27** Two browsers: agent `request_quote`s → my board updates ≤20 s with badge + flash (poll exists today; keep the regression).
23. **Scoping** Trades GET `/api/stage`: no tenant names in properties, no other trades' quotes/approvals, no unaddressed thread messages (`keep`-list extended only with `timeline/attachments/declines/access_notes`).
24. **Copy truth** "auto-chased at 3 days" appears only after N10 is live; until then the card says "we chase when it's late".
