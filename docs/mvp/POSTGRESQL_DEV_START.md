# Roger PostgreSQL development foundation — milestone 0

**Status:** repository preparation only; do not connect production Roger yet.

The prototype's future storage needs: landlord property submissions, tenancy
people/ownership, maintenance cases, private messages, trades credentials,
work orders, invoices, rent payments, deadlines, notifications and audit events.

## Hard safety boundaries

- Production site: `https://agency.lifecompass.shop` is still run by
  `/docker/roger/docker-compose.yml` with the **JSON** volume
  `roger_roger_data`; keep it that way during development.
- Development database uses a **different Docker Compose project** called
  `roger-pg-dev`, a named volume called `roger-pg-dev_pg_dev_data`, and a
  private internal Docker network. **No host ports and no Traefik labels**.
- Development data only: no production database import, no credentials copied
  from the live users file, and no production `DATABASE_URL`.
- Never run `docker compose down -v`, `docker volume prune`, or destructive
  database reset commands. Do not change the production Compose file or Docker
  volume for this milestone.
- The password is generated and held on the VPS only at
  `deploy/postgres/secrets/db_password` (excluded from Git).
- Current schema is a starting design, not a complete security/privacy or
  compliance implementation. PostgreSQL does not grant table-level scoping
  by itself. Authorization remains a required backend feature.

## Tomorrow: preparation and installation

From the VPS, use a **separate checkout** of
`feature/postgres-dev-foundation-20261010`. Do not overwrite the modified
production checkout `/docker/roger` or a running release.

1. Verify Docker availability, free memory and disk, and Roger health:
   `free -h`, `df -h /var/lib/docker`,
   `docker inspect roger --format '{{.State.Health.Status}}'`.
2. Fetch/checkout the dedicated development branch in a separate working
   directory; confirm the full commit SHA against GitHub.
3. Run `bash scripts/dev_postgres_setup.sh --check-only`.
4. After inspecting the Compose config and confirming the data volume is
   isolated, run `bash scripts/dev_postgres_setup.sh --install`.
5. Verify database tables using:

   ```bash
   docker compose -p roger-pg-dev -f deploy/postgres/compose.dev.yml \
     exec -T postgres psql -U roger_dev -d roger_dev \
     -c "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'mvp_%';"
   ```

6. Verify live Roger remains healthy; do **not** change live data storage.

The install script is repeatable: it leaves an existing password/volume in
place and the schema uses `CREATE TABLE IF NOT EXISTS`.

## What already exists versus what is new

- `migrations/001_postgres_stage_schema.sql` and
  `scripts/migrate_json_to_postgres.py` were created earlier for a **JSONB
  snapshot bridge**. That script imports whole snapshots and truncates bridge
  collections. **Do not run it against live data.**
- `migrations/002_mvp_relational_dev.sql` introduces purpose-built tables,
  all prefixed `mvp_`, so the experimental schema does not collide with the
  bridge. It models Parties, properties, ownership, submissions, documents,
  compliance, contractor credentials, repairs, scoped conversations, work
  orders, invoices, rent charges/payments, agent tasks, audit events and an
  event outbox.
- These tables are an initial design: future migrations must add version
  tracking, granular auth, client isolation rules, invoice line items, UK
  compliance by jurisdiction, rent reconciliation, scheduled reminders and
  audited administrator operations.
- An append-only audit trigger blocks ordinary UPDATE/DELETE operations.
  This is not tamper-proof against a database owner/superuser; production
  needs restricted roles, backups and external audit export.

## Development milestones after setup

1. Review/update schema with the V1–V5 MVP feature inventory.
2. Connect a **separate test instance** of the Roger app, not production.
3. Generate fictional test accounts/properties only; verify all four roles.
4. Implement backend workflows, secure document storage and automation.
5. Test data export/import, transaction safety, isolation and backup restore.
6. Write a separate production migration plan with rollback checkpoints,
   and seek explicit approval before any cutover.

## Troubleshooting and operations

```bash
# Status:
docker compose -p roger-pg-dev -f deploy/postgres/compose.dev.yml ps

# Database logs without printing any password:
docker compose -p roger-pg-dev -f deploy/postgres/compose.dev.yml logs --tail=60 postgres

# Stop only the development database (keeps the data volume):
docker compose -p roger-pg-dev -f deploy/postgres/compose.dev.yml stop postgres
```

**Never share or commit the password file, the production .env, or real
tenant/landlord data.**
