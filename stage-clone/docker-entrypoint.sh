#!/bin/sh
set -eu

DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"

# SaaS agency stacks have an independently bootstrapped PostgreSQL database.
# Never create demo/dev accounts or print passwords to container logs.
if [ "${ROGER_SAAS_MODE:-0}" = "1" ]; then
  if [ "${ROGER_STORAGE_BACKEND:-}" != "postgres" ] || [ -z "${ROGER_AGENCY_ID:-}" ]; then
    echo "ERROR: SaaS mode requires dedicated PostgreSQL and an agency ID" >&2
    exit 1
  fi
  python - <<'PY'
import os
import psycopg
with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
    stage_row = connection.execute(
        "SELECT payload FROM roger_stage_snapshot WHERE singleton_id=1"
    ).fetchone()
    users_row = connection.execute(
        "SELECT payload FROM roger_users_snapshot WHERE singleton_id=1"
    ).fetchone()
if not stage_row or not users_row:
    raise SystemExit("ERROR: SaaS PostgreSQL snapshots have not been bootstrapped")
stage = stage_row[0]
users = users_row[0]
if stage.get("agency_id") != os.environ["ROGER_AGENCY_ID"]:
    raise SystemExit("ERROR: wrong agency database. Start refused.")
accounts = users.get("users")
if not isinstance(accounts, list) or not any(
    u.get("role") == "agent" and u.get("username") == "agency-admin"
    for u in accounts if isinstance(u, dict)
) or any(u.get("username") == "dev" for u in accounts if isinstance(u, dict)):
    raise SystemExit("ERROR: invalid agency admin identity or unsafe dev account")
print("Dedicated agency database and admin identity verified.")
PY
  exec python /app/serve.py
fi

if [ ! -f "$DATA_DIR/stage.json" ]; then
  echo "Initialising Roger data store..."
  cp /app/stage.seed.json "$DATA_DIR/stage.json"
fi

if [ ! -f "$DATA_DIR/users.json" ]; then
  echo "Creating initial Roger portal accounts..."
  DATA_DIR="$DATA_DIR" python /app/make_users.py
  echo
  echo "IMPORTANT: save the generated passwords shown above."
  echo "They are generated only when users.json is first created."
fi

exec python /app/serve.py
