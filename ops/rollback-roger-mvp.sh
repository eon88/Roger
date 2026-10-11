#!/usr/bin/env bash
# Manual application-only rollback. Database and document files are preserved.
set -Eeuo pipefail
umask 077

ALLOW_LEGACY="$1"
if [[ "$ALLOW_LEGACY" != "true" && "$ALLOW_LEGACY" != "false" ]]; then
  echo "ERROR: legacy snapshot option must be true or false" >&2
  exit 2
fi

exec 9>/var/lock/roger-mvp-deploy.lock
if ! flock -n 9; then
  echo "ERROR: deployment or rollback already in progress" >&2
  exit 1
fi

BASE="/docker/roger/docker-compose.yml"
OVERRIDE="/docker/roger/docker-compose.override.yml"
DB_ENV="/docker/roger-postgres/roger-db.env"
BACKUPS="/root/roger-backups"
NOW="$(date -u +%Y%m%dT%H%M%SZ)"

echo "=== VALIDATE EXISTING ROGER ==="
test -f "$BASE" && test -f "$OVERRIDE" && test -f "$DB_ENV"
grep -qF '/docker/roger-postgres/roger-db.env' "$OVERRIDE"
docker inspect roger >/dev/null
docker inspect roger-postgres >/dev/null
test "$(docker inspect roger-postgres --format '{{.State.Health.Status}}')" = "healthy"
docker inspect roger --format '{{range .Config.Env}}{{println .}}{{end}}' |
  grep -qx 'ROGER_STORAGE_BACKEND=postgres'
CURRENT_IMAGE_ID="$(docker inspect roger --format '{{.Image}}')"
test -n "$CURRENT_IMAGE_ID"
test "$(docker inspect roger --format '{{.State.Running}}')" = "true"
(cd /docker/roger && docker compose config --quiet)

# Only select a previous-image snapshot from a deploy of the EXACT image now
# running. Never guess an older release or use failed-deploy snapshots.
SOURCE_BACKUP=""
SOURCE_SHA=""
if [[ -d "$BACKUPS" ]]; then
  while IFS= read -r candidate_name; do
    [[ "$candidate_name" =~ ^gha-deploy-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$ ]] || continue
    candidate="$BACKUPS/$candidate_name"
    [[ -d "$candidate" && ! -L "$candidate" && -f "$candidate/new_release_sha" ]] || continue
    sha=""
    read -r sha < "$candidate/new_release_sha" || true
    [[ "$sha" =~ ^[a-f0-9]{40}$ ]] || continue
    short="$(printf '%s' "$sha" | cut -c1-12)"
    [[ "$candidate_name" == *"-$short" ]] || continue
    expected_image="roger-mvp:$short"
    expected_id="$(docker image inspect "$expected_image" --format '{{.Id}}' 2>/dev/null || true)"
    [[ -n "$expected_id" && "$expected_id" == "$CURRENT_IMAGE_ID" ]] || continue
    if [[ -f "$candidate/deployment-success.sha" ]]; then
      marked=""
      read -r marked < "$candidate/deployment-success.sha" || true
      [[ "$marked" == "$sha" ]] || continue
    elif [[ "$ALLOW_LEGACY" != "true" ]]; then
      echo "Matching old snapshot $candidate_name has no success marker." >&2
      echo "Enable the 'older snapshot' checkbox only if this was a known good deployment." >&2
      exit 1
    fi
    SOURCE_BACKUP="$candidate"
    SOURCE_SHA="$sha"
    break
  done < <(find "$BACKUPS" -mindepth 1 -maxdepth 1 -type d \
            -name 'gha-deploy-*' -printf '%f\n' | LC_ALL=C sort -r)
fi

if [[ -z "$SOURCE_BACKUP" ]]; then
  echo "ERROR: no valid deployment snapshot matches the running Roger image." >&2
  echo "Refusing to roll back an unknown/manual release." >&2
  exit 1
fi

SHORT="$(printf '%s' "$SOURCE_SHA" | cut -c1-12)"
TARGET_IMAGE="roger-rollback:$SHORT"
TARGET_IMAGE_ID="$(docker image inspect "$TARGET_IMAGE" --format '{{.Id}}' 2>/dev/null || true)"
if [[ -z "$TARGET_IMAGE_ID" || "$TARGET_IMAGE_ID" == "$CURRENT_IMAGE_ID" ]]; then
  echo "ERROR: distinct saved previous application image not available." >&2
  exit 1
fi
test -s "$SOURCE_BACKUP/roger-postgres.dump"
test -f "$SOURCE_BACKUP/docker-compose.override.yml"
docker image inspect "$TARGET_IMAGE" --format '{{json .Config.Entrypoint}}' |
  grep -qv '^null$'

echo "Source deployment: $SOURCE_SHA"
echo "Restoring previous app image: $TARGET_IMAGE"
echo "Database: PRESERVED. Files: PRESERVED."
echo "Note: older application code may be incompatible with a newer DB schema."

# Snapshot the CURRENT data again before attempting an app-only rollback.
SAFETY="$BACKUPS/manual-rollback-$NOW-$SHORT"
install -d -m 700 "$SAFETY/data"
cp -p "$BASE" "$SAFETY/docker-compose.yml"
cp -p "$OVERRIDE" "$SAFETY/docker-compose.override.yml"
printf '%s\n' "$SOURCE_SHA" > "$SAFETY/rolled_back_deploy_sha"
printf '%s\n' "$SOURCE_BACKUP" > "$SAFETY/rollback_source_backup"

# Keep a runnable image of the current app for automatic emergency recovery.
FORWARD_IMAGE="roger-before-rollback:$SHORT"
if docker image inspect "$CURRENT_IMAGE_ID" >/dev/null 2>&1; then
  docker image tag "$CURRENT_IMAGE_ID" "$FORWARD_IMAGE"
else
  docker commit --pause=false roger "$FORWARD_IMAGE" >/dev/null
fi
docker image inspect "$FORWARD_IMAGE" >/dev/null

set_override_image() {
  python3 - "$OVERRIDE" "$1" <<'PY'
from pathlib import Path
import os
import re
import sys
p = Path(sys.argv[1])
new_image = sys.argv[2]
content = p.read_text()
assert "/docker/roger-postgres/roger-db.env" in content, "PostgreSQL env missing"
pattern = r"(?m)^(    image:\s*)[^\n]+$"
assert len(re.findall(pattern, content)) == 1, "expected exactly one Roger image"
content = re.sub(pattern, lambda m: m.group(1) + new_image, content, count=1)
temp = p.with_name(p.name + ".rollback-tmp")
temp.write_text(content)
os.chmod(temp, p.stat().st_mode & 0o777)
os.replace(temp, p)
PY
}

STOPPED=0
SUCCESS=0
recover_on_failure() {
  local exit_code=$?
  trap - EXIT
  if [[ "$SUCCESS" != 1 && "$STOPPED" == 1 ]]; then
    echo "=== ROLLBACK FAILED: RESTORE PRE-ROLLBACK APP IMAGE ===" >&2
    cp -p "$SAFETY/docker-compose.override.yml" "$OVERRIDE"
    set_override_image "$FORWARD_IMAGE" || true
    (cd /docker/roger && docker compose config --quiet &&
      docker compose up -d --no-build --no-deps --force-recreate \
        --wait --wait-timeout 120 roger) ||
      echo "CRITICAL: recovery failed. See backup $SAFETY" >&2
  fi
  if [[ "$SUCCESS" != 1 ]]; then
    echo "No PostgreSQL data was restored or rolled back." >&2
    echo "Pre-rollback backup: $SAFETY" >&2
  fi
  exit "$exit_code"
}
trap recover_on_failure EXIT

echo "=== STOP APP AND BACK UP THE CURRENT DB/FILES ==="
docker stop roger >/dev/null
STOPPED=1
docker exec roger-postgres pg_dump -U roger -d roger -Fc > "$SAFETY/roger-postgres.dump"
test -s "$SAFETY/roger-postgres.dump"
docker exec -i roger-postgres pg_restore --list < "$SAFETY/roger-postgres.dump" >/dev/null
docker cp roger:/data/. "$SAFETY/data/"
sha256sum "$SAFETY/roger-postgres.dump" > "$SAFETY/roger-postgres.dump.sha256"

echo "=== START PREVIOUS APPLICATION ==="
set_override_image "$TARGET_IMAGE"
(cd /docker/roger && docker compose config --quiet)
(cd /docker/roger && docker compose up -d --no-build --no-deps \
  --force-recreate --wait --wait-timeout 120 roger)

echo "=== VERIFY RESTORED APPLICATION ==="
test "$(docker inspect roger --format '{{.Image}}')" = "$TARGET_IMAGE_ID"
docker inspect roger --format '{{range .Config.Env}}{{println .}}{{end}}' |
  grep -qx 'ROGER_STORAGE_BACKEND=postgres'
curl -fsS --max-time 15 http://127.0.0.1:8901/api/public -o /dev/null
test "$(curl --max-time 15 -sS -o /dev/null -w '%{http_code}' \
  http://127.0.0.1:8901/api/stage)" = "401"
curl -fsS --max-time 15 http://127.0.0.1:8901/login -o /dev/null

printf 'SUCCESS\n' > "$SAFETY/rollback-success"
SUCCESS=1
trap - EXIT
echo "ROGER APPLICATION ROLLBACK SUCCESSFUL"
echo "Restored image: $TARGET_IMAGE"
echo "Database: unchanged; no previous dump imported."
echo "New safety backup: $SAFETY"
echo "Website: https://agency.lifecompass.shop"
