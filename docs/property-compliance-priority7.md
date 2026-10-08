# Property compliance workflow

The Agent Desk records property-level compliance evidence and preserves versions.

A record includes a property, requirement type, issue date, optional expiry and reminder dates, optional linked document, notes, creator and audit history. A missing-evidence record can be added without inventing a certificate date. When newer evidence is saved for the same property and requirement, the previous record is marked superseded and remains visible.

The API derives these states from explicit dates:

- **Missing** — an agent recorded that evidence is missing.
- **Expired** — expiry date is before today.
- **Expiring soon** — expiry is within 30 days.
- **Current** — evidence has no expiry or expires later than 30 days.
- **Superseded** — a replacement record exists.

A reminder becomes due on its recorded date. Expired items, near-term expiries, missing evidence and due reminders appear in the Agent Desk attention board. Roger does not infer legal requirements or certify that a document is valid. The list of requirement types is a recording aid; the agent must confirm which requirements apply to the property and jurisdiction. The workflow does not send email or SMS reminders.
