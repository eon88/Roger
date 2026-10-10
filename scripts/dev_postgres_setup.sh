#!/usr/bin/env bash
# DEV ONLY - does not touch /docker/roger, the live volume, or live Roger.
set -Eeuo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/deploy/postgres/compose.dev.yml"
SCHEMA="$ROOT/migrations/002_mvp_relational_dev.sql"
SECRET_DIR="$ROOT/deploy/postgres/secrets"
SECRET_FILE="$SECRET_DIR/db_password"
DC=(docker compose -p roger-pg-dev -f "$COMPOSE")

test -f "$COMPOSE" && test -f "$SCHEMA"
command -v docker >/dev/null
docker info >/dev/null

echo "=== PRODUCTION GUARD ==="
if docker container inspect roger >/dev/null 2>&1; then
  test "$(docker inspect roger --format '{{.State.Health.Status}}')" = "healthy" || {
    echo "Live Roger is not healthy. Do not change anything until investigated." >&2
    exit 1
  }
  echo "Live Roger: healthy (no changes)"
fi

if [ -L "$SECRET_DIR" ] || [ -L "$SECRET_FILE" ]; then
  echo "Secret location may not be a symlink" >&2
  exit 1
fi

if [ "${1:-}" = "--check-only" ]; then
  echo "CHECK ONLY: no Docker resources, secret or database created"
  echo "Compose project: roger-pg-dev"
  echo "Dev volume: roger-pg-dev_pg_dev_data"
  exit 0
fi
if [ "${1:-}" != "--install" ]; then
  echo "Usage: $0 --check-only | --install" >&2
  exit 2
fi

echo "=== PREPARE PRIVATE PASSWORD ==="
mkdir -p "$SECRET_DIR"
chmod 700 "$SECRET_DIR"
if [ ! -e "$SECRET_FILE" ]; then
  command -v openssl >/dev/null
  # Never display this password or commit it to Git.
  ( set -C; openssl rand -hex 32 > "$SECRET_FILE" )
  chmod 600 "$SECRET_FILE"
  echo "Created local-only PostgreSQL password"
else
  test -f "$SECRET_FILE" && test -s "$SECRET_FILE"
  chmod 600 "$SECRET_FILE"
  echo "Reusing existing local-only password"
fi

echo "=== VERIFY ISOLATION ==="
"${DC[@]}" config --quiet
"${DC[@]}" config --format json | python3 -c '
import json,sys
d=json.load(sys.stdin)
assert d.get("name") == "roger-pg-dev"
assert set(d["services"]) == {"postgres"}
s=d["services"]["postgres"]
assert not s.get("ports") and not s.get("network_mode")
assert any(n["target"] == "/var/lib/postgresql/data" and
           n["source"] == "pg_dev_data" and n["type"] == "volume"
           for n in s["volumes"])
assert all(d["networks"][name].get("internal") for name in s["networks"])
print("Isolated Compose project, storage and private network: PASS")
'

echo "=== START DEV POSTGRESQL ==="
"${DC[@]}" up -d postgres
CID="$("${DC[@]}" ps -q postgres)"
test -n "$CID"
for i in $(seq 1 60); do
  STATE="$(docker inspect "$CID" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}')"
  [ "$STATE" = healthy ] && break
  sleep 2
done
test "$(docker inspect "$CID" --format '{{.State.Health.Status}}')" = healthy

echo "=== INSTALL MVP DEVELOPMENT SCHEMA ==="
"${DC[@]}" exec -T postgres psql -X -v ON_ERROR_STOP=1     -U roger_dev -d roger_dev < "$SCHEMA" >/dev/null
"${DC[@]}" exec -T postgres psql -X -v ON_ERROR_STOP=1     -U roger_dev -d roger_dev     -c "SELECT count(*) AS mvp_tables FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'mvp_%';"

echo "=== FINAL STATUS ==="
"${DC[@]}" ps postgres
if docker container inspect roger >/dev/null 2>&1; then
  test "$(docker inspect roger --format '{{.State.Health.Status}}')" = healthy
  echo "Live Roger: healthy and unchanged"
fi
echo "DEV POSTGRESQL READY - PRODUCTION STILL USES JSON"
