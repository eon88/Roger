# Roger outbound email setup

Agent Desk supports deliberate, agent-authored email replies to the contact email saved on a case. Email is a separate action from portal replies.

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

This is outbound SMTP only. Incoming email sync, provider OAuth, delivery/bounce tracking, and attachment handling are still future work.
