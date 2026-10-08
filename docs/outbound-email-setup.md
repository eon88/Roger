# Roger outbound email setup

Agent Desk supports deliberate, agent-authored email replies to the contact email saved on a case, plus agent-triggered inbound sync. Email is separate from portal delivery.

Configure these environment variables on the Roger server:

| Variable | Purpose | Default |
|---|---|---|
| `ROGER_SMTP_HOST` | SMTP relay hostname | Required |
| `ROGER_SMTP_PORT` | SMTP port; 465 uses implicit TLS, other ports use STARTTLS | 587 |
| `ROGER_FROM_EMAIL` | Sender address | Required |
| `ROGER_SMTP_USER` | SMTP username, when authentication is required | Optional |
| `ROGER_SMTP_PASSWORD` | SMTP password | Optional |

Keep credentials in the deployment secret store. Do not put them in `stage.json`, source control, or the browser.

The server takes the recipient from the case's recorded contact email. The browser cannot choose an arbitrary recipient. A message is added to the case timeline and audit log only after the SMTP server accepts it. If the server is not configured or the SMTP relay rejects the message, Roger reports the error and leaves the timeline unchanged.

Configure these variables for inbound polling:

| Variable | Purpose | Default |
|---|---|---|
| `ROGER_IMAP_HOST` | IMAP mailbox hostname | Required |
| `ROGER_IMAP_PORT` | IMAP over TLS port | 993 |
| `ROGER_IMAP_USER` | Mailbox username | Required |
| `ROGER_IMAP_PASSWORD` | Mailbox password | Required |
| `ROGER_IMAP_FOLDER` | Mailbox folder to scan | `INBOX` |

An agent clicks **Sync email inbox** to import unseen messages. Roger matches the sender address to the newest case with that contact email; otherwise it opens a new email case. Imported messages are deduplicated by mailbox UID and added to the case timeline. The sync currently reads plain-text body content and does not import attachments.

Provider OAuth, automatic polling/webhooks, delivery/bounce tracking, and attachment handling remain future work.
