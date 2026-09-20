# Tenant Audit — "My Home" (Stage portal, http://127.0.0.1:8901/tenant)

**Auditor persona:** Daniel Mensah, working parent, tenant of 16 Parkside Mews. One-handed phone use, zero jargon tolerance, needs: *was I heard? who's coming? when? is my kid safe? how do I reach a human? can I prove this later?*
**Method:** live browser session (`audit-tenant`), drove the real UI, submitted a live report, inspected `tenant.html` / `dash.css` / `serve.py` / `stage.json` to confirm what the UI promises vs what the backend does. Screenshots taken at 390px and 1280px.
**Date:** 20 Sep 2026.

**Scores (as the renter):**
- First-impression trust: **4/10** — looks calm and clean, but has no phone number, no emergency path, and machine-speak where a worried parent needs plain words.
- Usability: **5/10** — genuinely simple one-page flow, good mobile layout; ruined by unreadable strips, truncated text, 9px labels.
- Workflow (does it actually look after me): **3/10** — the report lands and triages well, then the portal goes silent: status never changes, nobody is named, no date, no proof.

---

## 1. My existing reports — what the status actually promises

All four cards say the same thing, verbatim: **"20 Sept 2026 · with the agent"**.

| Report (as truncated in UI) | Badge shown | Strip shown | What's actually true in the backend |
|---|---|---|---|
| "The front door lock is broken from outside and I am locked o…" | `with the agent` | `PASSED TO THE RIGHT PERSON · JEV LIVE / maintenance / Emergency / 66% SAFETY` | job-4 `status: open`, `assigned_to: null` — **nobody has been passed to anyone.** I'm still outside. |
| "The radiator in the bedroom makes a banging noise when the h…" | `with the agent` | `PASSED TO THE RIGHT PERSON · KEYWORD FALLBACK / maintenance / Emergency / 30% SAFETY` | job-2 was completed and paid (£45). The card still says "with the agent". |
| "Kitchen tap drips constantly and there is a leak under the s…" | `with the agent` | `PASSED TO THE RIGHT PERSON · KEYWORD FALLBACK / maintenance / Soon / 90% SAFETY` | job-1 invoice £180 → landlord approval `appr-1` **approved**, job `paid`. Tenant sees none of this. |
| "Bathroom ceiling is wet and the paint is blistering — water…" | `with the agent` | JEV LIVE / Emergency / 93% | job created, unassigned. (Also: this is not a report I made — see §5.) |

**"with the agent" is a dead end.** `tenant.html` line 47 defines better labels — `in_progress:"a tradesperson is on it"`, `awaiting_approval:"waiting for landlord sign-off"`, `paid:"sorted — thanks"` — but `serve.py` never updates `case.status` after the case is created `"open"`. Those labels are unreachable code. Every report I will ever file says "with the agent" forever. A stressed parent reads that as *they've got it* the first day and *they're ignoring me* by day ten, and the UI gives no way to tell the difference.

**No date or deadline appears anywhere** except the submission day ("20 Sept 2026" — not even a time). No "by", no ETA, no "we'll update you within X". The £180/£45 money trail and the landlord sign-off that the task brief describes are **completely invisible on the tenant page** — I only know they exist because I curl'd `/api/stage`.

Would a stressed parent understand? "with the agent" — yes, but it promises nothing. "sorted — thanks" and "waiting for landlord sign-off" — never actually shown. "landlord sign-off pending" as a concept would also raise *whose landlord, waiting on what, for how long*.

## 2. Live test: reporting black mould

Typed exactly: *"There is black mould spreading in my son's bedroom and he has asthma."* → clicked **"Report it"**.

- Immediate reply (verbatim): **"Logged — a tradesperson has been asked."**
- New card appeared instantly: `20 Sept 2026 · with the agent` + strip `PASSED TO THE RIGHT PERSON · JEV LIVE / maintenance / Emergency / 96% SAFETY`.
- Backend: case 497 triaged `urgency 2 (raw 1.9), safety 0.96, confidence 100, engine: jev`; job-5 created `status: open, assigned_to: null`.

**What works:** the routing is genuinely good — mould + asthma was instantly read as an emergency with a child-health risk, faster and better than most letting agents' phone tree. The confirmation is immediate, so the "did it send?" anxiety is answered.

**What fails the emotionally-urgent test:**
- "a tradesperson has been asked" is a **lie by optimism**: no tradesperson exists for this job yet; it's a row in a queue nobody has accepted. Compare the agent view, which honestly says *"Routed: human decision required"*.
- **Nothing acknowledges the child.** The system clearly *knows* (96% safety, asthma parsed) but the tenant-facing reply is one generic sentence for a dripping tap and for mould in an asthmatic toddler's bedroom. No "we've flagged this as urgent because of your son's asthma".
- No name, no phone number, no "someone will call you by [time]", no way to add "actually it's worse today".
- **Did the portal make me feel heard? Half.** The instant strip says *something intelligent read me*, but the words themselves are machine telemetry, and the human facts I care about — who, when, is my boy safe tonight — are absent. Within an hour of no update, "Emergency" next to a static card becomes its own kind of anxiety.

## 3. The things I went looking for and could not find

Programmatic search of the rendered tenant page (`document.body.innerText`) for: phone, call, tel, contact, out-of-hours, hours, ETA, time, appointment, visit, rent, deposit, tenancy, contract, human — **all NOT FOUND** (only "Emergency" appears, inside the triage strips). Confirmed by grep: no phone number or emergency instruction exists anywhere in `tenant.html` or `dash.css`.

Missing, as a checklist of what a renter actually needs:
1. **A phone number / "talk to a human"** — none. The only "contact" affordance is the textarea. For a lockout at 10pm or a gas smell, a text box with no SLA is not a service.
2. **Out-of-hours / emergency instructions** — none. Nothing says "for gas smells leave the flat and call the National Gas Emergency Service 0800 111 999". Priya Shah's gas report (visible in the data) was handled by the same silent form. This is a safety gap, not a UX gap.
3. **Expected-time commitments** — none. No response SLA, no ETA, no "we'll be in touch by".
4. **Appointment booking for the tradesperson** — no slot picker, no "who is coming" name/photo, no confirm/reschedule. `assigned_to` exists in the backend and is never surfaced to me.
5. **Tenancy document** — no download, no link, not even a tenancy start date.
6. **Rent amount / payment history** — the rent (£2,400) exists in `/api/stage` but the tenant page shows no rent, no balance, no receipts.
7. **Deposit info** — nothing. No deposit amount, no scheme, no protected-since date. For the "prove it later for my deposit" need: no report reference numbers, no full-text of my own reports (truncated at 60 chars with no expand), no exportable history, no timestamps beyond the day.
8. **Feedback loop** — no way to comment "still leaking", to escalate, or to say it's fixed.

## 4. Trust & privacy probes — the machine under the glass

The tenant header exposes tabs **Front / Landlord / Trades / Agent** — one click from "My Home" I was on the Agent dashboard reading: **every tenant's reports** (Priya Shah's *"I can smell gas in the kitchen… My toddler plays on the floor there."*), other tenants' names, an enquiry with a visible email address, and **"STANDING AUTHORITY £150"** — the agency's internal spending rule. `/api/stage` is unauthenticated JSON: anyone can read all of it, and `POST /api/tenant/issue` accepts any `name` — a stranger can file reports as me (a "Bathroom ceiling is wet" case appeared in *my* list mid-audit, filed by another tester, because the identity is a hardcoded JS constant: `const ME = "Daniel Mensah"`).

**Does exposing internals help or scare a lay tenant?** As written: scares, and worse, *misleads*.
- **"KEYWORD FALLBACK"** is displayed to me in plain sight. It means "the AI didn't answer, a dumb stub guessed" — yet the same strip cheerfully asserts **"PASSED TO THE RIGHT PERSON"**. A tenant who decodes that tag learns the reassurance is boilerplate; a tenant who doesn't is falsely reassured. Either way the pair is dishonest.
- **"90% SAFETY"** (kitchen tap) reads as *90% safe* — it actually means *90% safety risk*. The agent view correctly labels it "SAFETY RISK"; the tenant view dropped the two words that carry the meaning. A banging radiator shows **"Emergency" urgency with 30% safety** — the numbers visibly disagree with each other, which teaches me the labels are decoration.
- **"JEV LIVE"**, **"CATEGORY"**, uppercase micro-labels at 9px: pure telemetry. Zero tenant value, high "this is watching me / this is a toy" charge.

**Three strips rewritten in plain English (what the tenant should see):**
1. Mould: ~~`PASSED TO THE RIGHT PERSON · JEV LIVE / maintenance / Emergency / 96% SAFETY`~~ → **"We've marked this urgent because mould near a child with asthma is a health risk. A damp specialist is being arranged now — we'll text you their name and arrival time within 2 hours. If your son's breathing gets worse, call your GP or 111."**
2. Kitchen tap: ~~`… Soon URGENCY / 90% SAFETY`~~ → **"Treated as a high safety risk (damp + electrical hazard near water). A plumber attended and the £180 repair is approved — job done. Anything still dripping? Tap here to reopen."**
3. Radiator: ~~`… KEYWORD FALLBACK / Emergency / 30% SAFETY`~~ → **"We're not sure how urgent this is, so a person — not a computer — will read your report today and get back to you by 5pm."**

The rule: show the tenant **who, when, and what to do next**; hide the engine's name for itself.

## 5. UI / first impression, brutal

**Good (real, not polite):**
- Calm paper/ink palette, serif headings, generous cards — looks more trustworthy than 90% of letting-agent portals.
- Mobile at 390px: single column, no horizontal overflow (`scrollWidth 390 == innerWidth 390`), tap targets fine, one obvious action. The REPORT box with placeholder *"e.g. The hallway light flickers when the door slams. No burning smell."* is a nice, human example that quietly teaches "say whether it's dangerous".
- English level of the *prose* is good: "Something needs attention?", "managed by your agent".
- Empty states exist ("Nothing reported yet. Use the box above when something needs attention." / "No home linked to this name yet.").

**Bad:**
- **`signed in as Daniel Mensah` with no login, no sign-out** — and the page title renders as **"🐴 My Home | Stage — Tenant"** (a horse emoji leaking into the tab). It reads toy-ish exactly where it needs to read institutional. I'm trusting this with a gas leak; there's no session, no security theatre, nothing that says my neighbours can't see my reports. (They can — §4.)
- The jev-strip is the loudest, most-repeated element on the page and says the least to me; its 9px/10px micro-labels (`URGENCY`, `SAFETY`, `CATEGORY`, `.move` section labels) are borderline unreadable on a phone while stirring pasta.
- Emergency state has no visual drama: the strip's background stays soft green for a 96%-risk mould emergency; only tiny inner chips turn red. The most urgent card in my list looks 80% like the least urgent one.
- Report text truncated at 60 chars, no expand — I can't re-read what I told them, which kills the "prove it later" use case.
- "with the agent" badge is amber for everything, forever — the badge system's color coding (blue `in_progress`, green `paid`) is dead code in practice (§1).
- Fonts: `Instrument Sans`/`Fraunces` are declared but never loaded on the dash pages (only `/dash.css`, no font link) — computed stack falls back to system-ui/Georgia. Minor, but it means the design isn't even its own design.
- Copy leak: *"You only ever see this page"* is displayed on a page whose header links to the Landlord, Trades and Agent dashboards. The sentence is false the moment it's rendered.

**Would I trust reporting a gas leak here?** I'd type it, because the box is inviting — then I'd put the phone down and call someone anyway, because there is no phone number, no emergency script, and no evidence on this page that a human is awake. First-impression trust: **4/10**.

---

## Findings register (severity-ranked)

| # | Sev | Area | Finding | Evidence |
|---|-----|------|---------|----------|
| T1 | high | workflow | Case status never advances: every report stuck at "with the agent" even after job paid/approved | `serve.py` never mutates `case.status`; STATUS_LABEL paid/awaiting_approval unreachable; kitchen tap job-1 `paid` yet card says "with the agent" |
| T2 | high | workflow | No phone number, no human contact, no out-of-hours/emergency instruction anywhere on tenant surface | innerText search: phone/call/contact/hours all NOT FOUND; no `tel:` in tenant.html |
| T3 | high | workflow | "PASSED TO THE RIGHT PERSON" + "a tradesperson has been asked" shown while `assigned_to: null` — false reassurance on emergencies | mould job-5 & lockout job-4 open/unassigned; strip text in tenant.html `jev()` |
| T4 | high | ui | "90% SAFETY" means 90% safety *risk*; tenant copy dropped "RISK" (agent view has it) — inverted meaning for laypeople | `SAFETY` vs agent's `SAFETY RISK` labels; radiator "Emergency + 30% SAFETY" contradiction |
| T5 | high | privacy | Unauthenticated `/api/stage` + tenant nav links to Agent/Landlord/Trades dashboards expose other tenants' reports (Priya's gas leak), emails, rents, "STANDING AUTHORITY £150" | live click path /tenant → Agent → Cases; curl /api/stage returns all |
| T6 | high | privacy | Identity is a hardcoded client constant; any POST with `name:"Daniel Mensah"` files reports into my list (observed: case 498 by another tester) | `const ME = "Daniel Mensah"`; handle_tenant_issue trusts body.name |
| T7 | med | workflow | No ETA, deadline, appointment booking, or tradesperson identity; no way to add info/escalate/comment on an open report | §3; no such fields in tenant.html |
| T8 | med | workflow | No deposit, rent, tenancy-document or payment-history surface; no reference numbers/receipts/export — tenant cannot "prove it later" | §3 keyword search NOT FOUND |
| T9 | med | ui | "KEYWORD FALLBACK" engine tag exposed next to reassurance copy; strips are telemetry, not communication | strips verbatim §1 |
| T10 | med | ui | Reports truncated at 60 chars, no expand; submission date has no time; no update history | my-cases renderer `c.message.slice(0,60)` |
| T11 | low | ui | 9–10px uppercase micro-labels (.metric span 9px, .move 10px) fail phone readability; emergency strips stay green | computed styles, screenshots |
| T12 | low | ui | "signed in as Daniel Mensah" with no login + 🐴 emoji in tab title + "You only ever see this page" next to 4 role links — toy-ish | header render, document.title |
| T13 | low | ui | Declared fonts (Instrument Sans/Fraunces) never loaded on dash pages | no font link in tenant.html/dash.css |

## Delights (what genuinely worked)
- One box, one button, zero forms — reporting took 5 seconds one-handed and the card appeared instantly. This is the best part of the whole product.
- The triage is *actually smart*: mould+asthma → Emergency/96%/jev in ~2s, gas+traveller → 98%. When it works, it works better than a human rota.
- Placeholder copy "e.g. The hallway light flickers when the door slams. No burning smell." is thoughtful, human, and teaches tenants to mention danger.
- "Your track record" as a section name is a nice framing of the deposit-proof idea — the intent is right even if the execution (truncated, no refs) isn't.
- Mobile layout survives 390px with no overflow; the visual design (paper, serif, calm green) genuinely de-escalates.
- The STATUS_LABEL vocabulary ("sorted — thanks", "waiting for landlord sign-off") is *already written* in a good voice — it just needs to be wired to real job states.

## Top fixes, in order
1. Sync case status to job/approval events so the tenant sees "a tradesperson is on it" → "sorted — thanks" (T1).
2. Add a contact block: agent phone, out-of-hours number, and a red banner on the report form: "Gas smell or danger? Leave the flat and call 0800 111 999 first." (T2)
3. Never show "passed to the right person" until `assigned_to` is non-null; until then say "a person is being assigned — we'll text you their name" (T3).
4. Rename the tenant strip: one plain sentence ("This is urgent because…") + "who's coming / when" fields; delete JEV LIVE / KEYWORD FALLBACK / CATEGORY / % from the tenant view (T4, T9).
5. Auth: role-scoped session, per-tenant API view, remove Landlord/Trades/Agent tabs from the tenant header (T5, T6).
6. Add: full-text expandable reports with reference numbers & timestamps, rent/deposit/tenancy documents, appointment confirmation (T7, T8, T10).
