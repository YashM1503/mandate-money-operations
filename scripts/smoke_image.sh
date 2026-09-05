#!/bin/sh
# Smoke a built Mandate image: health, Money Operations UI, packaged fixtures.
set -eu
IMAGE="${1:-mandate-ci}"
NAME="mandate-smoke-$$"
PORT="${SMOKE_PORT:-18000}"
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker run -d --name "$NAME" -p "127.0.0.1:${PORT}:8000" \
  -e MANDATE_ALLOWED_HOSTS=localhost,127.0.0.1 \
  "$IMAGE" >/dev/null
i=0
while [ "$i" -lt 40 ]; do
  if curl -fsS "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
    break
  fi
  i=$((i + 1))
  sleep 1
done
curl -fsS "http://127.0.0.1:${PORT}/healthz"
echo
code=$(curl -fsS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/money-operations")
[ "$code" = "200" ]
demo=$(curl -fsS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/demo.html")
[ "$demo" = "200" ]
docker exec "$NAME" test -f /app/sample-data/money-operations/monthly_account_summaries.csv
docker exec "$NAME" test -f /data/config.json
echo "image smoke ok"
