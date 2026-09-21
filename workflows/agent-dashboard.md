# Workflow design — Agent Desk (Stage)

**Role:** the solo agency desk ("Stefan — the agency desk" in users.json). Choreographer of every case: answers tenants, briefs landlords, picks trades, approves quotes, moves invoices, vets the network.
**Built against:** `stage-clone/serve.py` @ HEAD in repo (v2 post-audit), `stage.json` shapes as seeded, `agent.html` affordances as shipped. Every move below maps to a **real endpoint + params** or carries `NEEDS:`. Where the brief in other docs says `escalate_invoice`, the implemented name is **`send_to_landlord`** — this doc uses the code's name.

> Note for the builder: today the *backend* already supports most of the agent's missing choreography (reply, inform, add_tradesperson, assign, request_quote, approve_quote, decline_quote, send_to_landlord). The agent UI exposes almost none of it — Cases has only a Close box, Jobs only the two verification buttons. **Most of this doc is a UI pass over existing endpoints, plus a short list of genuinely missing primitives (NEEDS section).**

---

## 1. Day in the life (5 lines)

- Phone-first: a tenant rings or types about a boiler; the desk is on a 390px phone at the school gate as often as on a laptop.
- Three check-ins: 8am (overnight reports + emergencies first), lunch (quotes in, access arranged), 6pm (invoices, chases, tomorrow's bookings).
- The desk's fear is not "no buttons" but *silent states*: a gas job nobody took, a quote the landlord never saw, a case that looks closed but isn't.
- Pressure unit = the case, not the job: the desk thinks "492 → who, when, who pays", and wants the whole thread on one screen.
- Every decision must be defensible later to a landlord or an inspector: reason on record, timestamp, no silent vanishing.

## 2. Objects & states today (from code — do not fork these)

**Case** `cases[].status` — observed values: `new` (enquiry, agent_task, reopened), `reported` (tenant/issue non-maintenance), `dispatched` (tenant/issue where triage.category=maintenance → job auto-created; also restored by decline_quote), `quoted`, `in_progress`, `awaiting_approval`, `resolved`, `declined` (all mirrored upward from job/approval events via `sync_case` — `serve.py:296`), `closed` (case-action close). Rule that stays: case.status follows job/approval; only `close`/`reopen` are manual.
**Job** `jobs[].status`: `open` → `assigned` (agent assign) / `quote_requested` (agent request_quote or decline_quote) → `quoted` (trades submit_quote) → `in_progress` (trades accept, trades start, agent approve_quote, verify_approve) → `awaiting_approval` (complete with invoice > limit, or agent send_to_landlord) → `paid` (complete ≤ limit auto-settle; landlord approve) | `pending_verification` (accept fails credential gate) | `rejected` (landlord reject). Quotes live in `job.quotes[] {tradesperson,pence,note,at,status:pending|approved|declined}`.
**Approval** `approvals[].status`: `pending` → `approved` | `rejected` (reason required on reject; reject spawns an `agent_task` case with `status:new`). One-shot: re-deciding returns 409. Fields: `id, job_id, property_id, landlord, amount_pence, reason, evidence{tradesperson,job_created,work_completed}, requested_at, decided_at, sent_by_agent`.
**Registration** `registrations[].status`: `pending` → `approved` | `rejected` (note optional; **no status guard — re-deciding a decided reg is silently possible today**, serve.py:398). Trades approve copies `trades/gas_safe_number` into `TRADE_PROFILES` (in-memory).
**Property** `properties[]`: id/title/area/beds/rent/landlord/tenant — **no endpoint mutates it. Zero states; read-only seed data.**
**Triage** `case.triage`: `{category: maintenance|viewing|finance|other, trade: gas|plumbing|electric|locksmith|damp|general|other, urgency: 0|1|2, safety: 0..1, confidence, engine: jev|stub}` — set once at intake; recalibration exists only as a system batch.
**Money rule** `stage.authority.standing_limit_pence` (15000). ≤ limit → auto-settled on `complete`; > limit → approval to the property's landlord.

**Actors & reach (from `ROLE_API`/`ROLE_PAGES`, serve.py:98–101):** `/api/case-action` — agent, tenant, landlord, trades. `/api/job-action` — trades, agent, landlord. `/api/landlord-action` — landlord, agent. `/api/registration-action` — agent only. `/api/tenant/issue` — tenant, agent. `/api/trades-pool` GET — agent only. `/api/stage` GET — every logged-in role, **server-scoped**; agent receives the whole stage (all threads, all emails).
Audiences: a thread message is seen by a role iff its `to[]` contains that role's key (tenant filter also keeps anything authored by tenant). **There is no `to` value the scopes filter in, so `to:["agent"]` posts an agent-only note — that is the internal-notes channel today.** Two audience facts the design uses: (1) the tenant-audience guard at serve.py:702 can never fire (`to + ["tenant"]` always contains "tenant"), so **a tenant CAN address the landlord directly** (`to:["tenant","landlord"]`) and vice-versa — the landlord always sees the money side via approvals, so the desk's role is to *know about it* (agent sees all threads), not to gate it; design the composer to make tenant→landlord sends visibly "we'll see this too". (2) `/api/landlord-action` is callable by the **agent** role (ROLE_API) — today the desk could sign off its own escalated invoices; keep the affordance off the dashboard and lock the route [NEEDS N-06]. Off-portal parties (renter enquiries, registration applicants) have no login: replies to them can only be recorded on-portal and delivered by phone/email — `NEEDS: outbound email`.

---

## 3. Action matrix

Legend: **[EXISTS]** endpoint works today · **[UI-GAP]** endpoint exists, dashboard shows no affordance · **[NEEDS]** backend primitive missing. Move IDs `C-/J-/R-/P-/A-` are stable; acceptance checklist (§9) reuses them. Payloads are exact `/api/...` bodies. `X` = the tradesperson's exact `company` string from `GET /api/trades-pool`.

### 3.1 CASE actions (one card per case; `id` = numeric case id)

| # | Case state | Move | Endpoint + params | Pre → post | Side-effects (who sees what) |
|---|---|---|---|---|---|
| C-01 | any but `closed` | Read full picture | `GET /api/stage` (agent gets everything incl. `case.thread`, joined `job.case_id`, `approval.job_id`) | view | 15s poll; flash on status flip |
| C-02 | any | Reply to tenant | `POST /api/case-action {id, action:"reply", to:["tenant"], text}` [UI-GAP] | no status change | tenant sees it (to∋tenant); audit `case_reply` |
| C-03 | any | Inform landlord | `POST /api/case-action {id, action:"inform", to:["landlord"], text}` [UI-GAP] | no status change | landlord's case list keeps msgs with to∋landlord; audit `case_inform` |
| C-04 | any | Inform trades on thread | same, `to:["trades"]` [UI-GAP] | — | trades see it iff job touches the case |
| C-05 | any | Internal desk note | `POST /api/case-action {id, action:"reply", to:["agent"], text}` [UI-GAP — hidden channel] | — | only agent scope renders it; audit records text? no — note target only. Convention: prefix `[desk]` |
| C-06 | `dispatched`+ | Add chosen trade to the discussion | `POST /api/case-action {id, action:"add_tradesperson", tradesperson:X}` [UI-GAP] | adds `X` to `case.participants`; posts msg to tenant+trades "X has been added…" | errors 400 if X not in approved pool or already added |
| C-07 | any but `closed` | Close with reason | `POST /api/case-action {id, action:"close", reason}` [EXISTS — today's only button] | → `closed`; msg to all three roles | reason mandatory, kept on `closed_reason` |
| C-08 | `closed` | Reopen | `POST /api/case-action {id, action:"reopen"}` [UI-GAP; closed cards have no UI today] | → **always `new`** (trap: an in-flight job won't re-sync the case until its next event — builder must surface linked-job state, not trust `new`) | msg to tenant |
| C-09 | any | Safety / emergency flag | [NEEDS N-10] — display today: `triage.urgency>=2` ⇒ red lane, never editable | — | desk must be able to overrule a stub triage both ways |
| C-10 | any | Re-triage / correct category·trade | [NEEDS N-10] | — | engine=`stub` cases are keyword guesses; desk fixes the label |
| C-11 | `new` (enquiry) / `reported` (wrong lane) | "This needs a job" (create job on existing case) | [NEEDS N-01b]. Workaround today: `POST /api/tenant/issue {property_id, name:<tenant>, email, message}` (agent role allowed) — creates a *new* case+job, not attached to the old one; close the old one cross-referencing | → old case annotated by hand | audit `case_created` |
| C-12 | `new` (enquiry from renter/landlord with no login) | Answer them | compose reply with C-02 text (record on thread, `to:["tenant","agent"]` so it's kept even though the renter can't log in) **and** phone/email off-portal | — | [NEEDS N-05 outbound email w/ delivery log] |
| C-13 | any | Link/fix property on case | [NEEDS N-03] — intake already nulls unknown ids (v2 `find_prop`), so cases like #490 land `property_id:null` and **nothing can attach a property afterwards** | — | UI must render null-property cases hot ("no property linked — fix here") |
| C-14 | any live | Put case on hold / snooze | [NEEDS N-12] — no hold state; only close-reopen | — | justify: rare; hold ≠ closed because clock is visible |
| C-15 | any but `closed` | Merge duplicate cases | [NEEDS N-11]; today: close one with reason "Duplicate of #N" (C-07) | — | audit keeps the link in the note |

### 3.2 JOB actions (agent lane; `id` = `"job-N"`)

| # | Job state | Move | Endpoint + params | Pre → post | Notes |
|---|---|---|---|---|---|
| J-01 | `open` | Assign directly (work starts without a quote) | `POST /api/job-action {id, action:"assign", tradesperson:X}` [UI-GAP] | → `assigned`; msg to tenant+trades; audit `job_assigned` | pick X from `GET /api/trades-pool`; **assign does NOT credential-check — UI must show X's trades vs `required_trade` and warn red** (gate exists only on trades `accept`) |
| J-02 | `open`/`assigned` | Request a quote | `{id, action:"request_quote", tradesperson:X}` [UI-GAP] | → `quote_requested`, `assigned_to=X`; msg to trades | from `assigned` this doubles as a silent re-target (see J-08) |
| J-03 | `quoted` | Approve a quote | `{id, action:"approve_quote"}` [UI-GAP] | latest `pending` quote → `approved`; → `in_progress`; case syncs `in_progress`; msg tenant+trades | **auto-picks the newest quote — with 2+ quotes this is wrong: NEEDS `quote_index` (N-08)** |
| J-04 | `quoted` | Decline quote (reason) | `{id, action:"decline_quote", reason}` [UI-GAP] | all pending quotes → `declined`; job → `quote_requested`; case back to `dispatched`; msg to trades | reason default "price not right"; free text required by desk voice |
| J-05 | `pending_verification` | Allow booking anyway | `{id, action:"verify_approve"}` [EXISTS in UI] | → `in_progress` for the requester; `override_by:"agent"`; audit `booking_overridden` | security: no role guard server-side [NEEDS N-06] |
| J-06 | `pending_verification` | Send back (choose another trade) | `{id, action:"verify_decline"}` [EXISTS] | → `open`; clears requested_by/gate_reason; audit `booking_declined` | follow with J-01/J-02 immediately, else it rots |
| J-07 | `in_progress` | Pull job back to the board | `{id, action:"release"}` [UI-GAP] | → `open`, `assigned_to:null` | **today: no audit, no message, no case sync (serve.py:532). Dashboard must pair it with C-04+C-05; fix server-side [NEEDS N-07]** |
| J-08 | `assigned` | Reassign to a different trade | two-step today: J-02 to B (retargets + starts quote) **or** if work started, J-07 then J-01 to B. Direct `assign` from `assigned` is rejected [NEEDS N-02a] | as per leg used | always post "moved from A to B" via C-04 |
| J-09 | `in_progress` | Enter invoice by phone (trade is off-grid) | `{id, action:"complete", invoice_pence}` [no role guard today — treat as sanctioned move] | ≤ limit → `paid` (auto-settle, case `resolved`, **no thread msg [NEEDS N-07]**); > limit → `awaiting_approval` + approval created | desk stays human-on-money: read the amount back to the trade, note C-05 |
| J-10 | `in_progress`/`paid` **with** `invoice_pence` | Send invoice to landlord | `{id, action:"send_to_landlord"}` [UI-GAP — this is the "approve quotes / send invoice" move the user is missing] | → `awaiting_approval`, approval `sent_by_agent:true`, case syncs, msg to trades | from `paid` it re-opens landlord sight on an auto-settled bill → **duplicate approvals; guard [NEEDS N-13]** — use C-03 `inform` instead for visibility |
| J-11 | `awaiting_approval` | Chase the landlord | C-03 with T-11; age = now − `approval.requested_at` | no state change | UI shows "waiting 3 days — promised chase fired" (copy on trades page says auto-chase at 3 days; no scheduler exists [NEEDS N-16]) |
| J-12 | `awaiting_approval` | Withdraw / edit the ask | [NEEDS N-09] — approval is one-way | — | needed: cancel pending approval, re-send revised amount |
| J-13 | `rejected` | Renegotiate & re-quote | **DEAD END today.** Escape hatch only: new case via tenant/issue. Proper fix [NEEDS N-02b]: `requote` action → back to `open`/`quote_requested` keeping history | — | landlord reject already created an `agent_task` case — the desk acts on it via C-02/C-03, but can't move the job |
| J-14 | any but `paid`/`rejected` | Cancel a mis-dispatched job | [NEEDS N-01a — CRITICAL] | stray `open` jobs (e.g. wrong "no job needed" verdict) pollute every trade board forever | today only mitigation: leave open / close the case (job still open) |
| J-15 | all | Quote review sheet | render `job.quotes[]` + `approved_quote_pence` from `GET /api/stage` [UI-GAP] | — | never rendered to agent today |

### 3.3 REGISTRATION actions (`id` = `"reg-N"`, agent-only endpoint)

| # | State | Move | Endpoint + params | Post | Notes |
|---|---|---|---|---|---|
| R-01 | `pending` | Approve | `POST /api/registration-action {id, action:"approve", note}` [EXISTS] | → `approved`; trades approve seeds `TRADE_PROFILES` + joins `/api/trades-pool` | confirmation sheet + toast + 10s-undo client replay (audit has no undo [NEEDS N-15]) |
| R-02 | `pending` | Reject with note | same, `action:"reject"` [EXISTS] | → `rejected` | note feeds T-15 |
| R-03 | decided | Undo / re-decide | same endpoint again works **by accident** (no pending guard) | status flips | formalise + warn: revoking a trade must check `jobs.assigned_to` in-flight [NEEDS N-04] |
| R-04 | decided | See the history | filter `status!=="pending"` (agent.html today already lists Decided) | — | show `actioned_at` + `decision_note` — the "when/why did I vet them" evidence |
| R-05 | `approved` (trades) | Suspend / remove from pool | [NEEDS N-04] — TRADE_PROFILES is in-memory, gone on restart anyway | — | CRITICAL: pool durability |
| R-06 | `approved` (landlord) | Provision: login + first property | **DEAD END — approval does nothing today** [NEEDS N-03+N-04] | — | the whole landlord-onboarding promise stops here |
| R-07 | any | Tell the applicant | **No in-portal channel — registrants have no account.** [NEEDS N-05] | — | interim: desk emails off-portal, records T-14/T-15 text via C-05 note |

### 3.4 PROPERTY actions

| # | State | Move | Endpoint | Notes |
|---|---|---|---|---|
| P-01 | let / vacant | View board | `GET /api/stage` → `properties[]`, join open cases/jobs per `property_id` [UI-GAP — today shows rent/beds only, no activity roll-up] | "4 Holloway Yard — 2 open cases, nothing pending" |
| P-02 | any | Create / edit property, assign landlord & tenant, set rent | **[NEEDS N-03 — CRITICAL: no mutation endpoint exists at all]** | blocks R-06 and C-13; without it the portfolio is frozen at seed data |
| P-03 | any | Compliance record (CP12/EPC/deposit) with expiry | [NEEDS N-14] | the desk's headline fear; not in any state today |

### 3.5 APPROVAL / money actions (agent as conductor, not decider)

| # | State | Move | Endpoint | Notes |
|---|---|---|---|---|
| A-01 | `pending` | Watch list "Money — on the landlord" | join `approvals[pending]` to jobs/properties [UI-GAP: tiles exist, no per-approval card with evidence] | evidence block already in data — render it |
| A-02 | `pending` | Chase | C-03 + T-11 | SLA: chase at day 3 (promised by trades-page copy) |
| A-03 | `approved` | Outcome to all | automatic msg exists (landlord-action posts) | case → `resolved` |
| A-04 | `rejected` | Receive consequence | agent_task case arrives [EXISTS] → J-13 dead-end | desk's move list: tell trades (C-04/T-10), tell tenant (C-02), then needs N-02b to re-quote |
| A-05 | global | Standing authority per landlord | `stage.authority` global only; landlord's "Change limit" is a stub toast | [NEEDS N-03b per-landlord limit + agent editor] |

## 4. Dead ends today (the pain list — quoted from the shipped surface)

1. **"for each case you only have the option to close it"** — true: `agent.html` Cases renders exactly one action (`Close case` + reason input); reply/inform/add_tradesperson/reopen have endpoints and **no buttons**. The user's complaint is a UI truth.
2. **The agent cannot converse**: `case.thread` is in the agent's `/api/stage` payload but agent.html never renders it. Messages sent by anyone are invisible on the desk.
3. **All quote/invoice choreography invisible**: assign, request_quote, approve_quote, decline_quote, send_to_landlord, release — zero affordances. Jobs tab shows only verify buttons, and lanes for open/in_progress/awaiting/paid/rejected without actions.
4. `approve_quote` **cannot choose among quotes** (picks newest pending); `decline_quote` declines **all** pending quotes at once.
5. **`rejected` job = terminal.** Landlord decline creates an agent_task but the job itself has no legal move (`assign` won't accept `rejected`; `complete` needs `in_progress`). Renegotiation means a fake new case.
6. **No job cancel** — a maintenance mis-triage mints an `open` job that lives on every trades board forever (closing the case doesn't stop it).
7. `release` writes **no audit entry, no thread message, no case sync** (serve.py:532–534) — invisible undo.
8. `complete` auto-settle branch posts **no thread message** — tenant/landlord learn about £-movement only via status label.
9. **Reopen resets to `new` regardless of linked-job reality** — a mid-flight job leaves its case looking untouched.
10. **Registration approval notifies nobody** (registrants have no login, no email path) and **landlord approval provisions nothing** — no account, no property. Approved trades profiles die on restart (in-memory).
11. **Properties are immutable** — cannot onboard the landlord just approved; cannot record which tenant moved out; the "stage" itself can't be set.
12. Enquiry cases from renters have no reply channel — `to:["tenant"]` reaches only logged-in tenants matched by **display-name string**.
13. Role enforcement gaps: `accept`, `complete`, `release`, `verify_approve`, `verify_decline` on `/api/job-action` and **both decisions** on `/api/landlord-action` have no per-branch role guard (route allows trades/agent/landlord) — a landlord session could complete a job or, worse, the agent could approve its own escalated invoice; the quote/assign branches *are* guarded (`self.user["role"]=="agent"`). `send_to_landlord` from `paid` duplicates an approval.
14. No pause/snooze, no safety flag, no re-triage override, no merge, no outbound notifications, no chase scheduler despite copy promising one ("we chase automatically at 3 days" — nothing chases).

## 5. Handoffs & SLAs

### Into the desk (trigger → artifact on the desk → SLA to acknowledge)
| Trigger | From | Lands as | Ack SLA | Chase if missed |
|---|---|---|---|---|
| Tenant report (`/api/tenant/issue`) | tenant | case `reported`/`dispatched` + job `open` | urgency 2: 1 h during 8–20; urgency ≤1: 1 working day | red lane + browser badge (poll 15s exists in UI) |
| Public enquiry (`/api/public`, `/api/enquiry`) | renter/landlord/trade | case `new` type `enquiry` | 1 working day | phone list from `case.email` |
| Trade takes a job (accept) | trades | job `in_progress` + msg to tenant | same working day glance | flash-once already; no action |
| Credential-blocked booking | trades | job `pending_verification` | 4 h (blocks a visit) | J-05/J-06 |
| Quote submitted (submit_quote) | trades | job `quoted` + `quotes[]` append | 1 working day | J-03/J-04 |
| Trade finishes + invoices (complete) | trades | job `paid` (< limit) or `awaiting_approval` + approval | same day sanity-check amount vs quote | J-09 exists as fallback for phone invoice |
| Landlord decision (`/api/landlord-action`) | landlord | approval decided; job `paid`/`rejected`; case `resolved`/`declined`; reject spawns agent_task `new` | agent_task answered in 1 working day | A-04 loop |
| New registration (public form) | applicant | reg `pending` | 2 working days (it gates their earnings) | R-01/R-02 |
| Duplicate report on same property | tenant | second case | merge within 1 day | C-15 |

### Out of the desk (artifact handed over → expected return)
| Move | To | Artifact | Expected back | SLA |
|---|---|---|---|---|
| `assign` (J-01) | trades | job `assigned` + thread msg | start, or hand-back | visit arranged in 1 working day |
| `request_quote` (J-02) | trades | job `quote_requested` + T-04 | `submit_quote` | **quote back within 2 working days**; chase T-12 at day 3; then re-target J-08 |
| `approve_quote` (J-03) | trades+tenant | `in_progress` + T-05 | `complete` + invoice | per quote's promised date, default 5 working days |
| `send_to_landlord` (J-10) / auto-escalation | landlord | approval + evidence + T-08 | decide | **3 working days**, then A-02 chase; 7 days escalate to phone |
| C-06 add to discussion | trades | participant + thread access | access arranged with tenant | 1 working day |
| Emergency with safety ≥0.5 | (human rule) | phone first, thread second | call logged as C-05 note | 30 min |

## 6. Message templates (thread copy → `post_msg` payloads)

Voice: calm agency, plain English, concrete next step + when. `to` arrays are exact. Templates become prefills in the composer, editable before send. Office: 0121 496 0123 · office@stage.example.

- **T-01** acknowledge, emergency → `to:["tenant"]`: "Thanks for telling us, {name}. We're treating the {item} as an emergency — a tradesperson will be on the board for a taker today and you'll hear from us within 4 hours. If it gets worse or you feel unsafe, call the office on 0121 496 0123 straight away."
- **T-02** acknowledge, routine → `to:["tenant"]`: "Logged as case #{id}. We'll get the right person onto it — usually sorted within a few days. We'll message you here before anyone visits."
- **T-03** dispatch announced to tenant → `to:["tenant"]`: "Good news — {X} is now handling this. They'll arrange a time that suits you. If they don't reach you within a day, tell us and we'll chase."
- **T-04** quote request → `to:["trades"]`: "Job {job} at {property}: {short fault}. We need a quote before work starts — price and note back within two working days please. {X}, can you take this one?"
- **T-05** quote approved → `to:["tenant","trades"]`: "{X}'s quote of £{amount} is approved. Work can go ahead — {X}, please arrange access with {tenant}. We'll ask for the invoice here when it's done."
- **T-06** quote declined → `to:["trades"]`: "We can't sign off £{amount} — {reason}. Please re-quote with a lower price or a different scope, or tell us why it can't come down and we'll take it to the landlord."
- **T-07** heads-up to landlord before escalation → `to:["landlord"]`: "Heads-up on {property}: {X} has finished the {fault} work and the invoice came in at £{amount} — above your £{limit} standing authority, so it's yours to sign off rather than ours. We'll send it across shortly with the full history."
- **T-08** escalation cover note → `to:["landlord"]`: "Sign-off request for {property} — £{amount}. Reported by the tenant {reported_date}, done by {X} (credentials verified with us) {completed_date}, job ref {job}. Decline it and tell us why; we'll take it from there."
- **T-09** outcome to tenant (post payment) → `to:["tenant"]`: "All settled and paid — thank you for bearing with us on this one. If anything's still not right, send us a fresh report any time."
- **T-10** landlord declined → trades → `to:["trades"]`: "The landlord has declined the £{amount} invoice — their words: '{reason}'. Hold fire on invoicing; let's look at the options (reduced scope, second visit, itemised breakdown) and we'll take the best one back to them."
- **T-11** chase landlord → `to:["landlord"]`: "Gentle nudge: the £{amount} sign-off for {property} has been waiting {days} days. Approve or decline either way — silence is the only outcome we can't work with."
- **T-12** chase trades quote → `to:["trades"]`: "Just checking on job {job} — has the quote slipped? If it's not your work, say so and we'll pass it to someone else; no hard feelings."
- **T-13** closing note → `to:["tenant","landlord","trades"]`: "Closing this case: {reason}. Everything stays on the record here, and reopening is one message away if it comes back."
- **T-14** registration approved (email copy — off-portal today, [NEEDS N-05]) : "Welcome to the Stage network, {name}. You're approved for {trades} work with us and you'll see jobs on the board as soon as your account is set up by the office."
- **T-15** registration rejected (email copy): "Thanks for applying to work with us. We can't approve you for our list yet — {note}. Reply to this email and we'll talk about what's missing."
- **T-16** internal note convention → `to:["agent"]`: "[desk] {text}" — e.g. "[desk] Called tenant 10:05, engineer booked for 9–11am Thu, access with neighbour."

## 7. Undo · Reassign · Dispute · Pause (per object, every state)

**Undo.** No endpoint supports it; every reversible move gets a **client-side 10s-undo** that replays the exact inverse (table below). Irreversible-by-design: audit entries (append-only), approvals decided (one-shot by rule — dispute instead, §7.3), messages sent (post a correction instead).

| Move | Inverse (endpoint) | Honest limit |
|---|---|---|
| C-07 close | C-08 reopen (→ `new`; UI must re-show linked job state) | sub-state lost until next job event — builder note |
| J-01/J-02 assign/quote-request | J-07 release works **only** post-`in_progress`; from `assigned`/`quote_requested` re-`assign` someone else (J-08 leg 1) | original quote_requested target not restorable |
| J-03 approve_quote | none — approve_quote consumes the quote; **dispute path**: J-04 on the *next* quote or re-request (state already `in_progress` so J-04 is dead) ⇒ genuinely irreversible: confirmation sheet must force a read-back |
| J-04 decline_quote | trade re-submits (submit_quote) | quotes stay `declined` (history preserved) |
| J-05 verify_approve | J-07 release | |
| R-01/R-02 reg decision | R-03 re-decide | TRADE_PROFILES not cleaned — flag [NEEDS N-04] |

**Reassign.** Job `open`: J-01/J-02 to anyone in pool. Job `assigned` (no work yet): J-02 to B retargets (documented trick) or after work: J-07 then J-01/J-02 to B. Job `quoted` (A quoted, give to B): J-01/J-02 to B is allowed and **leaves A's quote `pending` forever** — `approve_quote` picks the *newest* pending, so B's quote wins the race only by timestamp, not by the desk's choice, and A never learns their quote was superseded (decline is all-or-nothing). UI on retarget must offer "decline A's open quotes" (J-04 first) and always post "moved from {A} to {B}" via C-04 + T-03 variant. Job `pending_verification`: J-01 to a credentialed trade directly. Property→different landlord, case→different property: [NEEDS N-03].

**Dispute.** (a) *Trade disputes quote decline*: desk re-reads, either J-02 back to same trade (re-quote) or informs landlord early via T-07. (b) *Landlord declines invoice*: agent_task spawns; desk negotiates T-10, then needs **N-02b `requote`** — until that lands, workaround = create companion job via tenant/issue and cross-reference both cases with notes (ugly, documented). (c) *Tenant disputes "done"*: reopen adjacent case (C-08) or fresh report; job `paid` is money-settled — new work = new job, never mutate the paid one. (d) *Desk mis-settles ≤limit invoice itself*: cannot un-pay — record T-16 note + chase the trade for credit off-portal [NEEDS N-09 refund/correction primitive].

**Pause.** Nothing has a hold state. Today's honest substitutes: `dispatched`+ no trade chosen = leave `open` (visible on board, correct); awaiting access with tenant = C-02 to tenant + T-16 note, job stays `in_progress` (UI shows "waiting — {days} silent" aging badge client-side). Proper `hold` on case+job with reason & auto-visibility: [NEEDS N-12, NICE].

## 8. Screens this implies (agent.html rebuild — structure, not visuals)

1. **Today board (Overview)** — keep tiles, make each a filtered deep-link; add lanes: emergencies (urgency≥2, open) · jobs unassigned > 1 day · quotes > 2 days unanswered · approvals waiting > 3 days · regs pending. Authority line stays.
2. **Cases (the case book)** — every case, sorted emergencies-first (client sort exists); each card = header (id·type·badge·property line·reporter+email) + triage strip + **full thread timeline** (render `c.thread` in chronological order, audience chips) + **composer**: template dropdown T-01…T-13 + `to` chips (Tenant/Landlord/Trades/Internal) → case-action reply. Action bar: `Assign trade ▸` (pool picker w/ credentials vs `required_trade`), `Request quote ▸`, `Add to discussion`, `Create job` [NEEDS], `Flag safety` [NEEDS], `Close`, `Reopen` (closed filter), filter chips by state/property.
3. **Job board** — lanes open / assigned / quote_requested / **quoted (review sheet: quotes table + approve-this-one [N-08] + decline-with-reason)** / in_progress (aging, release, enter-invoice-by-phone, **send to landlord**) / pending_verification (today's buttons + who & why) / awaiting_approval (approval card w/ evidence + chase T-11) / paid & rejected (history + dispute notes). Job drawer = thread for its case.
4. **Money** — approvals pending (evidence-first cards: trade, dates, amount vs limit, case link, send T-08 as one action), waiting-days aging bar, settled-this-month sum, per-landlord limit editor [NEEDS].
5. **Registrations** — pending queue with structured vetting sheet (gas-safe #, trades, insurance expiry from reg fields), confirmation modal, decided-history list w/ re-decide, email copy T-14/T-15 [NEEDS N-05].
6. **Properties** — per property: open cases, open jobs, last 5 closed, compliance strip [NEEDS], add/edit [NEEDS].
7. **Trades network** — pool from `GET /api/trades-pool`, per-trade live jobs, response stats (client-side from timestamps).
8. Global: 15s poll kept; emergency tile badge + sound off toggle; every action → toast + 10s undo where inverse exists (§7); all user text through `esc()` (XSS history).

## 9. NEEDS: backend primitives (one pass, with the dashboard)

| ID | Primitive | Priority |
|---|---|---|
| N-01a | `job-action: cancel` (agent; any state but paid/rejected; reason required; syncs case note, audits, messages trades) | **CRITICAL** |
| N-01b | `case-action: create_job` (agent; {id} → job on existing case, case→dispatched) | **CRITICAL** |
| N-02a | allow `assign` from `assigned` (true reassign w/ message "moved from A to B") | **CRITICAL** |
| N-02b | `job-action: requote` (agent; `rejected` → `quote_requested`/`open`, keeps history + reason) | **CRITICAL** |
| N-03 | Properties CRUD: create/edit property (landlord, tenant, rent, address); `case-action: link_property`; validate `property_id` at intake | **CRITICAL** |
| N-03b | Per-landlord standing authority + agent editor endpoint | NICE |
| N-04 | Registration lifecycle: decide-guard on `registration-action` + explicit `revoke` that clears TRADE_PROFILES/pool and warns if jobs in flight; pool persisted to stage.json | **CRITICAL** |
| N-05 | Outbound email (registration decisions, enquiry replies) with delivery logged to audit | **CRITICAL** |
| N-06 | Per-branch role enforcement on `/api/job-action` (`accept`/`complete`/`release` ⇒ assigned-or-requesting trade; `verify_approve`/`verify_decline` ⇒ agent; `complete` by agent requires `on_behalf` audit) and `/api/landlord-action` ⇒ landlord only (agent must never sign off its own escalation); the assign/quote branches already check `role=="agent"` — keep | **CRITICAL** (security) |
| N-07 | Side-effect parity: `release` + auto-settled `complete` must audit, `sync_case`, and post_msg; reopen must restore prior linked-state-aware status | **CRITICAL** |
| N-08 | `approve_quote {quote_index}` + per-quote decline | **CRITICAL** |
| N-09 | Approval lifecycle: agent `withdraw` pending approval; refund/correction primitive for mis-settled payments | NICE |
| N-10 | `case-action: retriage` (agent; overrides category/trade/urgency/safety, records before/after in audit) | **CRITICAL** |
| N-11 | `case-action: merge` (duplicate into another case, threads joined) | NICE |
| N-12 | Hold/pause on case & job with reason + aging visible, auto-unhold date | NICE |
| N-13 | Guard `send_to_landlord` from `paid` when an approval already exists (409) | NICE |
| N-14 | Compliance records per property (CP12/EPC/deposit + expiry, surfaced on Today board) | NICE |
| N-15 | Undo API (`audit_action: revert` marker) — until then client-side inverse replay only | NICE |
| N-16 | Chase scheduler (quotes 2 wd, approvals 3 wd) — client-side reminder flags meanwhile | NICE |
| N-17 | Formalise agent-only thread audience: accept `to:["agent"]` as first-class "desk note" (documented, or add `internal:true`) | NICE |

## 10. Acceptance checklist (one line per move; QA pass)

- C-01: desk sees case #N thread incl. every prior reply within 15s of it being sent.
- C-02: desk replies "T-02" to tenant → message renders on /tenant under the case within 20s; audit shows `case_reply`.
- C-03: inform landlord → text visible on /landlord's case thread only if `to` included landlord.
- C-05: internal note appears on agent thread and nowhere else (check tenant/landlord/trades scoped `/api/stage`).
- C-06: add R. Doyle → participant list grows, tenant sees "has been added to this discussion", second add → 400 toast.
- C-07/C-08: close requires reason; closed cases filterable; reopen returns card to queue with linked-job chip truthful.
- J-01: assign X → badge `assigned`, thread msg both audiences, X's board shows it; assigning non-pool name → clear 400.
- J-02→J-15: request quote from A → A's board asks quote; A submits → desk's quoted lane shows amount+note; decline with reason → A told, job quote_requested; re-target quoted job from A to B → desk UI surfaces A's still-pending quote and offers decline-then-request; approving must not hide *which* quote was chosen (N-08 — until it lands, the quoted sheet shows the timestamp of the auto-chosen newest quote on the confirm button).
- J-05/J-06: gate buttons behave as shipped today (regression).
- J-07: release → job open + thread note + audit line (asserts N-07 once backend lands; pre-landing assert desk posted the message itself).
- J-09: phone invoice ≤ £150 → `paid`, tenant+landlord see T-09 within the thread (asserts N-07).
- J-10: invoice > limit created without escalation → desk "send to landlord" → approval w/ evidence appears on /landlord; T-07/T-08 recorded.
- J-11: approval older than 3 days renders chase affordance pre-filled T-11; sending logs `case_inform`.
- J-13/A-04: landlord reject → agent_task case on desk; desk executes T-10+C-02; requote blocked by N-02b — assert task exists.
- R-01…R-05: approve reg → appears in trades-pool picker; reject → history list shows note+date; re-decide warning shown.
- R-06/P-02: property create blocked until N-03 — assert UI shows "not yet available" and never a silent dead button.
- Every state-changing click: toast + (where §7 lists an inverse) 10s undo that leaves stage identical to before (diff two `/api/stage` GETs).
- XSS: type `<img src=x onerror=…>` as a case message/registration detail → renders escaped on every lane of the rebuilt desk.
- Mobile: all lanes reachable at 390px without horizontal nav clipping (tabs wrap), all action targets ≥44px.
