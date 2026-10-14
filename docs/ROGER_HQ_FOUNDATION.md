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

## Step 5 pilot (development branch)

- `stage-clone/roger_pg.py` is an opt-in PostgreSQL repository adapter.
- `GET /api/hq/properties` is the first read-only HTTP integration. The endpoint requires an authenticated `agent`, server-held `user.id` and `user.agency_id` UUIDs, and matching `agency_memberships` entry.
- Enable only in a disposable development environment with `ROGER_STORAGE_BACKEND=postgres` and `ROGER_DATABASE_URL`. Without these, the legacy JSON backend remains active.
- The existing JSON user records do not yet contain these UUIDs; the pilot intentionally returns 503 rather than guessing tenant identity.
- This is **not** a complete switch to PostgreSQL. Legacy workflow writes, session storage, public forms, uploads, and other portal endpoints remain JSON-backed. Do not enable mixed backend mode in production.
- All changes must be tested in GitHub Actions before considering a staged deployment. Verify the actual run, not merely the existence of workflow configuration.

## Agency authentication work in progress

- `authenticate_agency_user(database_url, username, password, agency_slug)` resolves membership server-side, verifies scrypt credentials and rejects inactive agencies.
- Database accounts require `app_users.password_hash` in `salt_hex:digest_hex` format. Legacy JSON users have separate credentials; no migration has been performed.
- PostgreSQL authentication is **not yet wired to HTTP login/session handling**. The existing JSON login and four portals continue unchanged.
- The read-only HTTP pilot requires a trusted authenticated session with user UUID and agency UUID. Do not populate those fields from unverified request headers or browser-supplied JSON.
- Tests have been committed but the latest GitHub Actions run has not been independently verified; GitHub commit combined-status endpoint returned no statuses, which is not evidence of success or failure.
