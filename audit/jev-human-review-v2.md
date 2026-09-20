# Jev human-perspective review

_ran 2026-09-20 20:50 · 122 strings · 10 cases · model typesafe/jev-1.13_

## Clarity by surface (0=confusing, 2=clear)

- **tenant**: avg 1.05 · 23 strings · 23 possibly misleading
- **landlord**: avg 0.67 · 11 strings · 11 possibly misleading
- **trades**: avg 1.07 · 10 strings · 10 possibly misleading
- **agent**: avg 1.15 · 12 strings · 12 possibly misleading
- **public**: avg 0.96 · 49 strings · 49 possibly misleading
- **signin**: avg 0.39 · 17 strings · 17 possibly misleading

## Worst-rated strings (fix these first)

- **[public]** "stage." (in: *(page top)*) — understand 0.02/2 · misleads YES · warmth 22%
- **[public]** "stage." (in: *(page top)*) — understand 0.02/2 · misleads YES · warmth 21%
- **[public]** "stage." (in: *(page top)*) — understand 0.02/2 · misleads YES · warmth 19%
- **[signin]** "Join the contractor network" (in: *Estate agent*) — understand 0.09/2 · misleads YES · warmth 28%
- **[tenant]** "Public site" (in: *My Home*) — understand 0.13/2 · misleads YES · warmth 20%
- **[landlord]** "Demo: agent view" (in: *My Portfolio*) — understand 0.16/2 · misleads YES · warmth 22%
- **[public]** "Lettings, connected." (in: *Put your skills*) — understand 0.16/2 · misleads YES · warmth 33%
- **[signin]** "Public site" (in: *Stage portal*) — understand 0.17/2 · misleads YES · warmth 25%
- **[landlord]** "Demo: trades view" (in: *My Portfolio*) — understand 0.18/2 · misleads YES · warmth 21%
- **[signin]** "Estate agent" (in: *Estate agent*) — understand 0.2/2 · misleads YES · warmth 30%
- **[tenant]** "viewing as" (in: *My Home*) — understand 0.21/2 · misleads YES · warmth 24%
- **[landlord]** "Public site" (in: *My Portfolio*) — understand 0.21/2 · misleads YES · warmth 22%
- **[public]** "Send registration" (in: *You may contact me about this enquiry.*) — understand 0.25/2 · misleads YES · warmth 26%
- **[tenant]** "office@stage.example" (in: *Your reports*) — understand 0.26/2 · misleads YES · warmth 22%
- **[landlord]** "viewing as" (in: *My Portfolio*) — understand 0.26/2 · misleads YES · warmth 25%
- **[public]** "Trade, coverage and experience" (in: *Trade, coverage and experience*) — understand 0.29/2 · misleads YES · warmth 34%
- **[public]** "Send registration" (in: *You may contact me about this enquiry.*) — understand 0.3/2 · misleads YES · warmth 27%
- **[signin]** "Stage portal" (in: *Stage portal*) — understand 0.33/2 · misleads YES · warmth 32%
- **[signin]** "Portal | Stage" (in: *(page top)*) — understand 0.36/2 · misleads YES · warmth 27%
- **[tenant]** "My Home | Stage" (in: *(page top)*) — understand 0.38/2 · misleads YES · warmth 31%
- **[public]** "Name" (in: *Name*) — understand 0.38/2 · misleads YES · warmth 34%
- **[tenant]** "(National Gas — free, 24h). Then ring your agent on" (in: *My Home*) — understand 0.39/2 · misleads YES · warmth 33%
- **[signin]** "Tenant" (in: *Tenant*) — understand 0.39/2 · misleads YES · warmth 26%
- **[signin]** "Register your property" (in: *Estate agent*) — understand 0.4/2 · misleads YES · warmth 33%
- **[public]** "Landlord registration | Stage" (in: *(page top)*) — understand 0.4/2 · misleads YES · warmth 22%

## Triage calibration — Jev re-judging what the portal already stored

| case | stored | engine | Jev now | agree | vulnerable |
|--|--|--|--|--|--|
| 490 | 2 | jev | 1.91 | ✓ | 97% |
| 492 | 2 | jev | 1.56 | ✓ | 17% |
| 493 | 1 | jev | 0.57 | ✓ | 14% |
| 494 | 2 | jev | 2 | ✓ | 99% |
| 495 | 0 | jev | 0.01 | ✓ | 5% |
| 496 | 2 | jev | 1.76 | ✓ | 13% |
| 497 | 2 | jev | 1.81 | ✓ | 98% |
| 498 | 2 | jev | 1.6 | ✓ | 27% |
| 499 | 1 | jev | 1.31 | ✓ | 14% |
| 502 | 2 | jev | 2 | ✓ | 57% |

Agreement: **10/10** (100%). Every ✗ DRIFT is a human-facing mis-triage to re-check; stub-engine rows are expected to drift.

## Strings that mislead about safety or money

- **[tenant]** "e.g. The hallway light flickers when the door slams. No burning smell." (in: *What's going on?*)
- **[tenant]** "My Home | Stage" (in: *(page top)*)
- **[tenant]** "you@example.com" (in: *Your email (so we can reply)*)
- **[tenant]** "My Home" (in: *My Home*)
- **[tenant]** "Public site" (in: *My Home*)
- **[tenant]** "Gas smell, no heat in winter, flooding, or you feel unsafe?" (in: *My Home*)
- **[tenant]** "viewing as" (in: *My Home*)
- **[tenant]** "Call 0800 111 999 first" (in: *My Home*)
- **[tenant]** "(National Gas — free, 24h). Then ring your agent on" (in: *My Home*)
- **[tenant]** "report a problem" (in: *My Home*)
- **[tenant]** "your home" (in: *My Home*)
- **[tenant]** ". This form is for everything that can wait until morning." (in: *My Home*)
- **[tenant]** "Something needs attention?" (in: *Something needs attention?*)
- **[tenant]** "Your email (so we can reply)" (in: *Your email (so we can reply)*)
- **[tenant]** "Report it" (in: *Your email (so we can reply)*)
- **[tenant]** "What's going on?" (in: *What's going on?*)
- **[tenant]** "what you've reported" (in: *Your email (so we can reply)*)
- **[tenant]** "Your reports" (in: *Your reports*)
- **[tenant]** "Your reports are kept with dates and outcomes — useful evidence at the end of a tenancy. For anything this page doesn't cover, phone the office on" (in: *Your reports*)
- **[tenant]** "your paperwork" (in: *Your reports*)
- **[tenant]** "and a person will answer." (in: *Your reports*)
- **[tenant]** "office@stage.example" (in: *Your reports*)
- **[tenant]** ", Monday to Saturday, 8am to 8pm, or email" (in: *Your reports*)
- **[landlord]** "My Portfolio | Stage" (in: *(page top)*)
- **[landlord]** "DEMO — shared data, no login yet" (in: *(page top)*)
- **[landlord]** "viewing as" (in: *My Portfolio*)
- **[landlord]** "Public site" (in: *My Portfolio*)
- **[landlord]** "My Portfolio" (in: *My Portfolio*)
- **[landlord]** "Demo: trades view" (in: *My Portfolio*)
- **[landlord]** "Demo: agent view" (in: *My Portfolio*)
- **[landlord]** "money in and out" (in: *My Portfolio*)
- **[landlord]** "work in your buildings" (in: *My Portfolio*)
- **[landlord]** "decisions waiting for you" (in: *My Portfolio*)
- **[landlord]** "your properties" (in: *My Portfolio*)
- **[trades]** "DEMO — shared data, no login yet" (in: *(page top)*)
- **[trades]** "Job Board" (in: *Job Board*)
- **[trades]** "viewing as" (in: *Job Board*)
- **[trades]** "Public site" (in: *Job Board*)
- **[trades]** "R. Doyle Gas &amp; Heat" (in: *Job Board*)
- **[trades]** "Demo: landlord view" (in: *Job Board*)
- **[trades]** "jobs you can take" (in: *Job Board*)
- **[trades]** "your invoices and money" (in: *Job Board*)
- **[trades]** "jobs you've taken" (in: *Job Board*)
- **[trades]** "Demo: agent view" (in: *Job Board*)
- **[agent]** "DEMO — shared data, no login yet" (in: *(page top)*)
- **[agent]** "Agent Desk | Stage" (in: *(page top)*)
- **[agent]** "Agent Desk" (in: *Agent Desk*)
- **[agent]** "Cases" (in: *Agent Desk*)
- **[agent]** "Overview" (in: *Agent Desk*)
- **[agent]** "Jobs" (in: *Agent Desk*)
- **[agent]** "Registrations" (in: *Agent Desk*)
- **[agent]** "Properties" (in: *Agent Desk*)
- **[agent]** "History" (in: *Agent Desk*)
- **[agent]** "Public site" (in: *Agent Desk*)
- **[agent]** "Couldn't reach the portal." (in: *Agent Desk*)
- **[agent]** "Retry" (in: *Agent Desk*)
- **[public]** "stage." (in: *(page top)*)
- **[public]** "Stage | Homes to Rent" (in: *(page top)*)
- **[public]** "To rent" (in: *(page top)*)
- **[public]** "Sign in" (in: *(page top)*)
- **[public]** "Landlords &amp; trades" (in: *(page top)*)
- **[public]** "Your property." (in: *Your property.*)
- **[public]** "FOR LANDLORDS" (in: *(page top)*)
- **[public]** "Our care." (in: *Your property.*)
- **[public]** "Let and manage your property with support from our agency." (in: *Your property.*)
- **[public]** "Register your property" (in: *Your property.*)
- **[public]** "LETTINGS &amp; PROPERTY MANAGEMENT" (in: *Your property.*)
- **[public]** "Find your next home." (in: *Find your next home.*)
- **[public]** "Properties to rent" (in: *Properties to rent*)
- **[public]** "properties" (in: *Properties to rent*)
- **[public]** "Loading available homes…" (in: *Properties to rent*)
- **[public]** "FOR TRADESPEOPLE" (in: *Properties to rent*)
- **[public]** "Put your skills" (in: *Put your skills*)
- **[public]** "to work." (in: *Put your skills*)
- **[public]** "Join our contractor network for property maintenance and repairs." (in: *Put your skills*)
- **[public]** "Register as a tradesperson" (in: *Put your skills*)
- **[public]** "Lettings, connected." (in: *Put your skills*)
- **[signin]** "Portal | Stage" (in: *(page top)*)
- **[signin]** "Stage portal" (in: *Stage portal*)
- **[signin]** "demo — no accounts yet" (in: *Stage portal*)
- **[signin]** "Public site" (in: *Stage portal*)
- **[signin]** "who are you today?" (in: *Stage portal*)
- **[signin]** "Real logins land with the Supabase build. For now, each door shows the portal as that person sees it — with the demo identity noted inside." (in: *Stage portal*)
- **[signin]** "Tenant" (in: *Tenant*)
- **[signin]** "Report a problem and watch it get fixed. You only see your own home. (demo: Daniel Mensah, Parkside Mews)" (in: *Tenant*)
- **[signin]** "Landlord" (in: *Landlord*)
- **[signin]** "Approve big bills, see where the money went, keep your limit. (demo: T. Blackwood, two properties)" (in: *Landlord*)
- **[signin]** "Take jobs from the board, submit invoices, get paid. (demo: R. Doyle Gas &amp; Heat)" (in: *Tradesperson*)
- **[signin]** "Tradesperson" (in: *Tradesperson*)
- **[signin]** "Estate agent" (in: *Estate agent*)
- **[signin]** "The desk everything flows through: approvals, cases, dispatch, the full audit trail." (in: *Estate agent*)
- **[signin]** "Own a property or run a trade?" (in: *Estate agent*)
- **[signin]** "Register your property" (in: *Estate agent*)
- **[public]** "Landlord registration | Stage" (in: *(page top)*)
- **[signin]** "Join the contractor network" (in: *Estate agent*)
- **[public]** "stage." (in: *(page top)*)
- **[public]** "Back to lettings" (in: *(page top)*)
- **[public]** "FOR LANDLORDS" (in: *(page top)*)
- **[public]** "Register your property" (in: *Register your property*)
- **[public]** "Tell us about your property and the support you need." (in: *Register your property*)
- **[public]** "Name" (in: *Name*)
- **[public]** "The agency will review your registration and contact you." (in: *Register your property*)
- **[public]** "Email" (in: *Email*)
- **[public]** "Website" (in: *Website*)
- **[public]** "Tell us about your property" (in: *Tell us about your property*)
- **[public]** "You may contact me about this enquiry." (in: *You may contact me about this enquiry.*)
- **[public]** "Send registration" (in: *You may contact me about this enquiry.*)
- **[public]** "Portal access is arranged by the agent after your registration is reviewed." (in: *You may contact me about this enquiry.*)
- **[public]** "Tradesperson registration | Stage" (in: *(page top)*)
- **[public]** "stage." (in: *(page top)*)
- **[public]** "Back to lettings" (in: *(page top)*)
- **[public]** "FOR TRADESPEOPLE" (in: *(page top)*)
- **[public]** "Join our trades network" (in: *Join our trades network*)
- **[public]** "Tell us your trade, where you work and your experience." (in: *Join our trades network*)
- **[public]** "The agency will review your registration and contact you." (in: *Join our trades network*)
- **[public]** "Email" (in: *Email*)
- **[public]** "Name" (in: *Name*)
- **[public]** "Trade, coverage and experience" (in: *Trade, coverage and experience*)
- **[public]** "Website" (in: *Website*)
- **[public]** "You may contact me about this enquiry." (in: *You may contact me about this enquiry.*)
- **[public]** "Send registration" (in: *You may contact me about this enquiry.*)
- **[public]** "Portal access is arranged by the agent after your registration is reviewed." (in: *You may contact me about this enquiry.*)
