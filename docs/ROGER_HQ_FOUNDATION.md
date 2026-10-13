# Roger HQ — Multi-agency foundation (development only)

This branch is a first **schema prototype**, not a production migration.

- `db/001_multi_agency.sql`: agencies, accounts, memberships, properties, cases, jobs, audit log, and initial RLS policies.
- `tests/test_agency_isolation.py`: disposable-PostgreSQL isolation tests.
- Current Roger JSON backend is unchanged. No routes use PostgreSQL yet.
- Never run the schema or tests against production.
- RLS context must be set by trusted backend code, inside each transaction, after verifying membership. Never accept a client-provided agency ID as authority.
- Production runtime DB user must not own tables or have BYPASSRLS.
- Before real migration: cover approvals, documents, appointments, invitations, registrations, messages, subscription data; add indexes and migrations; test joins, updates, deletes, cross-agency references and role boundaries.
- A dedicated migration strategy must preserve existing live JSON data and credentials, with backups and rollback.
