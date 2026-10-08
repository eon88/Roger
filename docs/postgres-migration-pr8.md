# PostgreSQL migration bridge

Roger can run from the existing JSON store or an opt-in PostgreSQL snapshot backend. The default remains file storage.

The migration script preserves the original stage and user documents in singleton JSONB snapshots, then builds indexed per-entity projections for Parties, properties, tenancies, cases, jobs and documents. Stable record IDs and source JSON are retained. The projections are rebuilt transactionally whenever the stage snapshot is saved; they are a compatibility bridge for the current whole-stage write model, not a claim that every workflow has been redesigned as normalized SQL.

Before using a target database:

1. Create a private PostgreSQL database with TLS and credentials stored in the deployment secret store.
2. Stop writes to the source Roger instance and create a verified backup.
3. Install the optional driver: `pip install "psycopg[binary]>=3.2,<4"`.
4. Validate the source without connecting:
   `DATA_DIR=/path/to/roger-data python scripts/migrate_json_to_postgres.py --check-only`
5. Review every warning and the entity counts.
6. Import the snapshots:
   `DATABASE_URL=<secret> DATA_DIR=/path/to/roger-data python scripts/migrate_json_to_postgres.py`
7. Verify the snapshots, entity counts, login and portal workflows on a staging copy.
8. Only then set `ROGER_STORAGE_BACKEND=postgres` and `DATABASE_URL` on the application.

When PostgreSQL mode is enabled, Roger fails clearly if the snapshots are missing; it does not silently fall back to local JSON. Keep the source backup until restore has been verified. Uploaded file bodies are still embedded in document JSON, so object storage remains a separate migration.
