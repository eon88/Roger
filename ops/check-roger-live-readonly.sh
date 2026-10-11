#!/usr/bin/env bash
# Safe, read-only checks from within the Hostinger VPS; no production records changed.
set -Eeuo pipefail
BASE="http://127.0.0.1:8901"

check_status() {
  local route="$1" expected="$2" got
  got="$(curl --max-time 15 --connect-timeout 5 -sS -o /dev/null -w '%{http_code}' "$BASE$route")"
  if [[ "$got" != "$expected" ]]; then
    echo "FAIL $route: expected HTTP $expected, received $got" >&2
    exit 1
  fi
  echo "PASS $route: HTTP $got"
}

echo "=== Live Roger: infrastructure (no user data printed) ==="
test "$(docker inspect roger --format '{{.State.Running}}')" = true
test "$(docker inspect roger --format '{{.State.Health.Status}}')" = healthy
test "$(docker inspect roger-postgres --format '{{.State.Health.Status}}')" = healthy
docker inspect roger --format '{{range .Config.Env}}{{println .}}{{end}}' |
  grep -qx 'ROGER_STORAGE_BACKEND=postgres'
echo "PASS Roger and PostgreSQL containers are healthy; DB backend is postgres"

echo "=== Live Roger: public pages and API ==="
for route in / /login /api/public /api/whoami; do check_status "$route" 200; done
curl --max-time 15 -fsS "$BASE/api/whoami" |
  python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("authenticated") is False, "anonymous session authenticated"; print("PASS anonymous session stays anonymous")'

echo "=== Live Roger: protected routes without a login ==="
for route in /agent /tenant /landlord /trades /api/stage /api/documents /api/appointments /api/notifications; do
  check_status "$route" 401
done

echo "=== SUCCESS: live read-only smoke ==="
echo "No login attempted; no tenant, invoice, document or other record was changed."
echo "Four-role business workflows still require dedicated authenticated test users."
