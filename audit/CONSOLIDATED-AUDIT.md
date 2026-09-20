# CONSOLIDATED AUDIT — Stage Clone Portal
**Date:** 2026-09-20 · **Method:** 4 persona subagents drove the live system (browser + API) as agent, landlord, tenant, tradesperson.
**Full per-role evidence:** `agent-audit.md` · `landlord-audit.md` · `tenant-audit.md` · `trades-audit.md` (same folder)

## Scores (1–10, by the personas who had to use it)

| Role | Usability | Workflow |
|---|---|---|
| Agent (solo operator) | 3 | 2 |
| Landlord (investor) | 4 | 3 |
| Tenant (working parent) | 5 | 3 |
| Tradesperson (van, one-man band) | 4 | 2 |
| **Average** | **4** | **2.5** |

Verdict in one line: **the data model is ahead of every surface built on it** — all four roles independently discovered that the information they need exists in `stage.json` and is simply never rendered to them.

---

## Tier 0 — Security & liability bugs (fix immediately, before anyone else touches the demo)

| # | Finding | Who flagged | Evidence |
|---|---|---|---|
| 0.1 | **Stored XSS on /agent** — registration `details` and case `message` interpolated into `innerHTML` unescaped. A probe `<img src=x onerror=…>` executed as the agent; anyone submitting a form can flip registrations or exfiltrate all landlord/tenant data via `/api/stage`. | agent (browser-proven) | agent-audit §4 |
| 0.2 | **Public registration form broken end-to-end** — the cloned front page POSTs to `/api/public`, which only exists as GET → applicants literally see `Unexpected token '<', "<!DOCTYPE"…`. No real landlord/tradesperson can ever sign up. | agent (fetch-hooked) | agent-audit §3 |
| 0.3 | **No emergency-safety copy for tenants** — no phone number, no "gas smell? call 0800 111 999 first", no out-of-hours instruction. A tenant reporting gas has a textarea and nothing else. Liability-grade gap. | tenant | tenant-audit §2 |
| 0.4 | **No credential gating on trades jobs** — a gas engineer persona booked a lockout with one click; the 98%-safety gas job is bookable by any identity. Gas Safety (Installation and Use) Regs 1995 paper-trail risk. | trades | trades-audit §1 |
| 0.5 | **Auth is theatre, honestly labelled as such nowhere** — hardcoded `ME` constants, role tabs let every visitor "become" every role, `/api/stage` is world-readable. Fine for demo *if watermarked*; the "You only ever see this page" copy currently makes a false promise. | landlord + tenant + trades | landlord-audit §4 |

## Tier 1 — The broken spine: statuses never propagate (the #1 workflow fix)

All four roles hit this from different sides — one root cause: `case.status` is written once at creation and never touched again.

- Tenant: everything frozen at "with the agent" even when jobs are **paid**; the good labels in `STATUS_LABEL` are dead code
- Landlord: paid/rejected cases still badge "open"; rejection changes nothing the landlord or tenant can see
- Agent: **cannot see jobs, invoices or approvals at all** — the middle of every story is invisible; "human decision required" strips sit on cases whose only button is Close
- Trades: no "who took my £220 decision", no SLA, silent terminal rejection, no reason field
- Also: job-3 (gas emergency) sits **unassigned forever** with no one notified; "PASSED TO THE RIGHT PERSON" claims a person who was never assigned (`assigned_to:null`)

**The fix (one mechanism, ~4 surfaces):** a status-sync on job/approval events (accepted → dispatched, awaiting_approval → sign-off pending, paid → sorted, rejected → declined + agent task), a per-case **thread view** joining `case_id → job → approval → invoice`, and decision-history lists (approve/reject currently makes cards vanish with no toast, no log, no undo).

## Tier 2 — Evidence & money (the trust layer)

- **Approval cards carry zero evidence**: tradesperson never named (data exists!), no invoice ref, no photos, no certificates, no second-quote option → landlord persona: "I cannot safely approve."
- **No money view anywhere**: no ledger, fees, repair totals, balance; £285 charged against one landlord's property in an evening, invisible on her page
- **"Paid" is a badge, not money**: flipped in the same request, no date/ref/receipt/VAT
- **Standing authority is copy-only**: no editor, no under-limit settlement feed, trades told more clearly than the payer who owns the rule
- Registration form captures nothing verifiable (no Gas Safe number, insurance, references) and approval leaves no history

## Tier 3 — Language & UI (labels are lying to humans)

| Problem | Now | Should be |
|---|---|---|
| Inverted safety metric (3 roles) | "90% SAFETY" (means *risk*) | "Possible danger to someone: yes (98%)" |
| Engine telemetry shown to laypeople | "JEV LIVE · KEYWORD FALLBACK · SYSTEM ONE · ?" | internal only; one consistent strip label per role |
| Urgency without promise | "Emergency · URGENCY" | "Plumber dispatched today" |
| Same triage, 4 different names | DISPATCH / SYSTEM ONE VIEW / PASSED TO… / JEV TRIAGE | one vocabulary |
| Fake precision | "CONFIDENCE 100%" | omit |
| Truncation eats safety detail | gas job reads "My toddler plays on…" (70 chars, no expand) | full text + photo slots |
| Broken microcopy | "(undefined)" emails; 🐴 in the tab title; honeypot website rendered real; case 490 points at property `p-1` that doesn't exist; empty-state SVG doubled; /signin is a no-op | guard fields, collect email, validate property_id, make /signin the role chooser |
| Mobile | agent.html nav clips off-screen (no @media in its inline styles); 9px labels; 35px buttons; 3.77:1 contrast on payment terms | wrap/scroll tabs, 44px targets, ≥4.5:1 on anything financial |
| No live refresh | gas leak reported into an open tab never appears; no error/blank-state on API failure | 15s poll + badge |

## What the personas genuinely loved (keep these, don't sand them off)

- The **standing-authority sentence** — "that's why it reached you and not just the agent" — cited by three different roles as the best copy in the product; lift its pattern everywhere
- "no rush — reply when convenient"; "sorted — thanks"
- One-handed 5-second reporting with a placeholder that quietly teaches danger-flagging
- Jev's live judgment quality: mould+asthma → emergency; paint question → no job. "The model is ahead of the UI" (agent-audit)
- Red/amber colour language readable at a glance; calm paper design de-escalates stressed users
- Decimal handling (£160.50) correct end-to-end

## Suggested build order

1. **P0 — bugs & safety (one sitting):** XSS escape (`esc()` helper + CSP), fix `/register/*` form route + success state, emergency banner + agent phone on tenant form, demo-mode watermark, `(undefined)`/`?`/`p-1` guards, /signin → role chooser
2. **P1 — the spine:** status-sync engine + per-case thread view on /agent + decision histories + conditional "right person" copy + unassigned-job escalation tile
3. **P2 — trust layer:** structured registration fields (Gas Safe #, insurance, categories) → job credential gating → approval evidence block (tradesperson name at minimum, it's already in the data)
4. **P3 — money & polish:** landlord statement, real settlement semantics, standing-authority editor, polling/notifications, mobile pass, WCAG contrast fixes

## Data left behind by the audits
The personas created live test data (mould report, gas/lockout jobs, an approved reg, a rejected £220, etc.) — kept as evidence; pre-audit snapshot at `/tmp/stage-snapshot-before-audit.json` to restore any time.
