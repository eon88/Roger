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

## Step 5: opt-in agency HTTP login and sessions

- Apply `db/002_agency_sessions.sql` after schema 001 in a disposable PostgreSQL database.
- Set `ROGER_STORAGE_BACKEND=postgres` and `ROGER_DATABASE_URL` only in a non-production test environment.
- `POST /api/agency/login` accepts username/password/agency slug and sets a secure, HttpOnly, SameSite=Strict session cookie scoped to `/api/agency/`. Local plain-HTTP tests require `ROGER_COOKIE_SECURE=0` (never production).
- `GET /api/agency/whoami` and `GET /api/agency/properties` use PostgreSQL sessions. Property listings are currently agent-only; other roles fail closed until row-level ownership filters exist.
- This is an isolated pilot, not a production-ready replacement: no UI wiring, session revocation/logout endpoint, CSRF strategy for future state-changing endpoints, or complete role-specific portal API yet. Legacy JSON authentication and all legacy workflows remain unchanged.
- CI workflow runs are not verified as successful. The GitHub commit-status endpoint returned an empty status list, and direct workflow-page retrieval was unavailable. Review Actions logs before treating the changes as passing.

## Step 6: read-only maintenance workflow pilot

- CI now applies migrations 001, 002 and 003 before running test discovery. Integration tests no longer reapply those migrations.
- `GET /api/agency/workflows/{cases,appointments,jobs,approvals,documents}` requires a valid PostgreSQL agency session.
- Agents can read these collections within their own agency; tenant/landlord reads of cases and appointments are limited to explicitly granted property assignments. Trades and all non-agent job, approval and document reads fail closed pending record-specific grants.
- `GET /api/agency/properties` uses explicit property assignments for non-agent roles.
- All endpoints are read-only. No approval, job assignment, repair creation, messages, uploads, portal UI wiring or production data migration has been completed.
- CI results remain unverified: available connector workflow-run lookup only searches pull-request-triggered runs; this workflow triggers on branch pushes. No green status is asserted.

## Step 6 continuation: assignment and repair creation pilot

- Migration `004_workflow_assignments.sql` adds RLS-protected `job_assignments` and `approval_recipients` tables.
- Trades can read assigned jobs; landlords can read assigned approvals. Unassigned records are hidden.
- `POST /api/agency/cases` creates an open case only for a tenant with an explicit property grant, using an agency PostgreSQL session. It requires a same-origin `Origin` header and a JSON body with `property_id` and `description`.
- Job creation/assignment, approval decisions, appointment updates, messaging, document grants, and portal UI wiring are still outstanding. Existing JSON portal workflows are unchanged.
- The GitHub connector still does not verify branch-push Actions run outcomes. Commits and test additions do not prove tests passed.

## Step 6: isolated four-role browser preview

- Visit `/hq-agency` on a **development server** with `ROGER_STORAGE_BACKEND=postgres`, `ROGER_DATABASE_URL`, and migrations 001-006 applied.
- This page signs into `/api/agency/login` and loads role-scoped properties, cases, jobs, approvals, appointments, documents and inbox messages. It offers tenant case creation, agent job assignment, landlord approval decisions, tenant/landlord appointment responses and agency messaging.
- The preview does not modify the existing `/agent`, `/tenant`, `/landlord`, or `/trades` pages. Document listing shows metadata, not file contents; secure upload/download remains outstanding.
- A smoke test checks the new route, but GitHub Actions execution and PostgreSQL integration tests have **not** been independently verified green.
- Important: the development preview requires seeded agency accounts, memberships, property grants and relevant workflow records. It is not ready for production rollout.
