# Jev human-perspective review

_ran 2026-09-20 20:42 · 128 strings · 10 cases · model typesafe/jev-1.13_

## Clarity by surface (0=confusing, 2=clear)

- **tenant**: avg 0.98 · 22 strings · 22 possibly misleading
- **landlord**: avg 0.83 · 14 strings · 14 possibly misleading
- **trades**: avg 1.16 · 14 strings · 14 possibly misleading
- **agent**: avg 1.11 · 12 strings · 12 possibly misleading
- **public**: avg 0.96 · 49 strings · 49 possibly misleading
- **signin**: avg 0.33 · 17 strings · 17 possibly misleading

## Worst-rated strings (fix these first)

- **[public]** "stage." (in: *(page top)*) — understand 0.02/2 · misleads YES · warmth 21%
- **[public]** "stage." (in: *(page top)*) — understand 0.02/2 · misleads YES · warmth 21%
- **[public]** "stage." (in: *(page top)*) — understand 0.02/2 · misleads YES · warmth 21%
- **[tenant]** "your stage" (in: *My Home*) — understand 0.08/2 · misleads YES · warmth 31%
- **[landlord]** "your stage" (in: *What's happening in your buildings*) — understand 0.1/2 · misleads YES · warmth 27%
- **[signin]** "Front" (in: *Stage portal*) — understand 0.11/2 · misleads YES · warmth 28%
- **[signin]** "Agent" (in: *Agent*) — understand 0.12/2 · misleads YES · warmth 26%
- **[public]** "Lettings, connected." (in: *Put your skills*) — understand 0.16/2 · misleads YES · warmth 34%
- **[tenant]** "your track record" (in: *Your email (so we can reply)*) — understand 0.18/2 · misleads YES · warmth 18%
- **[public]** "Our care." (in: *Your property.*) — understand 0.18/2 · misleads YES · warmth 34%
- **[tenant]** "office@stage.demo" (in: *Your reports*) — understand 0.19/2 · misleads YES · warmth 17%
- **[tenant]** "(Mon–Sat 8–8) or" (in: *Your reports*) — understand 0.23/2 · misleads YES · warmth 23%
- **[signin]** "Register your property" (in: *Agent*) — understand 0.24/2 · misleads YES · warmth 28%
- **[landlord]** "Front" (in: *My Portfolio*) — understand 0.25/2 · misleads YES · warmth 23%
- **[public]** "Send registration" (in: *You may contact me about this enquiry.*) — understand 0.26/2 · misleads YES · warmth 26%
- **[public]** "Trade, coverage and experience" (in: *Trade, coverage and experience*) — understand 0.27/2 · misleads YES · warmth 34%
- **[public]** "Send registration" (in: *You may contact me about this enquiry.*) — understand 0.28/2 · misleads YES · warmth 25%
- **[landlord]** "Trades view" (in: *My Portfolio*) — understand 0.29/2 · misleads YES · warmth 27%
- **[public]** "Name" (in: *Name*) — understand 0.3/2 · misleads YES · warmth 34%
- **[signin]** "Tenant" (in: *Tenant*) — understand 0.32/2 · misleads YES · warmth 27%
- **[signin]** "Stage portal" (in: *Stage portal*) — understand 0.34/2 · misleads YES · warmth 32%
- **[signin]** "Portal | Stage" (in: *(page top)*) — understand 0.36/2 · misleads YES · warmth 28%
- **[landlord]** "your money" (in: *Needs your decision*) — understand 0.38/2 · misleads YES · warmth 29%
- **[landlord]** "verify" (in: *Needs your decision*) — understand 0.38/2 · misleads YES · warmth 22%
- **[public]** "Landlord registration | Stage" (in: *(page top)*) — understand 0.39/2 · misleads YES · warmth 22%

## Triage calibration — Jev re-judging what the portal already stored

| case | stored | engine | Jev now | agree | vulnerable |
|--|--|--|--|--|--|
| 490 | 2 | none | 1.94 | ✓ | 98% |
| 492 | 1 | none | 1.56 | ✓ | 17% |
| 493 | 2 | none | 0.62 | **✗ DRIFT** | 13% |
| 494 | 2 | jev | 2 | ✓ | 98% |
| 495 | 0 | jev | 0.01 | ✓ | 5% |
| 496 | 2 | jev | 1.79 | ✓ | 13% |
| 497 | 2 | jev | 1.83 | ✓ | 98% |
| 498 | 2 | jev | 1.63 | ✓ | 27% |
| 499 | 1 | jev | 1.32 | ✓ | 13% |
| 502 | 2 | jev | 2 | ✓ | 63% |

Agreement: **9/10** (90%). Every ✗ DRIFT is a human-facing mis-triage to re-check; stub-engine rows are expected to drift.

## Strings that mislead about safety or money

- **[tenant]** "My Home" (in: *My Home*)
- **[tenant]** "signed in as" (in: *My Home*)
- **[tenant]** "e.g. The hallway light flickers when the door slams. No burning smell." (in: *What's going on?*)
- **[tenant]** "you@example.com" (in: *Your email (so we can reply)*)
- **[tenant]** "Call 0800 111 999 first" (in: *My Home*)
- **[tenant]** "Gas smell, no heat in winter, flooding, or you feel unsafe?" (in: *My Home*)
- **[tenant]** "Front" (in: *My Home*)
- **[tenant]** "(National Gas — free, 24h). Then ring your agent on" (in: *My Home*)
- **[tenant]** ". This form is for everything that can wait until morning." (in: *My Home*)
- **[tenant]** "your stage" (in: *My Home*)
- **[tenant]** "report" (in: *My Home*)
- **[tenant]** "Something needs attention?" (in: *Something needs attention?*)
- **[tenant]** "My Home | Stage" (in: *(page top)*)
- **[tenant]** "What's going on?" (in: *What's going on?*)
- **[tenant]** "Report it" (in: *Your email (so we can reply)*)
- **[tenant]** "Your email (so we can reply)" (in: *Your email (so we can reply)*)
- **[tenant]** "your track record" (in: *Your email (so we can reply)*)
- **[tenant]** "Your reports" (in: *Your reports*)
- **[tenant]** "documents &amp; money" (in: *Your reports*)
- **[tenant]** "Your reports are kept with dates and outcomes — useful evidence at the end of a tenancy. Questions not covered here? Call your agent on" (in: *Your reports*)
- **[landlord]** "My Portfolio | Stage" (in: *(page top)*)
- **[tenant]** "(Mon–Sat 8–8) or" (in: *Your reports*)
- **[tenant]** "office@stage.demo" (in: *Your reports*)
- **[landlord]** "My Portfolio" (in: *My Portfolio*)
- **[landlord]** "DEMO — shared data, no login yet" (in: *(page top)*)
- **[landlord]** "Trades view" (in: *My Portfolio*)
- **[landlord]** "signed in as" (in: *My Portfolio*)
- **[landlord]** "Front" (in: *My Portfolio*)
- **[landlord]** "Agent view" (in: *My Portfolio*)
- **[landlord]** "approve" (in: *My Portfolio*)
- **[landlord]** "Needs your decision" (in: *Needs your decision*)
- **[landlord]** "What's happening in your buildings" (in: *What's happening in your buildings*)
- **[landlord]** "Properties" (in: *Properties*)
- **[landlord]** "your stage" (in: *What's happening in your buildings*)
- **[landlord]** "your money" (in: *Needs your decision*)
- **[trades]** "Job Board | Stage" (in: *(page top)*)
- **[trades]** "DEMO — shared data, no login yet" (in: *(page top)*)
- **[landlord]** "verify" (in: *Needs your decision*)
- **[trades]** "Job Board" (in: *Job Board*)
- **[trades]** "signed in as" (in: *Job Board*)
- **[trades]** "R. Doyle Gas &amp; Heat" (in: *Job Board*)
- **[trades]** "Front" (in: *Job Board*)
- **[trades]** "Agent view" (in: *Job Board*)
- **[trades]** "Landlord view" (in: *Job Board*)
- **[trades]** "book" (in: *Job Board*)
- **[trades]** "in progress" (in: *Open jobs*)
- **[trades]** "Open jobs" (in: *Open jobs*)
- **[trades]** "Yours now" (in: *Yours now*)
- **[trades]** "get paid" (in: *Yours now*)
- **[trades]** "Completed, waiting, settled" (in: *Completed, waiting, settled*)
- **[agent]** "Agent Desk | Stage" (in: *(page top)*)
- **[agent]** "DEMO — shared data, no login yet" (in: *(page top)*)
- **[agent]** "Overview" (in: *Agent Desk*)
- **[agent]** "Agent Desk" (in: *Agent Desk*)
- **[agent]** "Cases" (in: *Agent Desk*)
- **[agent]** "Jobs" (in: *Agent Desk*)
- **[agent]** "History" (in: *Agent Desk*)
- **[agent]** "Properties" (in: *Agent Desk*)
- **[agent]** "Registrations" (in: *Agent Desk*)
- **[agent]** "Front" (in: *Agent Desk*)
- **[agent]** "Couldn't reach the portal." (in: *Agent Desk*)
- **[agent]** "Retry" (in: *Agent Desk*)
- **[public]** "Stage | Homes to Rent" (in: *(page top)*)
- **[public]** "stage." (in: *(page top)*)
- **[public]** "To rent" (in: *(page top)*)
- **[public]** "Landlords &amp; trades" (in: *(page top)*)
- **[public]** "FOR LANDLORDS" (in: *(page top)*)
- **[public]** "Sign in" (in: *(page top)*)
- **[public]** "Your property." (in: *Your property.*)
- **[public]** "Let and manage your property with support from our agency." (in: *Your property.*)
- **[public]** "Register your property" (in: *Your property.*)
- **[public]** "LETTINGS &amp; PROPERTY MANAGEMENT" (in: *Your property.*)
- **[public]** "Find your next home." (in: *Find your next home.*)
- **[public]** "Our care." (in: *Your property.*)
- **[public]** "Properties to rent" (in: *Properties to rent*)
- **[public]** "properties" (in: *Properties to rent*)
- **[public]** "Loading available homes…" (in: *Properties to rent*)
- **[public]** "Put your skills" (in: *Put your skills*)
- **[public]** "FOR TRADESPEOPLE" (in: *Properties to rent*)
- **[public]** "to work." (in: *Put your skills*)
- **[public]** "Join our contractor network for property maintenance and repairs." (in: *Put your skills*)
- **[public]** "Lettings, connected." (in: *Put your skills*)
- **[public]** "Register as a tradesperson" (in: *Put your skills*)
- **[signin]** "Portal | Stage" (in: *(page top)*)
- **[signin]** "Stage portal" (in: *Stage portal*)
- **[signin]** "choose your view" (in: *Stage portal*)
- **[signin]** "demo — no accounts yet" (in: *Stage portal*)
- **[signin]** "Real logins land with the Supabase build. For now, each door shows the portal as that person sees it — with the demo identity noted inside." (in: *Stage portal*)
- **[signin]** "Front" (in: *Stage portal*)
- **[signin]** "as Daniel Mensah — report issues, track repairs, keep the paper trail." (in: *Tenant*)
- **[signin]** "Tenant" (in: *Tenant*)
- **[signin]** "Landlord" (in: *Landlord*)
- **[signin]** "as T. Blackwood — approve work above the limit, see where the money goes." (in: *Landlord*)
- **[signin]** "Tradesperson" (in: *Tradesperson*)
- **[signin]** "Own a property or run a trade?" (in: *Agent*)
- **[signin]** "the desk — registrations, triaged cases, dispatch, the whole book." (in: *Agent*)
- **[signin]** "Register your property" (in: *Agent*)
- **[signin]** "Agent" (in: *Agent*)
- **[public]** "Landlord registration | Stage" (in: *(page top)*)
- **[signin]** "Join the contractor network" (in: *Agent*)
- **[public]** "Back to lettings" (in: *(page top)*)
- **[public]** "stage." (in: *(page top)*)
- **[signin]** "as R. Doyle Gas &amp; Heat — take jobs, submit invoices, get settled." (in: *Tradesperson*)
- **[public]** "The agency will review your registration and contact you." (in: *Register your property*)
- **[public]** "FOR LANDLORDS" (in: *(page top)*)
- **[public]** "Register your property" (in: *Register your property*)
- **[public]** "Tell us about your property and the support you need." (in: *Register your property*)
- **[public]** "Name" (in: *Name*)
- **[public]** "Tell us about your property" (in: *Tell us about your property*)
- **[public]** "Website" (in: *Website*)
- **[public]** "You may contact me about this enquiry." (in: *You may contact me about this enquiry.*)
- **[public]** "Send registration" (in: *You may contact me about this enquiry.*)
- **[public]** "Email" (in: *Email*)
- **[public]** "Portal access is arranged by the agent after your registration is reviewed." (in: *You may contact me about this enquiry.*)
- **[public]** "Tradesperson registration | Stage" (in: *(page top)*)
- **[public]** "Back to lettings" (in: *(page top)*)
- **[public]** "FOR TRADESPEOPLE" (in: *(page top)*)
- **[public]** "stage." (in: *(page top)*)
- **[public]** "Join our trades network" (in: *Join our trades network*)
- **[public]** "Tell us your trade, where you work and your experience." (in: *Join our trades network*)
- **[public]** "The agency will review your registration and contact you." (in: *Join our trades network*)
- **[public]** "Name" (in: *Name*)
- **[public]** "Email" (in: *Email*)
- **[public]** "Trade, coverage and experience" (in: *Trade, coverage and experience*)
- **[public]** "Website" (in: *Website*)
- **[public]** "Send registration" (in: *You may contact me about this enquiry.*)
- **[public]** "You may contact me about this enquiry." (in: *You may contact me about this enquiry.*)
- **[public]** "Portal access is arranged by the agent after your registration is reviewed." (in: *You may contact me about this enquiry.*)
