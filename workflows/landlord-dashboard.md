# Workflow design — LANDLORD dashboard
**Role lens:** T. Blackwood — owner of 16 Parkside Mews (£2,400/mo, let) and 5 Holloway Yard (£1,800/mo, vacant). Full-time job elsewhere; checks the portal on the sofa twice a month, on a phone. Hired the agency precisely so she does *not* think about boilers — but she does think about the £150 standing authority and whether anyone is actually guarding her money.
**Surface today:** `stage-clone/landlord.html` (read-mostly) + `/api/landlord-action` + `/api/case-action` + scoped `/api/stage` (`serve.py:221-231`). Server live at 127.0.0.1:8901 (verified, read-only GETs).
**Companion docs:** `audit/landlord-audit.md` (pain evidence, quoted below), `audit/CONSOLIDATED-AUDIT.md` (build order P0-P3).

## Day in the life (5 lines max)
1. Twice a month, evening, phone: one-handed scan — "does anything need my signature, and did anyone spend my money since I last looked?"
2. If an approval waits, she has 90 seconds of attention: amount, who did the work, proof it happened, tap a button, write a reason only if declining.
3. She wants the £150 rule to be *hers*: see what auto-settled under it, nudge the number when a property changes, know a surprise under-limit spend can be queried, not swallowed.
4. She plans life (October abroad) and needs the portal to hold jobs still while she's away, without a phone call to the office.
5. End of month she reconciles: rent in, repairs out, what she approved, what she didn't — today she cannot reconcile a penny (landlord-audit §3).

**Frequency order for the dashboard:** decisions (rare, hot) > money glance (every visit) > thread replies (occasional) > settings (monthly at most, critical when wanted). Rare-but-critical lives deeper on screen, never absent (anti-pattern guard from doctrine).

## Objects & states today (from code)
| Object | States (verbatim) | Landlord's reach today | Code ref |
|---|---|---|---|
| Approval | `pending` → `approved` / `rejected` (reason required on reject) | approve/reject with reason; card then **vanishes** — no decided view on `/landlord` | `serve.py:647-690`, `landlord.html:74-92` |
| Job | `open, assigned, quote_requested, quoted, in_progress, pending_verification, awaiting_approval, paid, rejected` | read-only one-liner `↳ job-x: status · by X · £Y` under the case; landlord is in `ROLE_API["/api/job-action"]` but has **no designed move** there | `serve.py:99, 497-644`, `landlord.html:126-131` |
| Case | `new/reported, dispatched, quoted, in_progress, awaiting_approval, resolved, declined, closed` | scoped list with tenant's original message; **thread array is in the landlord payload but never rendered**; no reply box, yet `/api/case-action reply` accepts landlord | `serve.py:221-231, 693-735` |
| Thread msg | `{author, role, text, to[], at}` | landlord sees only messages with `"landlord" in to` | `serve.py:226, 306-315` |
| Standing authority | single global `stage.authority.standing_limit_pence` (shared by ALL landlords) | read-only; "Change limit" button = toast "ring the office" | `serve.py:609`, `landlord.html:105, 143` |
| Statement | not an object — computed client-side: rent-in (asking rent), paid total, awaiting total | aggregates only; fineprint admits "Receipts, management-fee breakdown and monthly digests are on the roadmap" | `landlord.html:94-107` |
| Property | `{id,title,area,beds,rent_pence? (rent),landlord,tenant}` | read-only card | `landlord.html:118-122` |
| Audit log | entries incl. `invoice_auto_settled` | **not in landlord scoped payload at all** | `serve.py:227-231` |

Evidence v2 already landed (do not re-design): approval card now names tradesperson + "credentials verified at sign-up", shows reported/completed dates, job ref, and the £-limit fineprint (`landlord.html:81-87`); reject-with-reason creates an agent task (`serve.py:676-686`); agent dashboard now sees "invoices waiting on landlord" (`agent.html:111,156-158`).

## Action matrix (object × state → moves)

16 designed moves, M1–M16. "Exists" = works today; "UI" = backend already
accepts it, only the surface is missing; "NEW" = needs a primitive (§9).
Every cell lists **post:** (state after), **say:** (message template §8),
**note:** (audit/notify side-effects). `landlord==me` and
`property_id ∈ my props` are implicit preconditions on every row (server
already scopes reads; writes must gain the same check — see N-1).

### Approval object
| State | Landlord moves | pre / post / side-effects |
|---|---|---|
| `pending` | **M1 Approve** (Exists) | pre: `status==pending`. post: approval `approved`, job→`paid`+`paid_at`, case→`resolved`; thread post to (tenant,trades,landlord) T2a; audit `invoice_approved`. |
| | **M2 Decline + reason** (Exists) | pre: reason non-empty (server already 400s without, `serve.py:659`). post: job→`rejected`, case→`declined`, agent_task case auto-created; thread T2b; audit `invoice_rejected`. |
| | **M3 Ask for more proof** (NEW N-3) | pre: `pending`. post: approval gains `evidence_request{at,what,text}`, stays pending with amber "waiting on proof" badge + SLA clock; thread post T3 to landlord+agent; audit `evidence_requested`. Never blocks the job beyond the hold it already is. |
| | **M4 Reply in thread** (UI) | `/api/case-action reply` already accepts landlord (`serve.py:101`); landlord.html has no box. Audience picker: tenant / trades / both. T4. |
| `approved` (was >£limit) | **M5 View decision history** (UI) | data already in scoped payload (`approvals` carries decided rows) — render it. Read-only + M4. |
| `rejected` | **M4 Reply**; "changed my mind" = reply T5 → agent re-presents a quote; decision itself is final (see Undo §6). | |

### Job object, landlord lens (job on my property)
| Job state | Landlord moves | notes |
|---|---|---|
| `open` / `assigned` / `quote_requested` | **M10 Pause** (NEW N-5), M4 reply | pause carries `{until?, reason}`; T6 posts to tenant+trades; agent sees flag on their board. |
| `quoted` | **M6 Ask for a second quote** (NEW N-4): posts T7, creates agent task, job stays `quoted`; **M10 Pause**; M4. |
| `in_progress` | M4 reply only. **Pause refused in one line:** work is on site and money may be mid-commitment — stopping live work is an agency phone call, not a sofa tap; the agent's own pause covers it. (Deliberate absence, doctrine §4.) |
| `pending_verification` | none — this gate is law/safety ("stays human" = the *agent*, product rule). DEAD END declared, §4 D-7. |
| `awaiting_approval` | handled via the approval card (M1–M4); **M10 Pause allowed** (stops nothing financial, only signals "hold settling" — job flag only; approval flow unaffected). |
| `paid` under limit | **M7 Dispute this settlement** (NEW N-6) + **M8 live with it / withdraw** (part of N-6 lifecycle). Also M5: every `paid` job must appear in history & statement (M13). |
| `paid` after approval | M4 reply; dispute path also available (owner may dispute even a job she waved through — honesty beats finality). |
| `rejected` | M4 reply ("good catch"), view in history. No landlord re-open — that's the agent's `request_quote`/reassign. |
| any | **M11 Unpause** (NEW N-5), or auto-lift at `until` date: system posts T8 to agent board + thread note; job does NOT auto-resume itself (agent re-dispatches — a landlord's return is information, not an action that hires people). |

### Case & thread (my properties)
| Case state | Landlord moves | notes |
|---|---|---|
| any open state | **M4 Reply** (UI, above); read scoped thread (fix: landlord.html never renders `c.thread` — D-2); **M9 Suggest a tradesperson** (UI via existing `add_tradesperson`, `serve.py:709-718` — landlord may only suggest *already-approved* firms; the vetting gate stays with the agent, which is the right shape). |
| `resolved` | M4 ("thank you, sorted"), view money trail; **never auto-closes from landlord side** — closing stays agent's record-keeping move. |
| `declined` / `closed` | read + M4 only. **Close/reopen are NOT landlord moves** — reachable today via `/api/case-action` because ROLE_API lets landlord in but the handler has no role guard (`serve.py:719-731`); NEEDS N-1b server guard to remove the accident. |
| `new`/`reported`/`dispatched`/`quoted`/`in_progress`/`awaiting_approval` | M4 + M10 (via the job) + view. No status edits: the case spine is the agent's; landlord edits *inputs to* it (money rules, pauses, evidence demands, words). |

### Authority, settings, money
| Object state | Landlord moves | notes |
|---|---|---|
| Standing limit (currently global £150) | **M12 Change my limit** (NEW N-1): per-landlord, integer pounds £50–£500, applies to work completed from the moment of change forward (audit note `limit_changed`, T9 confirmation). Retroactive application is meaningless and dangerous; say so in the copy. |
| Notifications | **M13 Set notification prefs** (NEW N-2): `chase_after_hours` (24/48/none), `notify_on_auto_settle` (on/off, default on), `monthly_digest` (on/off, default on). Portal-first (badge + "since your last visit" strip — D-4 fix); email is NICE-1. |
| Statement | **M14 View month** (UI+compute): rows from `jobs` already in scoped payload — date, property, trade, what, amount, mode badge (auto / you approved / declined / queried). **M15 Download CSV** (NEW N-7). **M16 Ask about a row** = M4 reply seeded with job ref. Management fee / rent-collected rows are honest blanks until N-8 (rent ledger) exists — show "not yet tracked" rather than fake it. |

## Dead ends today
Quoted from the live surface (`landlord.html`) and the audit's live findings.

| # | Dead end | Evidence (today) | Fixed by |
|---|---|---|---|
| D-1 | **"Change limit" is a lie.** The button fires a toast: *"Limit changes are set up with your agent — ring the office on 0121 496 0123…"* (`landlord.html:143`). No endpoint, no editor; the £150 even lives in a global `stage.authority` shared across all landlords. | landlord-audit §2: "copy-only control… tradesperson is told my limit more clearly than I am given control over it" | N-1, M12 |
| D-2 | **The thread exists but is invisible.** Scoped payload carries landlord-addressed `c.thread` messages (`serve.py:226`); `landlord.html` renders only a derived one-liner per job (`:126-131`) and **no reply box**, though the API already accepts landlord `reply` (`:101`). Landlord can speak but can neither hear properly nor answer from the UI. | audit §5: "the human loop — me → agent → tenant/trades — is broken at three of four hops" | UI pass §7, M4 |
| D-3 | **Decisions vanish.** After Approve/Reject the card disappears into the same empty state as "never anything to do" — *"Nothing needs your signature…"* — with no history, no receipt (audit Task 1 & 5, verified live). | data already present in scoped `approvals` | M5, §7 S1 |
| D-4 | **Under-limit money is silent.** `invoice_auto_settled` is written to `audit_log`, which is **not in the landlord payload at all** (`serve.py:227-231`); the £45 radiator paid in front of her "appears nowhere on my page" (audit §2). Statement shows a count only, no rows, no dispute route. | | N-6, M7/M14 |
| D-5 | **No dispute route.** Grep: no `dispute` anywhere in code or UI. Audit wishlist #10: "no way to dispute a paid under-limit job". | | N-6 |
| D-6 | **No pause / away-window.** No `paused` field, no route; "not while I'm abroad in October" is unrepresentable — today it's a phone call to the office, and the tenant finds out by an unexpected knock. | | N-5 |
| D-7 | **`pending_verification` is a black hole for the landlord** (deliberate — safety gate is the agent's) **but note the API accident in the other direction:** landlord is whitelisted on `/api/job-action` and `verify_approve`/`verify_decline` have **no role check** in the handler (`serve.py:520-531`), so a landlord (or her browser console) can approve a cert-blocked booking. Must be locked, not celebrated. Same class: `close`/`reopen` reachable by landlord (`:719-731`). | consolidated audit 0.5 "auth is theatre" | N-1b |
| D-8 | **Statement is three aggregates** and admits it: *"Receipts, management-fee breakdown and monthly digests are on the roadmap"* (`landlord.html:107`). Rent shown is asking rent, not collected rent; no fees exist in the data model at all. | audit §3 "headline finding" | M14/N-7 (repairs now) + N-8 (ledger, later) |
| D-9 | **No notification settings** — grep for `notif|alert|threshold` hits only a JS `alert()` on trades (audit §2). For a twice-a-month visitor, a stale pending approval is invisible unless she happens to sit down. | | N-2, M13 |

## Handoffs & SLAs
| Direction | Trigger → artifact | SLA (proposed) | Chase path |
|---|---|---|---|
| agent/system → landlord | job completes over limit (or agent `send_to_landlord`) → approval card + T1 | decide within **2 working days** | 24h portal nudge (T-CH, per `chase_after_hours`); 5 days → agent phones; **never auto-approve** — money decisions stay human, silence is not consent |
| landlord → agent | M2 decline → agent_task case (exists, `serve.py:676-686`) | agent acknowledges to tenant/trades within **1 working day** (audit §5: tenant was *never told*) | landlord's M4 reply on the case nudges the agent board |
| landlord → agent | M3 evidence request / M6 second quote / M7 dispute → agent task with 24h response target, dispute resolved ≤ **5 working days** with T10/T11 outcome | auto-flag to agent "overdue" list |
| landlord → trades+tenant | M10 pause (+ `until`) → T6 posts to both, job gated | trades must not visit while paused (server gate N-5c) | agent override needs recorded reason; landlord gets T12 if overridden |
| system → landlord | monthly close (1st) → statement row-set + digest T13 | landlord "query this row" within 14 days = M16/M7 | after 14 days rows marked "settled & unqueried" (advisory copy only, dispute technically stays open — never a hard lock on your own money talk) |
| landlord → agent | M12 limit change | effective immediately for future completions; agent may call if a job already in flight will be caught differently | audit trail visible on agent board |

## Undo / reassign / dispute / pause
- **Undo.** No decision hard-reverts (money state machine is append-only, per README rule 5): M1 approve → regretted = **dispute the settlement** (M7) on that row, which is the honest path; M2 decline → reply T5, agent re-quotes. Limit change M12 is instantly undoable (set it back; forward-only semantics make that safe). Pause M10 is fully reversible (M11). Replies M4: edit-in-place is NICE-3; the thread is a record, deletion is not offered.
- **Reassign.** Landlord never reassigns people — that's the agent's `assign`/`request_quote` (`serve.py:536-553`, agent-guarded, correctly). Landlord's expression of preference is M9 (suggest, only within the approved pool) and M4. Justified by the product rule: vetting is law/safety, stays with the human desk.
- **Dispute (M7/M8) — the missing object.** `dispute = {id, job_id, property_id, landlord, amount_pence, reason, opened_at, status: open→agent_review→upheld|not_upheld, outcome_note, resolved_at}`. Semantics: money is NOT clawed back; the statement row turns amber "queried — under review"; upheld ⇒ agent records credit on next statement (T10); not_upheld ⇒ evidence summary + T11 and the landlord keeps a reply route, never a dead end. Every dispute mirrors to the agent as a task case (same mechanism declines already use). Opening requires a reason (symmetry with reject-requires-reason, `serve.py:659`).
- **Pause (M10/M11).** `job.paused = {by, reason, until|null, at}` — a **flag, not a new status** (doctrine: extend, don't fork the state machine; every existing surface keeps reading `status`). Server gate: `/api/job-action` mutations on a paused job return 423 + T-copy unless actor is the pausing landlord (unpause) or agent (override with recorded reason → landlord gets T12). Allowed on `open/assigned/quote_requested/quoted/awaiting_approval`; refused on `in_progress` (see matrix). `until` expiry posts T8 to the agent board — resume is a human act, not a cron hire. Vacant property (5 Holloway Yard) is the natural sibling: a property-level default pause for lettings work is NICE-4.

## Screens this implies
One dashboard, four sections, ordered by how often she uses them. Mobile-first (390px renders fine today — a delight the audit credits; don't lose it).

- **S-1 Today (home, decision-first).** Pending approvals with full evidence table (exists, keep) + "you asked for proof" amber state + SLA countdown; *Decided* sub-list (approved/declined rows with amount, date, outcome — kills D-3); "Since your last visit" strip: n under-limit settlements with dispute links (kills D-4); chase banner per prefs.
- **S-2 Money.** Month selector; statement table M14 (row: date · property · trade · what · £ · mode badge · [Ask about this] [Query this settlement]); totals strip (current aggregates promoted to row-level truth); [Download CSV]; limit card with real inline editor (replaces the phone-the-office toast) + "what this means" fineprint (reuse the audit's beloved sentence pattern: *"up to £X settles without bothering you — that's why the little jobs never reach you"*); notification prefs card.
- **S-3 Properties & repairs.** Case cards now rendering the scoped `thread` as bubbles with author+time, plus reply box with audience picker (tenant / trades / both — default: both, never agent-only since agent sees everything anyway); job line with pause pill + [Park until… date + reason] / [Resume]; suggest-a-trade picker (approved pool only); per-property away-window note (NICE-4).
- **S-4 Settings** (reachable from S-2/S-3, not a top tab — rare but critical, deeper never absent): limit history log, dispute list with statuses, statement email/digest prefs (when NICE-1 lands).

No new role-switch tabs; scoping stays server-side (`serve.py:221-231` is the model).

## Message templates
Calm agency voice: plain English, concrete, no "triage/urgency/authority" jargon, decimal pounds kept exact (£160.50). `{...}` = payload fields. These are the literal `post_msg`/notification strings.

- **T1 · approval requested** (to landlord, at escalation — replaces today's silent card): "£{amount} needs your nod — {property}. {tradesperson} finished this on {completed}: {what}. Everything's on the card below, including who did it and when the tenant first reported it. It's above your £{limit} limit, that's why it reaches you and not just me."
- **T2a · you approved** (thread, to tenant+trades+landlord): "The landlord approved £{amount}. {tradesperson} will be settled shortly — thank you for waiting." *(extends today's generic line at `serve.py:665`)*
- **T2b · you declined** (thread + agent task): "The landlord declined £{amount} — “{reason}”. I'm picking this up with the trade and {tenant}; you'll hear from me within a working day."
- **T3 · proof requested** (approval pending, thread to landlord+agent): "Before nodding, the landlord would like to see {what — photos of the finished work / the invoice itself / a date the tenant confirmed}. I've asked the office to attach it."
- **T4 · landlord replies** (thread, chosen audience): free text, signed "— {landlord}". Placeholder in box: *"say something — the tenant and tradesperson will see this too if you pick them"*.
- **T5 · changed my mind after declining** (reply seeded): "On second thoughts I'm happy for this to go ahead — can we re-look at the price?"
- **T6 · job parked** (thread to tenant+trades+agent; 423 copy on blocked moves): "The owner is away until {until} — this job is parked until then unless it turns into a safety issue. {reason}."
- **T7 · second-quote ask** (thread + agent task): "I'd like a second opinion on the £{amount} quote before work starts — who else could the office send?"
- **T8 · park expires** (system→agent board + thread note to landlord): "{until} has passed — {landlord} is back. {job} is still parked; someone should decide whether to restart it."
- **T9 · limit changed** (confirmation + audit-visible): "Your approval limit is now £{new}, from today. Small jobs up to that settle without bothering you; anything bigger still comes to you. This doesn't change work already finished."
- **T10 · dispute upheld** (thread + statement row note): "You were right to query the £{amount} from {date} — {finding}. We're crediting it on your next statement."
- **T11 · dispute closed, not upheld**: "We looked into your query on {job} — {evidence summary in one line}. On the papers it stands, and here's everything again. If you still want to push, reply here and I'll take it to the trade with you."
- **T12 · pause overridden by agent** (thread to landlord): "The office restarted {job} despite the park — {reason: e.g. 'water is pouring through the ceiling, safety first'}. Ring me if you'd rather I hadn't."
- **T-CH · chase** (per `chase_after_hours`, portal banner; NICE-1 email copy): "Still waiting on your nod for £{amount} at {property} — the trade is waiting on their money. If it can wait longer, tell me and I'll park it myself."
- **T13 · monthly digest** (banner/email): "{month} at your two properties: {n} jobs, £{total} of repairs ({a} settled under your limit, {b} you signed off, {c} declined). Nothing needs you — {if pending: 'except £{pending}, still waiting on your nod'}."
- **T14 · auto-settled receipt line** (S-1 strip + statement): "{date} · {trade} · £{amount} — settled under your limit. [looks right] [query this]"

## NEEDS: backend primitives missing
Ordered so a **single pass builds bottom-up**: Wave 0 renders data the server *already sends* (zero API risk), then endpoints piggyback existing handlers, then genuinely new objects. Every wave is shippable alone.

**Wave 0 — surface-only, no serve.py change (kills D-2, D-3, half of D-4/D-8)**
- S-0a **Render scoped `c.thread` + reply box** (POST `/api/case-action {action:'reply', to:[…]}` — landlord already whitelisted, `serve.py:101`). [CRITICAL]
- S-0b **Decided-history list** from `approvals[]` with status≠pending (already in landlord payload). [CRITICAL — cheapest trust win in the product]
- S-0c **Statement rows** from scoped `jobs[]` (invoice_pence, completed_at, paid_at, status, assigned_to all present today); mode badge derived: `approved ∈ approvals → you signed it`, else `≤limit → auto`; quote `note`/`pence` from `job.quotes` (present, unrendered). [CRITICAL]

**Wave 1 — extend existing handlers (small, surgical serve.py deltas)**
- N-1 **Per-landlord authority + `POST /api/landlord-settings {limit_pence}`**, `ROLE_API {landlord, agent}`; store `stage.settings.landlords[<landlord>]`; **`complete` reads the owner's limit, falls back to `stage.authority`** (one-line change at `serve.py:609`); validate 5000–50000 pence; audit `limit_changed`. *Prereq sub-item:* landlord identity is the `display_name` string today (scoping at `serve.py:222` compares it) — give `users.json` entries a stable `landlord_id` carried on properties/approvals, or N-1 inherits a rename-vulnerability. [CRITICAL]
- N-1b **Lock the accidental moves** (same file, same pass): role-guard `verify_*` and `close`/`reopen` to agent inside `/api/job-action` and `/api/case-action`. Security-negative but belongs here: D-7. [CRITICAL]
- N-2 **`notify` prefs on the same settings object** `{chase_after_hours, notify_on_auto_settle, monthly_digest}` + portal "since last visit" computation (client stores last-seen ts; server adds `settled_events[]` to landlord scope, or simpler: derive from jobs — see S-0c). [CRITICAL: portal badge/strip · NICE: email]
- N-3 **`/api/landlord-action action:'more_evidence' {what,text}`** → `approval.evidence_requested{}`, card goes amber, thread T3, audit. Approval stays pending (no state added). [CRITICAL]
- N-4 **`/api/job-action action:'second_quote'`, landlord-guarded, only from `quoted`** → thread T7 + agent task case (clone the reject-task pattern `serve.py:676-686`). Job status unchanged. [NICE — agent can already do this manually]

**Wave 2 — new objects (the two moves that make the dashboard a control surface, not a billboard)**
- N-5 **Pause flag + gate**: `job.paused{by,reason,until,at}`; landlord `pause`/`unpause` via `/api/job-action`; server gate returns 423 on mutations while paused (unpause-by-owner and agent-override-with-reason exempt, T12 posts); expiry check piggybacks the 20s poll (agent board banner T8 — no cron needed in a flat-file demo). [CRITICAL — this is *the* "process editability" answer with the limit editor]
- N-6 **Dispute object + lifecycle**: `stage.disputes[]`; landlord `POST /api/landlord-action`-style `dispute {job_id, reason}` (works on any `paid` job, under- or over-limit); auto-creates agent task case; agent resolves `upheld|not_upheld` with note → thread T10/T11; statement rows join on `job_id` for the amber "queried" badge. [CRITICAL]
- N-7 **`GET /api/statement?month=YYYY-MM` (CSV)** for landlord/agent, server-built from jobs+approvals+disputes. [CRITICAL-cheap: it's a SELECT with commas. PDF = NICE-2]

**Wave 3 — honest money depth (needs data that doesn't exist yet; do not fake)**
- N-8 **Rent ledger + management fee model** — nothing in `stage.json` records collected rent or fees; today's "Rent in £2,400/mo" is *asking* rent wearing a statement's clothes. Requires new `ledger[]` object + agent entry flow. Until then S-2 shows "fee & rent collection: kept by your agent outside the portal" (one honest line beats the current fake). [CRITICAL for the *product*, NICE for this *sandbox* pass]
- NICE-1 email/push out-channel · NICE-2 PDF receipts with photo/cert slots (pairs with trades/agent evidence uploads) · NICE-3 edit own last thread reply · NICE-4 property-level away window (vacant Holloway Yard, lettings pause) · NICE-5 per-property limits for multi-portfolio landlords.

**Cross-doc dependencies (flag to sibling designs):** agent needs an approvals/disputes/evidence-request queue view (partially exists: "Waiting on landlord" tile, `agent.html:111,156-158`); trades needs the 423 copy on a parked job; tenant needs T6 visible ("parked until October" beats a silent stall).

## Acceptance checklist
One line per move; QA drives the live sandbox as `landlord` (portal polls every 20s — `landlord.html:144`; allow one refresh between steps).

- **M1** Landlord clicks Approve on T1 card → card moves to *Decided* (not vanishes), statement row gains "you signed it", job reads paid with `paid_at`, thread shows T2a to tenant+trades, `audit_log` gains `invoice_approved`.
- **M2** Decline without reason → 400 toast "tell us why" (exists); with reason → agent_task case appears on `/agent`, case badge flips to declined-equivalent copy, thread shows T2b, audit records reason.
- **M3** Ask-proof on a pending approval → card turns amber "waiting on proof", stays pending, agent sees the request on their board, audit gains `evidence_requested`; approving afterwards still works exactly once (existing 409 `already decided`).
- **M4** Landlord replies with audience "tenant" → text appears instantly in tenant's thread and in landlord's own view; agent sees it unscoped; messages not addressed to landlord never appear in her payload (re-test the `to` filter with a tenant-only message).
- **M5** After any decision, reload → *Decided* list shows amount, property, date, outcome, and her reject-reason verbatim.
- **M6** Second-quote ask on a `quoted` job → job still `quoted`, agent task created, T7 on thread; ask on an `open` job → 400.
- **M7** Dispute an auto-settled (£45) job → appears as open dispute for landlord AND as agent task; statement row goes "queried"; agent marks upheld → T10 + row shows credit note; money never un-pays silently (job stays `paid` throughout).
- **M8** Withdraw/accept dispute outcome → dispute closes, badge clears from statement, thread post visible.
- **M9** Suggest an approved firm on a case → participant added + T-style thread line; suggest a non-approved name → 400 "the agency vets trades first" (server already enforces, `serve.py:713`).
- **M10** Park job `open→assigned` states with until=1 Oct → trades sees 423 + T6 when accepting; agent override needs reason and T12 reaches landlord; park an `in_progress` job → refused with explanation.
- **M11** Unpause → gate lifts immediately; at `until` date with job still parked → agent board banner T8 exists, job status untouched.
- **M12** Set limit £120 as T. Blackwood → £140 job completed tomorrow escalates to her (over new limit) while S. Okoye's jobs still use the default £150; change back to £150 → instant; already-`awaiting_approval` approvals unaffected; audit shows both changes.
- **M13** Turn chase off → no banner at 24h on a pending £220; on → banner with T-CH copy on next poll.
- **M14** September statement rows reconcile to the penny with `jobs[]` totals (incl. £180/£45/£160.50/£210/£200/£90 legacy rows) and every row links to its case.
- **M15** CSV download parses; headers: date, property, job, trade, description, amount_pence→£, mode, decision, queried(Y/N).
- **M16** "Ask about row" pre-fills reply box with job ref; posted like M4.
- **Global** A landlord POSTing to `/api/landlord-action` against S. Okoye's approval id → 403 (ownership check, N-1); `/api/landlord-settings` from a tenant session → 403; landlord console attempt at `verify_approve`/`close` → 403 (N-1b). All new user-rendered strings pass through `esc()` (README rule 3).
