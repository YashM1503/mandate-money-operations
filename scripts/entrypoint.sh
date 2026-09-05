#!/bin/sh
set -eu
DATA_DIR="${MANDATE_DATA_DIR:-/data}"
if [ -z "${MANDATE_SIGNING_KEY:-}" ] && [ ! -f "$DATA_DIR/config.json" ]; then
  python /app/scripts/bootstrap.py
fi
exec uvicorn mandate.api:create_app --factory --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --no-proxy-headers
