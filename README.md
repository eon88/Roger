# Roger — Virtual Estate Agency Portal

Roger is a single-agent lettings and property-management portal.

## Product goal

The portal has two clear sides:

1. **Front end = advertising**
   - Show available properties to prospective tenants.
   - Advertise the agency's service to landlords.
   - Recruit tradespeople into the contractor network.
   - Provide registration/enquiry routes and portal sign-in.

2. **Back end = management**
   - Bring **landlords, tenants and tradespeople under one roof**.
   - Keep each role in its own scoped portal.
   - Let **one estate agent operate the whole system** from the Agent Desk.

The agent is the central operator. Tenants report and communicate, landlords own properties and approve money where required, tradespeople quote and carry out work, and the agent coordinates the entire lifecycle.

AI assists with triage and routing; it does not replace the agent's responsibility for legal, safety or money decisions.

## Current application

The working application lives in `stage-clone/`.

```text
stage-clone/
├── serve.py                 # HTTP server, auth, API, workflow/state engine
├── jev_client.py            # AI triage with local keyword fallback
├── make_users.py            # Seeds role accounts; users.json stays gitignored
├── stage.json               # Prototype datastore
├── index.html               # Public advertising / property listings
├── login.html               # Account login
├── signin.html              # Role sign-in landing page
├── register-landlord.html   # Landlord acquisition form
├── register-trades.html     # Trades recruitment form
├── agent.html               # Central management cockpit
├── landlord.html            # Landlord portal
├── tenant.html              # Tenant portal
├── trades.html              # Trades portal
├── dash.css                 # Shared portal styling
├── api-public.json          # Public demo/listing feed
├── favicon.svg
├── sample-home.jpg
└── _next/                   # Required compiled assets for the public pages
```

## Current management features

- Real session authentication with role-scoped access.
- Separate Agent, Landlord, Tenant and Trades portals.
- Properties, cases and per-case message threads.
- Maintenance jobs and status synchronisation.
- Trades assignment and quote requests.
- Quote approval / decline flows.
- Invoice handling and landlord approval above standing authority.
- Trades credential gating with agent override.
- Landlord and trades registration review.
- Appointments and viewing scheduling.
- Invitation tokens.
- Document upload, verification and role-scoped document access.
- Audit log.
- Jev/OpenRouter triage for category, urgency, safety and trade, with keyword fallback.
- Public advertising and acquisition routes for tenants, landlords and trades.

## Role model

### Agent
The one operating desk. Has the whole picture and coordinates properties, people, cases, jobs, approvals, registrations, appointments and documents.

### Landlord
Sees only their properties and relevant management information. Reviews approvals, property activity, appointments and documents.

### Tenant
Sees their home. Reports problems, follows cases, manages appointments and accesses relevant documents.

### Trades
Sees available/assigned work, quotes, job progress, invoices and relevant job documents.

## Source-of-truth rules

- The **public site is for advertising and acquisition**.
- The **private portal is for property management**.
- The **Agent Desk is the orchestration layer** for the whole system.
- Do not create parallel role systems or duplicate workflow engines.
- Extend the existing case/job/approval workflow instead of creating competing versions.
- Keep management data server-side and role-scoped.
- Keep human control over legal, safety, credential and money decisions.
- Do not add old prototypes, audit snapshots or duplicate generated copies back into the working tree.

## Run locally

```bash
cd stage-clone
python3 make_users.py   # first run only; prints generated passwords once
python3 serve.py
```

Then open:

```text
http://127.0.0.1:8901
```

No third-party Python package is required for the core server.

## Docker deployment

The repository includes `Dockerfile`, `docker-compose.yml` and `DEPLOY.md`.

Runtime state is stored in the persistent Docker volume `roger_data`, so application updates do not overwrite live agency data.
