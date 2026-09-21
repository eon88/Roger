# Jev workflow-design review

_ran 2026-09-21 06:07 · 30 items · recipients judged in-persona_

## agent-dashboard.md
- clarity avg 1.40/2 · 0 unkeepable-promise items · 5 safety holes · 1 emergency-covered

- [message→agent] "Good news — {X} is now handling this. They'll arrange a time that suits you. If they don't" — clear 1.18, SAFETY HOLE
- [message→agent] "Logged as case #{id}. We'll get the right person onto it — usually sorted within a few day" — clear 1.22, SAFETY HOLE
- [message→agent] "Job {job} at {property}: {short fault}. We need a quote before work starts — price and not" — clear 1.30, SAFETY HOLE
- [message→agent] "Closing this case: {reason}. Everything stays on the record here, and reopening is one mes" — SAFETY HOLE
- [message→agent] "Sign-off request for {property} — £{amount}. Reported by the tenant {reported_date}, done " — SAFETY HOLE
- [message→agent] "Welcome to the Stage network, {name}. You're approved for {trades} work with us and you'll" — clear 0.51
- [message→agent] "Thanks for applying to work with us. We can't approve you for our list yet — {note}. Reply" — clear 0.94
- [message→agent] "All settled and paid — thank you for bearing with us on this one. If anything's still not " — clear 0.98
- [message→agent] "Thanks for telling us, {name}. We're treating the {item} as an emergency — a tradesperson " — clear 1.10

## landlord-dashboard.md
- clarity avg 1.18/2 · 0 unkeepable-promise items · 4 safety holes · 1 emergency-covered

- [message→landlord] "{until} has passed — {landlord} is back. {job} is still parked; someone should decide whet" — clear 0.22, SAFETY HOLE
- [message→landlord] "We looked into your query on {job} — {evidence summary in one line}. On the papers it stan" — clear 1.27, SAFETY HOLE
- [message→landlord] "{month} at your two properties: {n} jobs, £{total} of repairs ({a} settled under your limi" — SAFETY HOLE
- [message→landlord] "The owner is away until {until} — this job is parked until then unless it turns into a saf" — SAFETY HOLE
- [message→landlord] "On second thoughts I'm happy for this to go ahead — can we re-look at the price?" — clear 0.59
- [message→landlord] "{date} · {trade} · £{amount} — settled under your limit. [looks right] [query this]" — clear 0.67
- [message→landlord] "The office restarted {job} despite the park — {reason: e.g. 'water is pouring through the " — clear 0.86
- [message→landlord] "Before nodding, the landlord would like to see {what — photos of the finished work / the i" — clear 0.93
- [message→landlord] "The landlord declined £{amount} — “{reason}”. I'm picking this up with the trade and {tena" — clear 1.17

## trades-dashboard.md
- clarity avg 1.21/2 · 0 unkeepable-promise items · 0 safety holes · 0 emergency-covered

- [message→trades] "Quote declined — {reason}. Please re-quote or a different trade will be asked." — clear 1.13

