# Jev human-perspective review

_ran 2026-09-20 22:39 · 124 strings · 11 cases · model typesafe/jev-1.13_

## Clarity by surface (0=confusing, 2=clear)

- **tenant**: avg 1.23 · 28 strings · 28 possibly misleading
- **landlord**: avg 1.40 · 9 strings · 9 possibly misleading
- **trades**: avg 1.57 · 9 strings · 9 possibly misleading
- **agent**: avg 1.33 · 12 strings · 12 possibly misleading
- **public**: avg 0.96 · 49 strings · 49 possibly misleading
- **signin**: avg 0.79 · 17 strings · 17 possibly misleading

## Worst-rated strings (fix these first)

- **[public]** "stage." (in: *(page top)*) — understand 0.02/2 · misleads YES · warmth 21%
- **[public]** "stage." (in: *(page top)*) — understand 0.02/2 · misleads YES · warmth 21%
- **[public]** "stage." (in: *(page top)*) — understand 0.02/2 · misleads YES · warmth 22%
- **[signin]** "Lettings site" (in: *Stage portal*) — understand 0.1/2 · misleads YES · warmth 26%
- **[tenant]** "Lettings site" (in: *My Home*) — understand 0.13/2 · misleads YES · warmth 18%
- **[public]** "Lettings, connected." (in: *Put your skills*) — understand 0.14/2 · misleads YES · warmth 33%
- **[signin]** "Register as a tradesperson" (in: *Sign in as the estate agent*) — understand 0.22/2 · misleads YES · warmth 24%
- **[agent]** "Try again" (in: *Agent Desk*) — understand 0.25/2 · misleads YES · warmth 22%
- **[public]** "Trade, coverage and experience" (in: *Trade, coverage and experience*) — understand 0.26/2 · misleads YES · warmth 34%
- **[public]** "Send registration" (in: *You may contact me about this enquiry.*) — understand 0.26/2 · misleads YES · warmth 23%
- **[public]** "Send registration" (in: *You may contact me about this enquiry.*) — understand 0.28/2 · misleads YES · warmth 24%
- **[tenant]** "office@stage.example" (in: *Your reports*) — understand 0.34/2 · misleads YES · warmth 22%
- **[signin]** "Register a property with the agency" (in: *Sign in as the estate agent*) — understand 0.34/2 · misleads YES · warmth 34%
- **[signin]** "Stage portal" (in: *Stage portal*) — understand 0.36/2 · misleads YES · warmth 33%
- **[public]** "Name" (in: *Name*) — understand 0.39/2 · misleads YES · warmth 34%
- **[trades]** "Lettings site" (in: *Job Board*) — understand 0.41/2 · misleads YES · warmth 34%
- **[public]** "Landlord registration | Stage" (in: *(page top)*) — understand 0.41/2 · misleads YES · warmth 22%
- **[public]** "Name" (in: *Name*) — understand 0.43/2 · misleads YES · warmth 33%
- **[public]** "Tradesperson registration | Stage" (in: *(page top)*) — understand 0.47/2 · misleads YES · warmth 26%
- **[public]** "Our care." (in: *Your property.*) — understand 0.2/2 · misleads YES · warmth 36%
- **[signin]** "The desk everything flows through: approvals, cases, dispatch, the full audit trail." (in: *Sign in as the estate agent*) — understand 0.2/2 · misleads YES · warmth 42%
- **[tenant]** ", 24 hours a day. For anything that can wait until morning, ring your agent on" (in: *My Home*) — understand 0.58/2 · misleads YES · warmth 33%
- **[public]** "Your property." (in: *Your property.*) — understand 0.64/2 · misleads YES · warmth 26%
- **[landlord]** "Your properties | Stage portal" (in: *(page top)*) — understand 0.74/2 · misleads YES · warmth 29%
- **[signin]** "If you own a rental property or work in property maintenance, register here first:" (in: *Sign in as the estate agent*) — understand 0.42/2 · misleads YES · warmth 45%

## Triage calibration — Jev re-judging what the portal already stored

| case | stored | engine | Jev now | agree | vulnerable |
|--|--|--|--|--|--|
| 490 | 2 | jev | 1.92 | ✓ | 97% |
| 492 | 2 | jev | 1.56 | ✓ | 18% |
| 493 | 1 | jev | 0.61 | ✓ | 13% |
| 494 | 2 | jev | 2 | ✓ | 99% |
| 495 | 0 | jev | 0 | ✓ | 5% |
| 496 | 2 | jev | 1.82 | ✓ | 13% |
| 497 | 2 | jev | 1.82 | ✓ | 98% |
| 498 | 2 | jev | 1.62 | ✓ | 29% |
| 499 | 1 | jev | 1.26 | ✓ | 14% |
| 502 | 2 | jev | 2 | ✓ | 61% |
| 503 | 1 | jev | 0.64 | ✓ | 14% |

Agreement: **11/11** (100%). Every ✗ DRIFT is a human-facing mis-triage to re-check; stub-engine rows are expected to drift.

## Strings that mislead about safety or money

- **[tenant]** "you@example.com" (in: *Your email (so we can reply)*)
- **[tenant]** "e.g. The hallway light flickers when the door slams. No burning smell." (in: *What's going on?*)
- **[tenant]** "Your home | Stage portal" (in: *(page top)*)
- **[tenant]** "My Home" (in: *My Home*)
- **[tenant]** "Signed in as" (in: *My Home*)
- **[tenant]** "Lettings site" (in: *My Home*)
- **[tenant]** "Call National Gas free on" (in: *My Home*)
- **[tenant]** "Log out" (in: *My Home*)
- **[tenant]** "Gas smell, no heat in winter, flooding, or you feel unsafe?" (in: *My Home*)
- **[tenant]** ", 24 hours a day. For anything that can wait until morning, ring your agent on" (in: *My Home*)
- **[tenant]** "or use the form below." (in: *My Home*)
- **[tenant]** "your home" (in: *My Home*)
- **[tenant]** "report a problem" (in: *My Home*)
- **[tenant]** "Something needs attention?" (in: *Something needs attention?*)
- **[tenant]** "What's going on?" (in: *What's going on?*)
- **[tenant]** "We need a working email so the office can reply to you." (in: *Your email (so we can reply)*)
- **[tenant]** "A short, plain description is enough — it helps the right tradesperson arrive prepared." (in: *What's going on?*)
- **[tenant]** "Your email (so we can reply)" (in: *Your email (so we can reply)*)
- **[tenant]** "Your reports" (in: *Your reports*)
- **[tenant]** "what you've reported" (in: *Your email (so we can reply)*)
- **[tenant]** "Send report" (in: *Your email (so we can reply)*)
- **[tenant]** "your paperwork" (in: *Your reports*)
- **[tenant]** "Phone the office on" (in: *Your reports*)
- **[tenant]** "Your reports are kept with dates and outcomes — useful evidence at the end of a tenancy." (in: *Your reports*)
- **[tenant]** "— Monday to Saturday, 8am to 8pm, and a person will answer." (in: *Your reports*)
- **[tenant]** "office@stage.example" (in: *Your reports*)
- **[tenant]** "Or email" (in: *Your reports*)
- **[tenant]** "and we will reply within one working day." (in: *Your reports*)
- **[landlord]** "Your properties | Stage portal" (in: *(page top)*)
- **[landlord]** "My Portfolio" (in: *My Portfolio*)
- **[landlord]** "Lettings site" (in: *My Portfolio*)
- **[landlord]** "Signed in as" (in: *My Portfolio*)
- **[landlord]** "Log out" (in: *My Portfolio*)
- **[landlord]** "money in and out" (in: *My Portfolio*)
- **[landlord]** "bills you need to approve" (in: *My Portfolio*)
- **[landlord]** "ongoing repairs and complaints" (in: *My Portfolio*)
- **[landlord]** "your properties" (in: *My Portfolio*)
- **[trades]** "Job Board" (in: *Job Board*)
- **[trades]** "Your jobs | Stage portal" (in: *(page top)*)
- **[trades]** "Signed in as" (in: *Job Board*)
- **[trades]** "R. Doyle Gas &amp; Heat" (in: *Job Board*)
- **[trades]** "Lettings site" (in: *Job Board*)
- **[trades]** "Log out" (in: *Job Board*)
- **[trades]** "jobs you can take" (in: *Job Board*)
- **[trades]** "jobs you've taken" (in: *Job Board*)
- **[trades]** "your invoices and money" (in: *Job Board*)
- **[agent]** "Agent Desk | Stage" (in: *(page top)*)
- **[agent]** "Agent Desk" (in: *Agent Desk*)
- **[agent]** "Cases" (in: *Agent Desk*)
- **[agent]** "Overview" (in: *Agent Desk*)
- **[agent]** "Jobs" (in: *Agent Desk*)
- **[agent]** "Registrations" (in: *Agent Desk*)
- **[agent]** "Properties" (in: *Agent Desk*)
- **[agent]** "Lettings site" (in: *Agent Desk*)
- **[agent]** "History" (in: *Agent Desk*)
- **[agent]** "Log out" (in: *Agent Desk*)
- **[agent]** "Try again" (in: *Agent Desk*)
- **[agent]** "Couldn't reach the portal." (in: *Agent Desk*)
- **[public]** "Stage | Homes to Rent" (in: *(page top)*)
- **[public]** "To rent" (in: *(page top)*)
- **[public]** "stage." (in: *(page top)*)
- **[public]** "Landlords &amp; trades" (in: *(page top)*)
- **[public]** "Sign in" (in: *(page top)*)
- **[public]** "FOR LANDLORDS" (in: *(page top)*)
- **[public]** "Your property." (in: *Your property.*)
- **[public]** "Let and manage your property with support from our agency." (in: *Your property.*)
- **[public]** "Our care." (in: *Your property.*)
- **[public]** "LETTINGS &amp; PROPERTY MANAGEMENT" (in: *Your property.*)
- **[public]** "Register your property" (in: *Your property.*)
- **[public]** "Properties to rent" (in: *Properties to rent*)
- **[public]** "properties" (in: *Properties to rent*)
- **[public]** "Find your next home." (in: *Find your next home.*)
- **[public]** "FOR TRADESPEOPLE" (in: *Properties to rent*)
- **[public]** "Put your skills" (in: *Put your skills*)
- **[public]** "Loading available homes…" (in: *Properties to rent*)
- **[public]** "Register as a tradesperson" (in: *Put your skills*)
- **[public]** "Join our contractor network for property maintenance and repairs." (in: *Put your skills*)
- **[public]** "to work." (in: *Put your skills*)
- **[signin]** "Stage portal" (in: *Stage portal*)
- **[signin]** "Sign in | Stage portal" (in: *(page top)*)
- **[public]** "Lettings, connected." (in: *Put your skills*)
- **[signin]** "Lettings site" (in: *Stage portal*)
- **[signin]** "pick a role to view the portal as" (in: *Stage portal*)
- **[signin]** "sign in to continue" (in: *Stage portal*)
- **[signin]** "Sign in as a tenant" (in: *Sign in as a tenant*)
- **[signin]** "Every door is a real sign-in: each account sees only its own homes, jobs or bills — nothing else. Ask the agency desk for an account." (in: *Stage portal*)
- **[signin]** "Report a problem and watch it get fixed. You only see your own home. (account: tenant)" (in: *Sign in as a tenant*)
- **[signin]** "Sign in as a landlord" (in: *Sign in as a landlord*)
- **[signin]** "Approve big bills, see where the money went, keep your limit. (account: landlord)" (in: *Sign in as a landlord*)
- **[signin]** "Sign in as a tradesperson" (in: *Sign in as a tradesperson*)
- **[signin]** "Sign in as the estate agent" (in: *Sign in as the estate agent*)
- **[signin]** "Take jobs from the board, submit invoices, get paid. (account: trades)" (in: *Sign in as a tradesperson*)
- **[signin]** "The desk everything flows through: approvals, cases, dispatch, the full audit trail." (in: *Sign in as the estate agent*)
- **[signin]** "Register a property with the agency" (in: *Sign in as the estate agent*)
- **[signin]** "If you own a rental property or work in property maintenance, register here first:" (in: *Sign in as the estate agent*)
- **[signin]** "Register as a tradesperson" (in: *Sign in as the estate agent*)
- **[public]** "Landlord registration | Stage" (in: *(page top)*)
- **[public]** "stage." (in: *(page top)*)
- **[public]** "Back to lettings" (in: *(page top)*)
- **[public]** "FOR LANDLORDS" (in: *(page top)*)
- **[public]** "Register your property" (in: *Register your property*)
- **[public]** "The agency will review your registration and contact you." (in: *Register your property*)
- **[public]** "Tell us about your property and the support you need." (in: *Register your property*)
- **[public]** "Name" (in: *Name*)
- **[public]** "Tell us about your property" (in: *Tell us about your property*)
- **[public]** "Website" (in: *Website*)
- **[public]** "Email" (in: *Email*)
- **[public]** "Portal access is arranged by the agent after your registration is reviewed." (in: *You may contact me about this enquiry.*)
- **[public]** "Send registration" (in: *You may contact me about this enquiry.*)
- **[public]** "You may contact me about this enquiry." (in: *You may contact me about this enquiry.*)
- **[public]** "Tradesperson registration | Stage" (in: *(page top)*)
- **[public]** "stage." (in: *(page top)*)
- **[public]** "Back to lettings" (in: *(page top)*)
- **[public]** "FOR TRADESPEOPLE" (in: *(page top)*)
- **[public]** "Join our trades network" (in: *Join our trades network*)
- **[public]** "Name" (in: *Name*)
- **[public]** "Tell us your trade, where you work and your experience." (in: *Join our trades network*)
- **[public]** "The agency will review your registration and contact you." (in: *Join our trades network*)
- **[public]** "Trade, coverage and experience" (in: *Trade, coverage and experience*)
- **[public]** "Email" (in: *Email*)
- **[public]** "Website" (in: *Website*)
- **[public]** "Send registration" (in: *You may contact me about this enquiry.*)
- **[public]** "Portal access is arranged by the agent after your registration is reviewed." (in: *You may contact me about this enquiry.*)
- **[public]** "You may contact me about this enquiry." (in: *You may contact me about this enquiry.*)
