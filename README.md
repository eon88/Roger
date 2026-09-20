# Stage — virtual estate agency portal

A working demo + dev sandbox for a solopreneur-run UK lettings agency. One case
book, four role portals, AI triage as the wiring.

## Run it

```bash
cd stage-clone
python3 serve.py            # stdlib only, no pip installs — http://127.0.0.1:8901
```

Data is flat files: `stage-clone/stage.json` is the whole database
(properties, cases, jobs, approvals, registrations, audit_log).
`stage-clone/users.json` (gitignored) holds scrypt password hashes + sessions —
seed your own with `python3 make_users.py`.

## Layout

| path | what |
|---|---|
| `/` | public site (cloned from the original ChatGPT-hosted stage.site; forms POST `/api/public`) |
| `/signin` → `/login` | role doors, real session auth (httpOnly cookie) |
| `/agent` `/landlord` `/tenant` `/trades` | the four portals |
| `stage-clone/serve.py` | stdlib HTTP server: routing, auth, role-scoped API, workflow engine |
| `stage-clone/jev_client.py` | Jev (TypeSafe System One via OpenRouter) batched triage: category, urgency, safety, trade — with keyword fallback |
| `audit/` | 4 persona audits + consolidated fix list + `jev_human_review.py` (see Workflow rules) |
| `estate-agency-portal-draft.md`, `keyhouse-portal-prototype.html` | original spec + v0.4 single-file prototype (predecessor, reference only) |

## The domain model (Operating Model)

Four dancers on one stage (the property): **tenant** reports, **agent**
choreographs, **landlord** approves money, **trades** fix things. The AI is
electricity, not a dancer: every incoming message gets one batched Jev call
(category/urgency/safety/trade). Rules that stay human: law, safety, money.
Invoices ≤ £150 ("standing authority") auto-settle; above it the landlord
signs off; jobs whose required trade the booker lacks are held for agent
verification. Every action lands in `stage.json.audit_log`.

## Workflow rules (learned the hard way — see audit/)

1. **Status propagates or it lies.** `case.status` must follow job/approval
   events (dispatched → in_progress → awaiting_approval → resolved/declined).
   Never introduce a state a lower surface can't see.
2. **Server-side scoping only.** `/api/stage` answers differ per role. Client
   filtering is presentation, not security.
3. **Escape all user text** (`esc()` in every page). A registration probe once
   XSS'd the agent desk.
4. **Jev judges, never writes.** Typed score/choice/noul questions only; prose
   stays human. `audit/jev_human_review.py` re-rates the whole portal in one
   command after copy changes — JSONL diff is the regression gate.
5. **Reject/decline needs a reason + consequences** (creates an agent task).
   Decisions never vanish silently.

## Conventions

- Visual language: paper `#faf7f2`, pine `#1e6b4f`, Fraunces display /
  Instrument Sans UI, unboxed cards (`dash.css`) — match it in new views.
- Plain English for users; move vocabulary (REPORT/APPROVE/VERIFY) lives in
  the data and CSS class names, not headline copy.
- Demo identities: Daniel Mensah (tenant), T. Blackwood (landlord),
  R. Doyle Gas & Heat (trades). Keep the stories coherent — the seeded
  `stage.json` walks through tap-leak, gas-smell and lockout cases.

## Roadmap (from the audit, not invented)

Real Supabase auth + per-account data · receipts/VAT/payment provider ·
compliance calendar (CP12, EPC, deposits) · landlord standing-authority
editor · notifications/push · rent ledger.
