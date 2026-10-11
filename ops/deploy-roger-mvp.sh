#!/usr/bin/env bash
# Roger: GitHub Actions-triggered deployment on the Hostinger VPS.
# This script is streamed over authenticated SSH; its application archive is
# prepared from an exact GitHub commit and uploaded separately.
set -Eeuo pipefail
umask 077

SHA="${1:-}"
ARCHIVE="${2:-}"
if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ERROR: expected a 40-character commit SHA" >&2
  exit 2
fi
if [[ "$ARCHIVE" != "/root/roger-deploy/incoming/$SHA.tar.gz" || ! -s "$ARCHIVE" ]]; then
  echo "ERROR: exact uploaded release archive is missing" >&2
  exit 2
fi

exec 9>/var/lock/roger-mvp-deploy.lock
if ! flock -n 9; then
  echo "Another Roger deployment is running; refusing to overlap." >&2
  exit 1
fi

SHORT="${SHA:0:12}"
IMAGE="roger-mvp:$SHORT"
BASE="/docker/roger/docker-compose.yml"
OVERRIDE="/docker/roger/docker-compose.override.yml"
DB_ENV="/docker/roger-postgres/roger-db.env"
RELEASE="/root/roger-deploy/releases/$SHA"
BACKUP="/root/roger-backups/gha-deploy-$(date -u +%Y%m%dT%H%M%SZ)-$SHORT"

echo "=== PREPARE $SHORT ==="
test -f "$BASE"
test -f "$OVERRIDE"
test -f "$DB_ENV"
docker inspect roger >/dev/null
docker inspect roger-postgres >/dev/null
test "$(docker inspect roger-postgres --format '{{.State.Health.Status}}')" = "healthy"
docker inspect roger --format '{{range .Config.Env}}{{println .}}{{end}}' |
  grep -qx 'ROGER_STORAGE_BACKEND=postgres'
grep -qF '/docker/roger-postgres/roger-db.env' "$OVERRIDE"

# Build from the uploaded revision WITHOUT touching the outdated /docker/roger checkout.
install -d -m 700 "$RELEASE"
tar -xzf "$ARCHIVE" -C "$RELEASE"
test -f "$RELEASE/Dockerfile"
test -f "$RELEASE/stage-clone/serve.py"
docker build --label "org.opencontainers.image.revision=$SHA" -t "$IMAGE" "$RELEASE"
docker run --rm --entrypoint python "$IMAGE" -c '
import psycopg, py_compile
py_compile.compile("/app/serve.py", doraise=True)
print("Roger image includes PostgreSQL driver and compiles.")
'

echo "=== TAKE RESTORABLE BACKUPS ==="
install -d -m 700 "$BACKUP/data"
cp -p "$BASE" "$BACKUP/docker-compose.yml"
cp -p "$OVERRIDE" "$BACKUP/docker-compose.override.yml"
docker image tag "$(docker inspect roger --format '{{.Image}}')" "roger-rollback:$SHORT"
printf '%s\n' "$SHA" > "$BACKUP/new_release_sha"

STOPPED=0
SWITCHED=0
SUCCESS=0

rollback() {
  local result=$?
  trap - EXIT
  if [[ "$SUCCESS" != "1" ]]; then
    echo "=== DEPLOYMENT FAILED — RESTORE PREVIOUS APP IMAGE ===" >&2
    if [[ "$SWITCHED" == "1" ]]; then
      cp -p "$BACKUP/docker-compose.override.yml" "$OVERRIDE"
    fi
    if [[ "$STOPPED" == "1" ]]; then
      (cd /docker/roger && docker compose up -d --no-build --no-deps \
        --force-recreate --wait --wait-timeout 120 roger) ||
        echo "ERROR: automatic app rollback failed; see $BACKUP" >&2
    fi
    echo "Database has NOT been automatically restored. Dump: $BACKUP/roger-postgres.dump" >&2
  fi
  exit "$result"
}
trap rollback EXIT

# The application is paused while the snapshots are taken so the DB dump and
# remaining on-disk files belong to the same quiet point in time.
echo "=== QUIESCE ROGER AND BACK UP POSTGRESQL ==="
docker stop roger >/dev/null
STOPPED=1
docker exec roger-postgres pg_dump -U roger -d roger -Fc > "$BACKUP/roger-postgres.dump"
test -s "$BACKUP/roger-postgres.dump"
docker exec -i roger-postgres pg_restore --list < "$BACKUP/roger-postgres.dump" >/dev/null
docker cp roger:/data/. "$BACKUP/data/"

echo "=== UPDATE IMAGE PIN AND START ROGER ==="
python3 - "$OVERRIDE" "$IMAGE" <<'PY'
from pathlib import Path
import re
import sys
p = Path(sys.argv[1])
new_image = sys.argv[2]
content = p.read_text()
assert "/docker/roger-postgres/roger-db.env" in content, "PostgreSQL env file missing"
pattern = r"(?m)^(    image:\s*)[^\n]+$"
assert len(re.findall(pattern, content)) == 1, "expected one Roger image line"
content = re.sub(pattern, lambda m: m.group(1) + new_image, content, count=1)
p.write_text(content)
PY
SWITCHED=1
(cd /docker/roger && docker compose config --quiet)
(cd /docker/roger && docker compose up -d --no-build --no-deps \
  --force-recreate --wait --wait-timeout 120 roger)

echo "=== VERIFY LIVE ROGER ==="
test "$(docker inspect roger --format '{{.Image}}')" = \
  "$(docker image inspect "$IMAGE" --format '{{.Id}}')"
docker inspect roger --format '{{range .Config.Env}}{{println .}}{{end}}' |
  grep -qx 'ROGER_STORAGE_BACKEND=postgres'
curl -fsS --max-time 15 http://127.0.0.1:8901/api/public -o /dev/null
test "$(curl --max-time 15 -sS -o /dev/null -w '%{http_code}' \
  http://127.0.0.1:8901/api/stage)" = "401"
curl -fsS --max-time 15 http://127.0.0.1:8901/login -o /dev/null

SUCCESS=1
trap - EXIT
echo "ROGER DEPLOYMENT SUCCESSFUL: $SHA"
echo "Application: https://agency.lifecompass.shop"
echo "Rollback backup: $BACKUP"
echo "Note: database snapshots are preserved; automatic rollback only changes the app image."
