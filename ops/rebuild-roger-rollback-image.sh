#!/usr/bin/env bash
# Recover a runnable rollback image when Docker has pruned the original
# image's content metadata. Never stops the live container or touches /data.
# Usage: bash ops/rebuild-roger-rollback-image.sh <tag> <Dockerfile> <backup-dir>
set -Eeuo pipefail
umask 077

TAG="$1"
TRUSTED_DOCKERFILE="$2"
RESCUE="$3"

if [[ ! "$TAG" =~ ^roger-rollback:[0-9a-f]{12}$ ]]; then
  echo "ERROR: invalid rollback image tag" >&2
  exit 2
fi
if [[ ! -f "$TRUSTED_DOCKERFILE" ]]; then
  echo "ERROR: trusted Dockerfile unavailable" >&2
  exit 2
fi
if [[ ! "$RESCUE" =~ ^/root/roger-backups/gha-deploy-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}/previous-app$ ]]; then
  echo "ERROR: rescue destination must be within a private deployment backup" >&2
  exit 2
fi

# The currently running overlay filesystem can be readable even when Docker's
# image store is damaged. Copy ONLY /app, never the live /data mount.
test "$(docker inspect roger --format '{{.State.Running}}')" = "true"
docker inspect roger --format '{{range .Config.Env}}{{println .}}{{end}}' |
  grep -qx 'ROGER_STORAGE_BACKEND=postgres'
RUNNING_ENTRYPOINT="$(docker inspect roger --format '{{json .Config.Entrypoint}}')"
RUNNING_WORKDIR="$(docker inspect roger --format '{{.Config.WorkingDir}}')"
RUNNING_USER="$(docker inspect roger --format '{{.Config.User}}')"
if [[ "$RUNNING_ENTRYPOINT" != '["/app/docker-entrypoint.sh"]' ||
      "$RUNNING_WORKDIR" != "/app" || -n "$RUNNING_USER" ]]; then
  echo "ERROR: running image config differs from the reviewed layout; stopping safely." >&2
  exit 1
fi

install -d -m 700 "$RESCUE/stage-clone"
docker cp roger:/app/. "$RESCUE/stage-clone/"
for required in serve.py index.html login.html agent.html docker-entrypoint.sh make_users.py stage.json; do
  if [[ ! -f "$RESCUE/stage-clone/$required" ]]; then
    echo "ERROR: running source missing $required; cannot ensure rollback" >&2
    exit 1
  fi
done

# Fail closed if live /app contains unexpected links or credential files;
# such files must never be baked into the reconstructed image.
if find "$RESCUE/stage-clone" \
    \( -type l -o -name '.env' -o -name '*.pem' -o -name 'id_rsa' -o -name 'id_ed25519' \) \
    -print -quit | grep -q .; then
  echo "ERROR: /app contains links or credential-like files; cannot package it safely." >&2
  exit 1
fi
cp -p "$TRUSTED_DOCKERFILE" "$RESCUE/Dockerfile"

# Drop runtime byproducts, not application sources.
find "$RESCUE/stage-clone" -type f \
  \( -name '*.pyc' -o -name '*.log' \) -delete
find "$RESCUE/stage-clone" -type d -name __pycache__ -prune -exec rm -rf {} +

echo "=== REBUILD PREVIOUS APP IMAGE FROM LIVE APP FILES ==="
docker build --label "roger.backup.origin=live-app-copy" -t "$TAG" "$RESCUE"

test "$(docker image inspect "$TAG" --format '{{json .Config.Entrypoint}}')" = "$RUNNING_ENTRYPOINT"
test "$(docker image inspect "$TAG" --format '{{.Config.WorkingDir}}')" = "$RUNNING_WORKDIR"
test "$(docker image inspect "$TAG" --format '{{.Config.User}}')" = "$RUNNING_USER"

# A runnable Docker image and identical critical source are prerequisites.
for file in serve.py index.html login.html agent.html docker-entrypoint.sh make_users.py; do
  live_hash="$(docker exec roger sha256sum "/app/$file" | awk '{print $1}')"
  backup_hash="$(docker run --rm --entrypoint sha256sum "$TAG" "/app/$file" | awk '{print $1}')"
  if [[ -z "$live_hash" || "$live_hash" != "$backup_hash" ]]; then
    echo "ERROR: backup differs from currently running /app/$file" >&2
    exit 1
  fi
done
docker run --rm --entrypoint python "$TAG" -c '
import psycopg, py_compile
py_compile.compile("/app/serve.py", doraise=True)
print("Rollback image Python compiles and PostgreSQL driver loads.")
'

echo "RECOVERABLE PREVIOUS APP IMAGE: $TAG"
echo "Private source snapshot: $RESCUE"
