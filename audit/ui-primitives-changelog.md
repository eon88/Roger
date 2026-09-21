# UI pass — surface date/doc/invite primitives (2026-09-21)

Pages edited (UI only; serve.py/API contract untouched):
- dash.css: added .badge.proposed/confirmed/cancelled/completed, .docrow, .appt,
  .filechip, .divider, .agent-quick
- tenant.html: + Appointments section (confirm/decline; status-past list);
  "paperwork" now lists real documents from /api/documents (filechip link),
  placeholder buttons removed.
- agent.html: overview + Appointments card + Documents card (verify/reject on
  pending); case actions + Book a viewing / Send invite / Upload document.
- landlord.html: + Appointments section + "paperwork on file" (docs) scoped to
  own properties.
- trades.html: + "paperwork on your jobs" (docs) scoped to assigned jobs.

Verified (real browser): tenant confirm->confirmed + toast; agent overview shows
appts/docs + case action buttons; landlord sees own-prop appts/docs only;
trades sees job docs only. All 4 scripts pass `node --check`.
